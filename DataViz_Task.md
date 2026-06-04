- `[x]` 1. 开启底层流式支持：修改 `core/llm_factory.py` 启用 `streaming=True`
- `[x]` 2. 重构大模型节点为异步节点：将 `planner_node`、`coder_node`、`analyzer_node` 改为 `async def` 并升级为 `await .ainvoke`
- `[x]` 3. 实现 `analyzer_node` 模型分流：在 `analyzer_node` 中实现轻量追问/闲聊意图降级调用 `flash_llm`
- `[x]` 4. 运行本地脚本 `test_agent.py` 与 `test_followup.py` 验证计时与功能正确性
- `[x]` 5. 手动测试运行 WebApp 确认页面流式传输正常

## 🚀 性能优化第二阶段：探针异步降级与 Coder 字段对齐优化

- `[x]` 6. 重构 `profiler_node` 为异步非阻塞节点，并将大模型调用降级为 `flash_llm.ainvoke`
- `[x]` 7. 优化 `coder_node`：从 `state` 中读取 `schema_hypothesis` 并注入其提示词，增加真实字段对齐映射约束
- `[x]` 8. 运行本地测试脚本 `test_agent.py` 验证能否一发成功（首轮生成成功，不再报错重试，且耗时降为数秒）
- `[x]` 9. 在网页端进行对话测试，观察系统响应速度的改善
