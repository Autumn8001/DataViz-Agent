import datetime
import json
from pathlib import Path
import re
import sys
import threading
from typing import Literal
import time
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    RemoveMessage,
    SystemMessage,
)
from langgraph.graph import END, START, StateGraph
import pandas as pd

# 强制标准输出与错误输出为 UTF-8 编码，解决 Windows 终端中文/Emoji 打印导致的 UnicodeEncodeError 闪退
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

from .database import get_checkpointer
from .llm_factory import LLMFactory
from .sandbox import run_in_sandbox
from .state import AgentState

# ======================================================================
# 1. 实例化核心大模型组件
# ======================================================================
flash_llm = LLMFactory.get_flash_model()  # 意图规划/轻量分类节点
core_llm = LLMFactory.get_core_model()  # 核心程序员/总结报告节点


# ======================================================================
# 节点 0：数据探针与认知层 (Profiler)
# ======================================================================
def profiler_node(state: AgentState) -> dict:
    """数据探针：在一切开始之前，先摸清数据的底细"""
    start_time=time.perf_counter()
    file_path = state.get("active_file_path")
    # 如果没有文件，或者之前已经探测过了（有了假设），直接放行
    if not file_path or state.get("schema_hypothesis"):
        print(f"  [Timer] profiler_node 耗时: {time.perf_counter() - start_time:.2f}s")
        return {"requires_human_approval": False}

    print("  [Profiler] 新数据注入！正在启动数据探针进行试探性探索...")
    try:
        suffix = Path(file_path).suffix.lower()
        if suffix == ".csv":
            try:
                df = pd.read_csv(file_path, encoding="utf-8-sig")
            except (UnicodeDecodeError, Exception):
                print("  [Profiler] utf-8 乱码拦截，正在降级使用 gbk 重新解析...")
                df = pd.read_csv(file_path, encoding="gb18030")
        elif suffix in [".xlsx", ".xls"]:
            df = pd.read_excel(file_path)
        else:
            # 如果大模型或者用户上传了奇怪的 txt 或 json，主动抛出异常进入下方兜底
            raise ValueError(f"不支持的文件格式: {suffix}")
        dtypes = {k: str(v) for k, v in df.dtypes.items()}
        missing = df.isnull().sum().to_dict()
        head = df.head(3).to_markdown()

        # RAG 检索企业数据字典
        dict_path = Path(__file__).parent.parent / "data" / "data_dict.json"
        with open(dict_path, "r", encoding="utf-8") as f:
            company_dict = json.load(f)

        retrieved_context = []
        for col_name in df.columns:
            meaning = company_dict.get(col_name)
            if meaning:
                retrieved_context.append(f"字段'{col_name}'在业务上的意思是：{meaning}")
        if retrieved_context:
            rag_info = "\n".join(retrieved_context)
        else:
            rag_info = "未在企业字典中检索到已知字段"

        prompt = f"""
        # 角色: 首席元数据架构师 & 数据资产探针专家
        
        # 任务目标
        对保存在路径 `{file_path}` 的上传数据集进行严格的结构化审计和资产探针扫描。并输出分析报告。

        # 输入元数据
        - 各字段数据类型: {dtypes}
        - 空值/缺失值统计: {missing}
        - 企业字典匹配情况 (RAG 检索上下文):
        {rag_info}
        - 样例数据 (前 3 行):
        {head}

        # 分析与输出要求
        你必须同时生成两个部分，并严格使用指定的 HTML 标签包裹它们：
        
        1. **用户简明总结** (包裹在 `<USER_SUMMARY>` 和 `</USER_SUMMARY>` 标签中)：
           用 2-3 句话以极度亲切、通俗易懂的中文向非技术用户总结这个数据集的主要内容。
           - 告诉用户这是关于什么的数据。
           - **如果有歧义/缺失列**：指出哪些列有歧义或缺失（例如：“我们发现 `tx_dt` 可能是日期但存为了文本，且 `qty` 列存在空值”）。
           - **如果没有歧义/缺失**：友好地告诉用户数据很干净，可以直接开始分析。

        2. **技术推测报告** (包裹在 `<DETAILED_HYPOTHESIS>` 和 `</DETAILED_HYPOTHESIS>` 标签中)：
           为后台 AI 编写代码提供详细的字段定义和质量审计报告，包括：
           - 各个字段的具体业务语义和推测含义。
           - 数据质量审计细节（异常类型、缺失比例分析等）。
           - 任务阻碍因子决策（是否必须先进行人工清洗/指定）。

        # 安全分类规则 (极其关键)
        检查元数据中的模糊性。请在响应的**最末尾一行**输出以下分类暗号之一（不要包裹在任何标签中）：
        - 如果发现高歧义列名（如词典中未包含的缩写）、需要人工确认解析格式的日期列、或关键标识字段缺失率超过 30%，必须输出：`[NEED_HUMAN]`
        - 如果数据格式非常清晰直观，字段语义明确，且数据类型无明显冲突，必须输出：`[SAFE]`
        """
        # 呼叫旗舰大脑进行认知探索
        response = core_llm.invoke([HumanMessage(content=prompt)])
        raw_content = response.content.strip()

        user_summary_match = re.search(
            r"<USER_SUMMARY>(.*?)</USER_SUMMARY>", raw_content, re.DOTALL
        )
        detailed_hypothesis_match = re.search(
            r"<DETAILED_HYPOTHESIS>(.*?)</DETAILED_HYPOTHESIS>", raw_content, re.DOTALL
        )

        if user_summary_match:
            user_summary = user_summary_match.group(1).strip()
        else:
            user_summary = "已完成数据分析准备。数据字段已就位。"

        if detailed_hypothesis_match:
            hypothesis = detailed_hypothesis_match.group(1).strip()
        else:
            hypothesis = (
                raw_content.replace("<USER_SUMMARY>", "")
                .replace("</USER_SUMMARY>", "")
                .replace("<DETAILED_HYPOTHESIS>", "")
                .replace("</DETAILED_HYPOTHESIS>", "")
                .strip()
            )

        need_human = "[NEED_HUMAN]" in raw_content
        print(
            f"  [Profiler] 探针探索完毕。发现模糊/歧义字段，是否需要人类确认: {need_human}"
        )
        print(f"  [Timer] profiler_node 耗时: {time.perf_counter() - start_time:.2f}s")

        return {
            "schema_hypothesis": hypothesis,
            "user_summary": user_summary,
            "requires_human_approval": need_human,
            "messages": [
                SystemMessage(content=f"<数据探针报告>\n{hypothesis}\n</数据探针报告>")
            ],
        }
    except Exception as e:
        print(f"  [Profiler] 探测失败，跳过认知层: {e}")
        print(f"  [Timer] profiler_node 耗时: {time.perf_counter() - start_time:.2f}s")
        return {"requires_human_approval": False}


