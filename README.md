<h1 align="center">DataViz Agent 智能数据分析与可视化助手</h1>

<p align="center">
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.11%2B-blue?logo=python&logoColor=white" alt="Python 3.11+"></a>
  <a href="https://fastapi.tiangolo.com/"><img src="https://img.shields.io/badge/FastAPI-0.100%2B-009688?logo=fastapi&logoColor=white" alt="FastAPI"></a>
  <a href="https://github.com/langchain-ai/langgraph"><img src="https://img.shields.io/badge/LangGraph-Agentic-orange" alt="LangGraph"></a>
  <a href="https://streamlit.io/"><img src="https://img.shields.io/badge/Streamlit-UI-FF4B4B?logo=streamlit&logoColor=white" alt="Streamlit"></a>
  <a href="https://www.postgresql.org/"><img src="https://img.shields.io/badge/PostgreSQL-15%2B-4169E1?logo=postgresql&logoColor=white" alt="PostgreSQL"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-green" alt="License"></a>
</p>

DataViz Agent 是一个基于 **FastAPI + LangGraph + Pandas + PostgreSQL Checkpointer + Streamlit** 构建的数据分析 Agent，支持用户上传 CSV/Excel 后进行数据探针、意图识别、轻量工具调用、代码生成、AST 沙箱执行、错误重试、图表回传和流式日志展示。

这个项目的重点不是替代专业 BI 平台，而是探索“LLM + 工具调用 + 状态机编排”在数据分析场景中的工程化落地。

---

## 🖥️ 系统界面展示 (Screenshot)

![DataViz Agent 运行效果图](./assets/screenshot.png)

---

## 核心能力

### 1. LangGraph 状态机编排

系统将一次数据分析任务拆分为多个可控节点：

```mermaid
graph TD
    START([开始]) --> profiler[数据探针 Profiler]
    profiler --> router{是否需要人工确认}
    router -->|需要| human[人在回路 HITL]
    router -->|不需要| planner[意图识别 Planner]
    human --> planner
    planner -->|字段/缺失/预览| quick[Quick Tool]
    planner -->|绘图/计算/分析| coder[代码生成 Coder]
    planner -->|闲聊/追问| analyzer[结果总结 Analyzer]
    quick --> analyzer
    coder --> executor[AST 沙箱执行 Executor]
    executor -->|失败且未超过3次| coder
    executor -->|成功或熔断| analyzer
    analyzer --> cleaner[清理内部消息]
    cleaner --> END([结束])
```

通过节点拆分，模型不再“一步到位”直接回答，而是按数据探针、规划、执行、总结的流程逐步推进，便于调试和定位问题。

### 2. 数据探针与上下文压缩

上传数据后，`profiler_node` 会读取文件结构，提取字段名、数据类型、缺失值、样例数据，并结合本地数据字典生成 `schema_hypothesis`。后续代码生成节点主要读取这些结构化信息，而不是直接把整张表塞给模型，从而减少 token 消耗和幻觉风险。

当探针发现字段歧义、关键列缺失率较高等情况时，系统会触发人在回路，等待用户补充说明后再继续执行。

### 3. Quick Tool 轻量工具路径

对于“有哪些字段”“缺失值情况”“看前几行”这类确定性请求，系统会路由到 `quick_tool_node`，直接调用 Pandas 工具函数返回结果，避免简单任务进入代码生成和沙箱执行链路。

目前内置工具包括：

- `get_columns`：查看字段列表。
- `get_missing_summary`：统计缺失值。
- `preview_rows`：预览前几行数据。

### 4. 代码生成、沙箱执行与错误重试

对于绘图、统计、筛选、指标计算等复杂任务，系统由 `coder_node` 生成 Python 分析代码，再交给 `executor_node` 执行。执行失败时，错误信息会写回状态，最多触发 3 次重新生成，避免无限重试造成成本浪费。

沙箱执行前会通过 AST 静态扫描拦截高风险操作，例如：

- 禁止导入 `os`、`sys`、`subprocess`、`socket`、`requests` 等模块。
- 禁止调用 `eval`、`exec`、`open`、`__import__` 等高危函数。
- 禁止访问 `__subclasses__`、`__globals__`、`__builtins__` 等敏感属性。

