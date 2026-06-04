# 🚀 性能优化第二阶段实施方案：探针异步降级与 Coder 字段对齐优化

为了进一步攻克 110 秒的极高耗时瓶颈，本阶段将实施以下两个深度的优化举措：

1. **探针节点（`profiler_node`）异步化与分流降级**：
   - 将 `profiler_node` 从 `def` 重构为 `async def`。
   - 探针节点的任务是生成字段质量报告与基本的数据概要，这些工作同样不需要动用旗舰级 `core_llm`，我们将底层调用降级为极速、低成本的 `flash_llm` (`glm-4-flash`) 并使用 `await ainvoke`，预期可将该节点的耗时由 **27秒直接压缩至 2~3秒**。

2. **打通“探针-程序员”信息链，提高代码一次生成成功率**：
   - 目前 `coder_node` 在生成 Python 代码时，只接收了原始列名与前 3 行数据，但**完全没有参考探针生成的 schema 假设**，导致第一次生成时总是因找不到“销售大区”等用户口吻的列名而报 `KeyError` 从而触发了额外的报错重试。
   - 解决方案：将 `schema_hypothesis`（探针做出的字段语义映射与人类纠正假设）直接注入 `coder_node` 的 System Prompt 中，强约束 Coder 必须参考该假设映射真实字段。这能够**极大地提高代码一次性生成成功率，消灭长达 25+ 秒的自我纠错（Reflexion）重试过程**。

---

## 🛠️ 拟修改文件

### 1. `core/agent.py`
#### [MODIFY] [agent.py](file:///d:/Rag/DataViz_Agent/core/agent.py)
* **`profiler_node`**：
  - 重构为 `async def profiler_node(state: AgentState) -> dict:`。
  - 将大模型调用修改为 `await flash_llm.ainvoke(...)`，实现该节点的并发非阻塞及模型分流降级。
* **`coder_node`**：
  - 在参数提取中获取 `schema_hypothesis = state.get("schema_hypothesis", "暂无元数据分析假设。")`。
  - 在 `system_prompt` 中加入 `- 数据探针分析假设与字段语义映射: {schema_hypothesis}`。
  - 并在技术执行规范中增加约束，要求 Coder 编写代码时必须严格根据探针语义映射将用户提问字段翻译为数据集真实字段名。

---

## 🧪 验证计划

1. **本地脚本验证**：
   - 运行 `test_agent.py` 验证在故意设坎（“销售大区”列名不直接匹配）的情况下，Coder 能否在第一轮中直接写对代码。
   - 观察控制台中 `profiler_node` 和 `coder_node` 的耗时是否分别降至毫秒级/秒级，且不再触发第二轮自我纠错。
2. **网页端再次确认**：
   - 启动系统在网页端进行完整分析测试，确认端到端响应时间大幅缩短。