def profiler_router(state: AgentState) -> Literal["human_node", "planner_node"]:
    """探针交警：根据是否有歧义，决定是否拦截图流转"""
    if state.get("requires_human_approval"):
        print("  [Router] 数据存在歧义！即将触发中断 (Interrupt)，等待人类介入...")
        return "human_node"
    return "planner_node"


# ======================================================================
# 节点 0.5：人在回路拦截器 (Human Node)
# ======================================================================
def human_node(state: AgentState) -> dict:
    """
    当图冻结被唤醒后执行此节点。
    此时 state["messages"] 已经包含了用户刚刚回复的确认指令。
    """
    start_time = time.perf_counter()
    old_hypothesis = state.get("schema_hypothesis", "")
    human_feedback = state["messages"][-1].content
    new_hypothesis = old_hypothesis + "\n[人类修正]:" + human_feedback

    print("  [HITL] 接收到人类的确认/纠偏指令，警报解除，放行！")
    print(f"  [Timer] human_node 耗时: {time.perf_counter() - start_time:.2f}s")
    return {"schema_hypothesis": new_hypothesis, "requires_human_approval": False}



# ======================================================================
# 节点 1：前台接待员 (Planner)
# ======================================================================
def planner_node(state: AgentState) -> dict:
    """意图规划器：用极低的成本判断用户到底想干嘛"""
    start_time=time.perf_counter()
    messages = state.get("messages", [])
    if not messages:
        print(f"  [Timer] planner_node 耗时: {time.perf_counter() - start_time:.2f}s")
        return {"messages": []}

    user_input = messages[-1].content

    prompt = f"""
    你是一个极其专业的数据分析系统意图规划员。你的任务是分析用户的输入，并将其归类为以下三个单词之一：
    
    - greeting: 简单问候（如“你好”、“哈罗”）、日常闲聊、询问你的身份或模型架构（如“你是谁”、“你是什么模型”、“你能做什么”）、或者是和数据分析完全无关的日常对话。
    - question: 用户针对**已经生成的分析报告、图表内容、编写的 Python 代码进行追问、解释或细节提问**（例如“解释一下第二条建议”、“为什么周末交易量低”、“刚才的代码是什么意思”、“刚才分析的平均值是多少”）。这类请求不需要重新生成新的图表或编写新的 Python 代码。
    - analysis: 用户明确提出了**新的数据处理、分析、绘图、计算指标、筛选过滤等硬活需求**，需要智能体**编写/生成新的 Python 代码并运行**（例如“帮我画一个折线图”、“统计各区域销售额并生成柱状图”、“清理空值并计算本月总利润”）。

    【分类示例】：
    - "你好，你能帮我干嘛？" -> greeting
    - "你是什么模型开发的？" -> greeting
    - "为什么周六的数据比周日低这么多？" -> question
    - "刚才的第一个建议，具体应该怎么优化？" -> question
    - "刚才画图的 Python 代码是什么原理？" -> question
    - "帮我重新统计下华东区域的销售额，并画图" -> analysis
    - "画一个各地区销售量对比饼图" -> analysis
    - "计算总利润" -> analysis

    【当前用户输入】："{user_input}"

    请严格只输出一个英文单词（"greeting"、"question" 或 "analysis"），不要有任何标点符号、Markdown 标记或解释废话。
    """

    response = flash_llm.invoke([HumanMessage(content=prompt)])
    intent = response.content.strip().lower()

    print(f"  [Planner] 侦测到用户意图: {intent}")
    print(f"  [Timer] planner_node 耗时: {time.perf_counter() - start_time:.2f}s")

    return {
        "messages": [SystemMessage(content=f"<内部路由标签>{intent}</内部路由标签>")]
    }


