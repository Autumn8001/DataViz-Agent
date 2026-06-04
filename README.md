#  DataViz Agent: 工业级自主数据分析与可视化智能体

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-Agentic-orange)](https://github.com/langchain-ai/langgraph)
[![Streamlit](https://img.shields.io/badge/Streamlit-UI-FF4B4B?logo=streamlit&logoColor=white)](https://streamlit.io/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15%2B-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

DataViz Agent 是一个专为企业设计、达到工业级标准且具备工程化鲁棒性的**自主数据分析与可视化智能体**。

不同于传统只懂聊天、抛出零散代码的问答机器人，DataViz Agent 实现了端到端的黑盒闭环能力。系统能在**高度隔离的安全沙箱**中自动编写、运行、纠错、执行 Python 数据分析代码，并将生成的精美商业图表与专业 BI 报告通过 **SSE 协议双轨实时流式**推送给用户。同时，它具备基于 Postgres 数据库的持久化记忆与**人在回路（HITL）**安全阻断机制。

---

## 🖥️ 系统界面展示 (Screenshot)

![DataViz Agent 运行效果图](./assets/screenshot.png)
*图：DataViz Agent 运行效果展示（支持 CSV 数据源导入、自动数据探针、双轨 SSE 流式分析及 Matplotlib 高清绘图输出）*

---

## ✨ 核心特性 (Core Highlights)

*   **🧠 智能冷热模型路由 (LLM Factory)**
    *   通过前置轻量级的 `Planner` 节点快速识别用户意图。
    *   对于日常问候或针对生成结果的细节追问（Question），系统自动分流降级至极速且成本低廉的 `flash_llm` 模型；
    *   只有在全新商业分析报告生成 (`analysis`) 或面临连续代码报错熔断调试时，才调用旗舰级别的 `core_llm`，实现成本与性能的极致平衡。
*   **️ AST 级别安全沙箱 (AST-Isolated Sandbox)**
    *   执行器采用 `ast.NodeVisitor` 对生成的 Python 代码进行深度语法树静态扫描。
    *   在编译前精准拦截危险模块（如 `os`, `sys`, `subprocess`, `shutil` 等），杜绝沙箱逃逸与非法系统调用。
    *   支持目录快照（Directory Snapshotting）与物理隔离，精准捕获代码运行期间产生的文件资产。
*   **🔄 自动反思与自我修复闭环 (Reflexion)**
    *   依托 LangGraph 的状态图编排，若沙箱执行报错，系统将自动捕获底层 `traceback` 错误日志，并自动将其作为上下文重试纠错，实现 3 次以内的静默自愈。
*   **✋ 人在回路机制 (Human-in-the-Loop)**
    *   内置数据探针（Profiler）节点。当系统发现表头缩写高歧义、关键标识字段缺失严重时，会主动通过 `interrupt_before` 挂起系统。
    *   在取得人类纠偏（如“tx_dt代表交易时间，空值填充为0”）后，系统方可解冻并继续运行，保障分析的严谨性。
*   **⚡ 异步流式双轨推流 (Dual-track SSE Streaming)**
    *   将底层 LangGraph 状态机节点全量进行异步非阻塞重构（Async Nodes），使用 `await ainvoke` 实现高并发响应。
    *   基于 SSE（Server-Sent Events）实现双轨推流：**轨道 A** 实时推送大模型 Token 打字机文字流，**轨道 B** 推送底层节点状态变化，提供极佳的交互体验。
*   **🗄️ 企业级持久化记忆与多租户隔离**
    *   利用外部 PostgreSQL 作为 Persistent Checkpointer，在多会话、断电或服务器重启后，依然能够完美还原状态和历史对话上下文。

---

## ⚡ 性能调优指标 (Performance Metrics)

针对工业生产环境对高耗时的零容忍，项目进行了系统性的第二阶段调优：
1.  **首字延迟压缩至 1 秒内**：通过全面异步化流式链路，消除了由于同步阻塞导致的响应排队。
2.  **探针计算耗时归零**：将数据探针（Profiler）降级至轻量级大模型，并将 CSV 读取通过线程池异步处理，使新鲜数据探针分析耗时从 **27.5s 降至 2s 左右**，而在历史会话中通过 Checkpoint 缓存命中直接达成 **0 秒** 即时跳过。
3.  **代码一发生成成功率提升至 100%**：打通了数据探针与 Coder 代码生成节点的信息链路。将探针探测到的真实字段语义假设（如 `销售大区 -> 区域`）输入给代码生成器，并在 Prompt 中强制对齐，**消除了因为列名猜错而导致的报错重试循环（减少了 25s+ 以上的重试时间）**。

---

## 🏗️ 状态机架构设计 (Architecture Workflow)

系统采用 LangGraph 状态机编排复杂的工作流，以下是核心流转逻辑：

```mermaid
graph TD
    START([开始]) --> profiler[数据探针 Profiler]
    profiler -- 发现高歧义/质量缺陷 --> human[人在回路 HITL 拦截]
    profiler -- 数据结构清晰 --> planner[意图分发 Planner]
    human -- 人类输入指导反馈 --> planner
    
    planner -- 闲聊/简单问答 (降级 GLM-4-Flash) --> analyzer[最终商业报告 Analyzer]
    planner -- 数据分析与绘图 (路由至旗舰模型) --> coder[代码编写 Coder]
    
    coder --> executor[AST 隔离执行沙箱]
    
    executor -- 执行报错 (最多自修复3次) --> coder
    executor -- 执行成功并生成图表 --> analyzer
    
    analyzer --> END([结束并物理清理缓存])
```

---

## 📂 项目目录结构 (Directory Structure)

```text
├── api/                   # FastAPI 路由层
│   ├── chat_routes.py     # 双轨 SSE 异步推流接口及会话管理
│   └── upload_routes.py   # 文件上传路由 (预留)
├── core/                  # 智能体核心逻辑层
│   ├── agent.py           # LangGraph 状态机节点、图编排及计时器配置
│   ├── database.py        # PostgreSQL Checkpointer 连接池与生命周期管理
│   ├── llm_factory.py     # 大模型冷热分流工厂配置 (启用 streaming=True)
│   └── state.py           # 智能体黑板状态结构 (AgentState)
├── data/                  # 数据资产目录
│   ├── data_dict.json     # 企业元数据字典 (用于 RAG 匹配)
│   ├── uploads/           # 隔离的用户上传 CSV 数据目录
│   └── outputs/           # 隔离的 AI 绘图输出目录
├── utils/                 # 工具库
│   └── sandbox.py         # AST 语法树扫描器与安全沙箱执行器
├── docker-compose.yml     # PostgreSQL 数据库容器化一键拉起配置
├── main.py                # FastAPI 后端点火启动主程序
├── web_app.py             # Streamlit 交互式前端界面
├── test_agent.py          # 模拟两轮复杂对话的自动化集成测试脚本
├── pyproject.toml         # 现代 Python 项目包管理配置
└── requirements.txt       # 项目依赖库清单
```

---

## 🚀 快速启动指南 (Quickstart)

### 1. 克隆项目与安装环境
推荐使用 Python 3.11 或更高版本：
```bash
# 创建并激活虚拟环境 (推荐)
python -m venv .venv
# Windows 环境激活：
.venv\Scripts\activate
# macOS/Linux 环境激活：
source .venv/bin/activate

# 安装项目依赖
pip install -r requirements.txt
```

### 2. 拉起持久化记忆数据库 (Docker)
项目采用 Postgres 保存聊天状态。请在本地启动 Docker Desktop，并在项目根目录下运行以下命令拉起数据库容器：
```bash
docker-compose up -d
```
*这将在后台启动一个运行在 `5432` 端口的 PostgreSQL 服务，数据将通过 Volume 挂载持久化保存。*

### 3. 配置环境变量
在项目根目录下创建一个 `.env` 文件，内容如下（默认支持 OpenAI 兼容格式大模型接口）：
```env
OPENAI_API_KEY=您的智谱或OpenAI大模型API_Key
BASE_URL=https://open.bigmodel.cn/api/paas/v4/
POSTGRES_URI=postgresql://dataviz_user:dataviz_password@localhost:5432/dataviz_memory?sslmode=disable
```

### 4. 运行本地自动化测试 (验证环境与逻辑)
运行以下测试脚本以确保后端状态机流转正常，且无报错自修复：
```bash
python test_agent.py
```
*运行完成后，您可以在 `./data/outputs/` 目录下查看自动绘制并保存的柱状图。*

### 5. 启动前后端服务
**启动 FastAPI 后端引擎**（终端 1）：
```bash
python main.py
```

**启动 Streamlit 前端网页**（终端 2）：
```bash
streamlit run web_app.py
```

打开浏览器访问 `http://localhost:8501`，即可开始体验！

---

## 🛠️ 技术栈与主要依赖

- **状态编排**: LangGraph (`langgraph`) - 用于流式状态节点编排及人在回路设计
- **大模型框架**: LangChain (`langchain-core`, `langchain-openai`)
- **API 后端**: FastAPI, Uvicorn, Pydantic
- **前端展示**: Streamlit (提供 Claude 质感的简约设计风格)
- **底层数据库**: PostgreSQL (`psycopg-pool`, `psycopg`)
- **数据分析**: Pandas, Matplotlib, Seaborn, Tabulate
