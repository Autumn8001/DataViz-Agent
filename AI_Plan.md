# 🚀 性能优化实施方案：冷热模型解耦、异步化与流式推流激活

为了解决回复延迟高、用户等待时间长的问题，本项目将针对性地实施以下三个维度的性能优化：

1. **激活底层流式传输**：在 `LLMFactory` 实例化大模型时开启 `streaming=True`，使前端能够真正感知到“打字机式”的流式输出，消除漫长的空白等待。
2. **轻量意图模型降级**：在 `analyzer_node` 中，如果用户意图为 `greeting`（闲聊问候）或 `question`（针对已有报告的追问），降级使用高速度、低成本的 `flash_llm`（`glm-4-flash`）进行响应；只有在需要输出复杂 BI 商业报告（`analysis`）或调试错误代码时，才调用旗舰级的 `core_llm`（`glm-4`）。
3. **节点函数全面异步化**：将状态机中的核心 LLM 调用节点（`planner_node`、`coder_node`、`analyzer_node`）全部重构为 `async def`，并将内部 LLM 调用方式升级为 `await ainvoke(...)`，释放 Python 线程池压力，提升高并发下的响应速度。

---

## 🛠️ 拟修改文件

### 1. `core/llm_factory.py`
#### [MODIFY] [llm_factory.py](file:///d:/Rag/DataViz_Agent/core/llm_factory.py)
* 在 `get_flash_model` 和 `get_core_model` 中均添加 `streaming=True` 实例化参数。

### 2. `core/agent.py`
#### [MODIFY] [agent.py](file:///d:/Rag/DataViz_Agent/core/agent.py)
* **`planner_node`**：重构为 `async def`，使用 `await flash_llm.ainvoke(...)`。
* **`coder_node`**：重构为 `async def`，使用 `await core_llm.ainvoke(...)`。
* **`analyzer_node`**：
  * 重构为 `async def`。
  * 根据追问意图（`intent`）进行模型分流：若意图为 `greeting` 或 `question`，使用 `response = await flash_llm.ainvoke(...)`；若为 `analysis` 或代码报错，则使用 `response = await core_llm.ainvoke(...)`。

---

## 🧪 验证计划

1. **测试脚本验证**：
   * 运行 `scratch/test_followup.py`，查看在第二轮追问时，`analyzer_node` 的耗时是否从之前的 ~7s 降至 2s 以内。
   * 运行 `test_agent.py` 确保整体逻辑和图流程依然 100% 正确。
2. **网页流式测试**：
   * 启动 Web 服务，在网页端输入需求，验证打字机流式效果是否被真正激活，且追问时的响应速度有显著提升。