def intent_router(state: AgentState) -> Literal["analyzer_node", "coder_node"]:
    """根据 Planner 贴的标签，决定把任务分发给谁"""
    last_msg = state["messages"][-1].content

    if "greeting" in last_msg or "question" in last_msg:
        print("  [Router] 只是闲聊或针对历史提问，直接交由分析员回复。")
        return "analyzer_node"
    else:
        print("  [Router] 需要干硬活，叫程序员起来写代码！")
        return "coder_node"


# ======================================================================
# 节点 2：代码生成器 (Coder)
# ======================================================================
def coder_node(state: AgentState) -> dict:
    """代码生成器：根据用户需求和数据骨架，生成极其纯粹的 Python 代码"""
    start_time = time.perf_counter()
    print("  [Coder] 程序员已就位，准备编写分析代码...")

    file_path = state.get("active_file_path")
    if not file_path:
        print(f"  [Timer] coder_node 耗时: {time.perf_counter() - start_time:.2f}s")
        return {"messages": [AIMessage(content="对不起，您还没有上传任何数据文件。")]}

    try:
        df = pd.read_csv(file_path)
        columns = df.columns.tolist()
        head_str = df.head(3).to_markdown()
    except Exception as e:
        print(f"  [Timer] coder_node 耗时: {time.perf_counter() - start_time:.2f}s")
        return {"messages": [AIMessage(content=f"读取文件失败: {str(e)}")]}

    system_prompt = f"""
    # 角色: 资深数据科学家 & 首席 Python 工程师
    
    ## 背景与元数据
    - 目标数据集路径: `{file_path}`
    - 可用字段列名: {columns}
    - 数据样例 (前 3 行):
    {head_str}

    ## 任务目标
    生成一段完整、高质量、可直接在生产环境执行的 Python 脚本，以读取数据集，执行用户的数据分析请求，并在生成图表时将其保存为高分辨率的图片。

    ## 技术执行规范
    1. **数据操作**:
       - 必须且仅使用 Pandas (`import pandas as pd`) 来加载和处理目标数据集。
       - 处理时间序列时：如果用户请求了按天/月/年等时间维度的分析，必须先使用 `pd.to_datetime` 对时间/日期字段进行转换。
       - 处理缺失值：必须安全地处理可能存在的缺失值 (NaN)，使用 `.fillna()` 填充（例如填 0）、`.dropna()` 丢弃，或选择合适的聚合边界。
    2. **数据可视化标准 (如果涉及绘制图表)**:
       - 所有生成的图表图片必须保存到 `./data/outputs/` 目录下。为了防止覆盖历史对话中的图表，文件名必须是唯一的，必须导入 `uuid` 模块，并保存为类似 `f"./data/outputs/chart_{{uuid.uuid4().hex[:8]}}.png"` 的随机命名。
       - 为了避免资源浪费和排版混乱，除非用户明确要求，否则只生成**一张**最核心、最能直观回答用户问题的图表。
       - 使用 Matplotlib 和 Seaborn 绘图。必须配置如下中文防乱码与审美风格：
         ```python
         import matplotlib.pyplot as plt
         import seaborn as sns
         import uuid
         plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei'] # 保证 Windows/Linux 下中文正常显示
         plt.rcParams['axes.unicode_minus'] = False  # 保证负号正常显示
         plt.figure(figsize=(10, 6), dpi=150)       # 高清分辨率与默认黄金比例
         sns.set_theme(style="whitegrid", font="SimHei")
         ```
       - 图表必须包含清晰的标题 (`plt.title()`)、X轴与Y轴标签 (`plt.xlabel()`, `plt.ylabel()`)，并且在 `plt.savefig()` 前调用 `plt.tight_layout()` 以防止图表边缘截断。
       - 绘图完毕后必须调用 `plt.close()` 释放内存。
    3. **输出格式限制 (极其重要)**:
       - 只能输出纯粹、有效的 Python 代码本身。
       - **严禁**将输出包裹在 markdown 代码块（如 ```python ... ```）中。
       - **严禁**在代码前后输出任何解释性文字、引导语或问候废话。输出 must and only 直接以 `import` 语句作为开头。
    """

    messages_to_send = [SystemMessage(content=system_prompt)] + state["messages"]
    response = core_llm.invoke(messages_to_send)

    generated_code = response.content.strip()

    if generated_code.startswith("```python"):
        generated_code = generated_code[9:-3].strip()

    print("  [Coder] 代码生成完毕，已写入黑板，等待沙箱执行！")
    print(f"  [Timer] coder_node 耗时: {time.perf_counter() - start_time:.2f}s")

    return {
        "generated_code": generated_code,
        "dataframe_columns": columns,
    }


