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

### 5. 状态持久化与流式日志

项目使用 PostgreSQL Checkpointer 持久化 LangGraph 状态，支持基于 `thread_id` 恢复历史会话和已上传文件路径，解决多轮追问时状态丢失的问题。

后端通过 SSE 输出多类事件：

- `token`：最终回答内容和图表 Markdown。
- `status`：当前执行节点提示。
- `trace`：节点开始、结束和耗时信息。

前端使用 Streamlit 展示聊天内容、生成图表、历史会话和执行过程折叠面板，便于观察 Agent 的运行路径。

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

## 🛠️ 技术栈与主要依赖

- **状态编排**: LangGraph (`langgraph`) - 用于流式状态节点编排及人在回路设计
- **大模型框架**: LangChain (`langchain-core`, `langchain-openai`)
- **API 后端**: FastAPI, Uvicorn, Pydantic
- **前端展示**: Streamlit (提供 Claude 质感的简约设计风格)
- **底层数据库**: PostgreSQL (`psycopg-pool`, `psycopg`)
- **数据分析**: Pandas, Matplotlib, Seaborn, Tabulate