需要说明的是：该沙箱用于学习项目和本地演示场景，能降低风险，但不能等价于生产级容器隔离或系统级安全沙箱。

### 5. SSO 会话持久化、防越权拦截与物理输出隔离

系统将 SSO Token 与 LangGraph 状态机、后端数据库及沙箱输出目录紧密联动，全面提升多用户场景下的安全性：

- **SSO 去中心化验签**：前端通过统一登录接口取得 JWT Token 后，Agent 后端利用共享密钥在本地对称解密，提取 `user_id` 和 `tenant_id`，实现无直连的单点登录。
- **Postgres 关系表硬校验 (agent_sessions)**：
  系统初始化时自动在数据库建立 `agent_sessions` 关系物理表，物理绑定 `thread_id` 与所有者 `user_id` 的专属拥有者关系。当用户访问、拉取会话历史（`/history/{id}`）或删除会话（`DELETE`）时，后端必须在关系表中进行强校验匹配，防止任何旁路越权。
- **物理路径双重隔离防穿越**：
  - **上传隔离**：用户上传的 CSV/Excel 文件物理存储于 `data/uploads/{user_id}/`，且后端在校验文件请求时，使用 `Path(file_path).resolve().is_relative_to(user_uploads_dir)` 精准校验其必须落在当前用户的隔离子目录下，杜绝 `../` 目录穿越攻击。
  - **图表输出隔离**：Matplotlib/Seaborn 渲染的所有图片及代码运行结果，动态输出到 `./data/outputs/{user_id}/` 隔离子目录。
  - **递归沙箱图表捕获**：沙箱捕获新生成文件的快照机制升级为基于 `os.walk` 递归深度扫描 outputs 文件夹，保证隔离子目录下的图表文件可以完美回传。
- **多轨流式响应**：基于 FastAPI SSE 双轨吐出执行状态（status）、沙箱运行步骤与耗时日志（trace）以及大模型回复 token，在 Streamlit 展开面板内流式流转。

### 6. 模型抽象与私有化部署预留

项目在工程设计上将大模型调用统一封装在 `core/llm_factory.py` 中，业务节点不直接依赖任何具体模型厂商。

- 默认使用 OpenAI-compatible 接口调用云端模型。
- 通过 `FLASH_MODEL` 和 `CORE_MODEL` 区分轻量模型与核心模型，分别用于意图路由和代码生成/分析总结。
- 如果企业内网模型服务兼容 OpenAI API，例如 vLLM、Ollama OpenAI-compatible API 或 Xinference，通常只需要调整 `BASE_URL`、`OPENAI_API_KEY`、`FLASH_MODEL` 和 `CORE_MODEL` 等环境变量，Agent 状态机、沙箱执行和前端展示链路无需重写。

---

## 技术栈

| 模块 | 技术 |
| :--- | :--- |
| 后端服务 | FastAPI, SSE |
| Agent 编排 | LangGraph, LangChain |
| 数据处理 | Pandas, OpenPyXL |
| 可视化 | Matplotlib, Seaborn |
| 状态持久化 | PostgreSQL, LangGraph Checkpointer |
| 前端 | Streamlit |
| 安全控制 | AST 静态扫描, 受限命名空间执行 |
| 依赖管理 | uv |

---

## 项目结构

```text
DataViz_Agent/
├── api/
│   ├── chat_routes.py      # SSE 对话接口、执行日志、历史会话
│   └── upload_routes.py    # CSV/Excel 上传接口
├── core/
│   ├── agent.py            # LangGraph 节点与状态机编排
│   ├── database.py         # PostgreSQL Checkpointer 连接
│   ├── llm_factory.py      # 模型工厂
│   ├── sandbox.py          # AST 安全扫描与代码执行
│   ├── state.py            # AgentState 状态定义
│   └── tools.py            # quick_tool 轻量数据工具
├── utils/
│   └── viz_theme.py        # Matplotlib/Seaborn 图表主题
├── data/
│   ├── uploads/            # 上传文件目录，Git 忽略
│   └── outputs/            # 图表输出目录，Git 忽略
├── docker-compose.yml      # PostgreSQL 本地开发环境
├── main.py                 # FastAPI 应用入口
├── web_app.py              # Streamlit 前端
└── pyproject.toml          # 项目依赖
```