# ======================================================================
# 节点 3：沙箱执行员 (Executor)
# ======================================================================
def executor_node(state: AgentState) -> dict:
    """执行沙箱节点：把大模型写的代码放进 AST 隔离舱里跑"""
    start_time = time.perf_counter()
    print("  [Executor] 拿到代码，准备送入 AST 安全沙箱执行...")

    code = state.get("generated_code", "")
    error_count = state.get("error_count", 0)

    if not code:
        print(f"  [Timer] executor_node 耗时: {time.perf_counter() - start_time:.2f}s")
        return {
            "execution_error": "没有检测到生成的代码",
            "error_count": error_count + 1,
        }

    result = run_in_sandbox(code)

    if result["success"]:
        print("  [Executor]  代码执行成功！")
        new_files = result.get("new_files", [])
        image_paths = [
            f
            for f in new_files
            if f.lower().endswith((".png", ".jpg", ".jpeg", ".gif"))
        ]
        image_tags = []
        if image_paths:
            for img_path in image_paths:
                image_tags.append(f"![Generated Chart]({img_path})")
            print(f"  [Executor] 已捕获生成的新图片: {', '.join(image_paths)}")

        print(f"  [Timer] executor_node 耗时: {time.perf_counter() - start_time:.2f}s")
        return {
            "execution_error": "",
            "error_count": 0,
            "messages": [
                SystemMessage(
                    content=f"<沙箱执行成功>\n控制台输出:\n{result['output']}\n</沙箱执行成功>"
                )
            ]
            + [AIMessage(content=tag) for tag in image_tags],
        }
    else:
        print(f"  [Executor]  沙箱拦截或代码报错 (当前第 {error_count + 1} 次失败)")
        print(f"  [Timer] executor_node 耗时: {time.perf_counter() - start_time:.2f}s")
        return {
            "execution_error": result["error"],
            "error_count": error_count + 1,
            "messages": [
                SystemMessage(
                    content=f"<沙箱执行失败>\n报错信息:\n{result['error']}\n请仔细检查列名或语法，修改代码并重试！\n</沙箱执行失败>"
                )
            ],
        }



def error_router(state: AgentState) -> Literal["coder_node", "analyzer_node"]:
    """纠错红绿灯：决定是打回重做，还是继续往下走"""
    error = state.get("execution_error", "")

    if error:
        if state.get("error_count", 0) < 3:
            print("  [Router] 发现报错！大模型正在自我纠错 (Reflexion)，打回给程序员！")
            return "coder_node"
        else:
            print("  [Router] 连续报错 3 次！触发熔断机制，强行进入总结节点。")
            return "analyzer_node"
    else:
        print("  [Router] 代码完美运行，进入最终分析节点！")
        return "analyzer_node"


# ======================================================================
# 节点 4：智能分析总结员 (Analyzer)
# ======================================================================
def analyzer_node(state: AgentState) -> dict:
    """智能分析总结：拿着沙箱跑出来的数据，给老板写汇报，或直接答疑解惑"""
    start_time = time.perf_counter()
    print("  [Analyzer] 分析员就位，正在准备撰写报告或答疑解惑...")

    now_str = datetime.datetime.now().strftime("%Y-%m-%d %A")
    error = state.get("execution_error", "")
    error_count = state.get("error_count", 0)
    generated_code = state.get("generated_code", "")
    dataframe_columns = state.get("dataframe_columns", [])

    # 从历史消息中查找最新的内部路由标签，决定回复口吻
    intent = "analysis"  # 默认值
    for msg in reversed(state.get("messages", [])):
        if isinstance(msg, SystemMessage) and "<内部路由标签>" in str(msg.content):
            content_str = str(msg.content)
            if "greeting" in content_str:
                intent = "greeting"
            elif "question" in content_str:
                intent = "question"
            break

    if error and error_count >= 3:
        system_prompt = f"""
     你是一个资深 AI Agent 调试工程师。
    当前数据分析代码已连续执行失败 {error_count} 次，请生成一份面向开发者和用户都能理解的调试报告。

    ## 当前上下文
    - 可用字段列表:
    {dataframe_columns}

    - 最后一次报错信息:
    {error}

    - 最后一次生成的代码:
    {generated_code}

    ## 报告必须包含
    1. 失败原因概述：用通俗中文说明为什么任务没有完成。
    2. 关键报错信息：提取最关键的错误，不要粘贴冗长堆栈。
    3. 字段匹配分析：结合可用字段列表，判断是否可能是字段名写错、日期字段格式错误、缺失值处理不当等问题。
    4. 下一步建议：告诉用户可以如何修改问题、确认字段、或重新上传数据。

    ## 注意
    - 可以引用必要的代码片段，但不要整段复述代码。
    - 不要假装任务成功。
    - 不要输出业务分析结论。
    - 如果问题很可能来自字段名不匹配，请明确指出“用户问题中的字段”和“数据集中真实字段”可能不一致。
    """
    elif intent in ["greeting", "question"]:
        system_prompt = f"""
    # 角色: 首席商业智能总监 & 首席数据分析师
    
    ## 任务目标
    当前用户提出了一个关于历史已生成数据分析结论、代码或闲聊追问的问题。请结合当前的数据上下文（包括之前编写的代码、沙箱控制台输出及已生成的报告内容），以专业、客观、耐心的口吻直接解答用户的追问。
    
    ## 回答规范
    1. **直奔主题**：不要撰写包含“核心摘要”、“指标与发现”、“建议措施”等格式的完整商业分析报告模板。直接回答用户的问题本身。
    2. **结合上下文**：充分运用历史对话中的数据百分比、趋势、分析指标与业务语义进行解答。
    3. **简洁明了**：重点突出，不要重复展示复杂的 Python 代码细节，除非用户明确要求解释代码。
    """
    else:
        system_prompt = f"""
    # 角色: 首席商业智能总监 & 首席数据分析师
    
    ## 背景与元数据
    - 当前系统时间: {now_str} (在处理任何时间敏感的问题，如“今天”、“昨天”、“本月”时，请参考此时间)。
    
    ## 任务目标
    结合 Python 沙箱执行的输出结果（包括控制台输出的统计数据），撰写一份面向管理层的高级商业智能报告。报告必须专业、精炼，且聚焦于商业决策价值。

    ## 报告撰写规范
    1. **报告结构**:
       - **核心摘要 (Executive Summary)**: 用 1-2 句话高度概括最核心 of 商业洞察。
       - **核心指标与发现 (Core Metrics & Findings)**: 使用列表展示关键计算结果、趋势变化、异常数据及核心发现。
       - **建议措施 (Actionable Recommendations)**: 结合数据发现，提出 3-4 条具有可操作性的业务或技术建议。
    2. **语言与语气**: 必须使用客观、专业、由数据驱动的商业报告口吻，使用具体的数据百分比和趋势进行量化描述。
    3. **特殊规则限制**:
       - 严禁重复展示 Python 代码细节或冗长的调试堆栈日志。
       - 严格聚焦于业务语义、投资回报率 (ROI)、增长率及数据趋势。
       - 如果沙箱执行中成功生成了图表，必须在报告结尾以友好的口吻显式提醒用户查看下方生成的图表。
    """

    messages_to_send = [SystemMessage(content=system_prompt)] + state["messages"]
    response = core_llm.invoke(messages_to_send, config={"tags": ["final_analyzer"]})

    print("  [Analyzer] 报告撰写与解答完毕！")
    print(f"  [Timer] analyzer_node 耗时: {time.perf_counter() - start_time:.2f}s")

    return {"messages": [response]}