---

## 快速启动

### 1. 安装依赖

```bash
uv sync
```

### 2. 配置环境变量

复制 `.env.example` 为 `.env`，并填写模型 API 与 PostgreSQL 地址：

```env
# 云端大模型 (支持 OpenAI 兼容格式，如智谱等)
OPENAI_API_KEY=your_llm_api_key_here
BASE_URL=https://open.bigmodel.cn/api/paas/v4/
FLASH_MODEL=glm-4-flash
CORE_MODEL=glm-4

# 私有化本地模型部署切换示例 (如 vLLM, Ollama, Xinference)
# OPENAI_API_KEY=local_dummy_key
# BASE_URL=http://localhost:8000/v1
# FLASH_MODEL=local-fast-model
# CORE_MODEL=local-reasoning-model

POSTGRES_URI=postgresql://dataviz_user:dataviz_password@localhost:5432/dataviz_memory?sslmode=disable
```

### 3. 启动 PostgreSQL

```bash
docker compose up -d
```

### 4. 启动服务

后端：

```bash
python main.py
```

前端：

```bash
streamlit run web_app.py
```

打开 `http://localhost:8501` 即可使用。

---

## 🛡️ 安全加固与越权测试审计

为了达到企业级准生产的安全性标准，本项目实施了六大纵深加固防线，能够抵御各类路径穿越、身份假冒与越权注入风险。

### 1. 六大防越权加固防线
- **用户名强格式正则**：注册用户名仅允许 `^[a-zA-Z0-9_-]{2,50}$`，杜绝通过特殊字符造成路径穿越或 SQL 注入。
- **上传物理 UUID 重命名**：物理落盘时剥离目录前缀，采用 `uuid.uuid4().hex` 作为物理文件名，防范恶意穿越覆盖系统敏感文件。
- **用户级历史强隔离**：聊天历史记录的拉取和删除在 SQL 层面绑定 `user_id` 过滤，消除同一租户不同用户对话历史串色风险。
- **屏蔽前端 history 传入**：彻底废除对前端请求体内历史聊天上下文的直接采用，全部由后端从 PostgreSQL 数据库提取，防御对话内容伪造。
- **会话关系物理表硬校验** (Agent 端)：在 Postgres 数据库建立 `agent_sessions` 关系表，每次对话、拉取及删除时均查表强校验归属。
- **文件绝对路径 resolve 校验** (Agent 端)：CSV 物理文件访问时，采用 `Path.resolve().is_relative_to` 精准校验隔离范围，杜绝 `../` 回退绕过。

### 2. 一键自动化集成测试
项目在仓库内置了一键自动化集成渗透测试脚本：`scripts/test_security.py`。该脚本可自动对上述漏洞防线发起模拟渗透攻击：
- **运行测试**：
  ```bash
  python scripts/test_security.py
  ```
- **越权测试机制**：
  1. 尝试以非法字符/路径符号注册用户，检验**格式校验器阻断率**；
  2. 尝试以上传包含 `../../` 的恶意文件，检验**上传文件物理名净化及重命名存盘**；
  3. 用户 B 尝试调用 API 强行获取用户 A 的 `session_id` 对话历史，检验**数据库用户级强隔离**；
  4. 用户 B 假冒用户 A 的 thread_id 前缀或跨越其 uploads 隔离目录（`../`）读取文件，检验 **Postgres 关系表拦截率** 与 **Path.resolve 路径隔离阻断率**。

---

## 适用场景与边界

适合场景：

- CSV/Excel 表格的快速探索、统计和可视化。
- 演示 LangGraph Agent 工作流、工具调用、人在回路和状态持久化。
- 学习 LLM 生成代码后的安全检查、执行回传和错误自修复。

当前边界：

- 沙箱是基于 AST 的静态拦截和受限执行，不等价于生产级容器隔离。
- 图表质量依赖模型生成代码和数据字段质量。
- 当前前端基于 Streamlit，适合演示和本地使用，不是完整商业 BI 前端。