# ======================================================================
# 节点 5：垃圾数据清洗员 (Cleaner)
# ======================================================================
def cleaner_node(state: AgentState) -> dict:
    """垃圾清理：清除黑板上多余 of 系统内部调试/报错调试消息"""
    start_time = time.perf_counter()
    messages_to_remove = []
    for msg in state.get("messages", []):
        if isinstance(msg, SystemMessage):
            content_str = str(msg.content)
            if (
                "<内部路由标签>" in content_str
                or "<沙箱执行失败>" in content_str
                or "<沙箱执行成功>" in content_str
            ):
                if msg.id:
                    messages_to_remove.append(RemoveMessage(id=msg.id))

    if messages_to_remove:
        print(
            f"  [Cleaner] 垃圾车已启动，共清理了 {len(messages_to_remove)} 条内部调试垃圾记录！"
        )

    print(f"  [Timer] cleaner_node 耗时: {time.perf_counter() - start_time:.2f}s")
    return {"messages": messages_to_remove}



# ======================================================================
# 6. 终极图装配 (Graph Assembly)
# ======================================================================
def build_graph():
    """将所有节点和路由函数组装成完整的有向状态图"""
    print(" 正在拼装 DataViz Agent 核心状态机 (带 HITL 安全阀)...")

    builder = StateGraph(AgentState)

    # 1. 注册所有节点
    builder.add_node("profiler_node", profiler_node)
    builder.add_node("human_node", human_node)
    builder.add_node("planner_node", planner_node)
    builder.add_node("coder_node", coder_node)
    builder.add_node("executor_node", executor_node)
    builder.add_node("analyzer_node", analyzer_node)
    builder.add_node("cleaner_node", cleaner_node)

    # 2. 构筑连接边关系
    builder.add_edge(START, "profiler_node")

    builder.add_conditional_edges(
        "profiler_node",
        profiler_router,
        {"human_node": "human_node", "planner_node": "planner_node"},
    )

    builder.add_edge("human_node", "planner_node")

    builder.add_conditional_edges(
        "planner_node",
        intent_router,
        {"analyzer_node": "analyzer_node", "coder_node": "coder_node"},
    )

    builder.add_edge("coder_node", "executor_node")

    builder.add_conditional_edges(
        "executor_node",
        error_router,
        {"coder_node": "coder_node", "analyzer_node": "analyzer_node"},
    )

    builder.add_edge("analyzer_node", "cleaner_node")
    builder.add_edge("cleaner_node", END)

    # 3. 实例化存盘点并编译生效
    memory = get_checkpointer()
    app = builder.compile(checkpointer=memory, interrupt_before=["human_node"])
    print(" V2 高阶状态机拼装完成！随时准备接收请求！")
    return app


_agent_app = None
_agent_lock = threading.Lock()


def get_agent_app():
    """延迟获取 agent_app，保证实例化的所有组件（如 AsyncPostgresSaver）都在同一个 asyncio event loop 内"""
    global _agent_app
    if _agent_app is None:
        with _agent_lock:
            if _agent_app is None:
                _agent_app = build_graph()
    return _agent_app
