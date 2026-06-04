import os
import sys
import asyncio
from langchain_core.messages import HumanMessage
from core.agent import get_agent_app

sys.stdout.reconfigure(encoding='utf-8')

agent_app = get_agent_app()
config = {"configurable": {"thread_id": "test_followup_001"}}

async def main():
    # 第一轮：正常分析数据
    question1 = "帮我分析一下数据，画出销售趋势图。"
    print("=" * 60)
    print(f"👤 轮次 1 提问: {question1}")
    print("=" * 60)

    initial_state = {
        "messages": [HumanMessage(content=question1)],
        "active_file_path": "./data/uploads/test.csv",
        "error_count": 0
    }

    async for step in agent_app.astream(initial_state, config=config, stream_mode="updates"):
        for node_name, node_output in step.items():
            if "messages" in node_output and node_output["messages"]:
                print(f"[{node_name}]: {node_output['messages'][-1].content[:100]}...")

    # 第二轮：进行追问（这应该被归类为 question 意图，直接走 analyzer，不写代码也不画图）
    question2 = "为什么华东区域业绩最好？请基于刚才的报告给我几个可能的解释。"
    print("\n" + "=" * 60)
    print(f"👤 轮次 2 追问: {question2}")
    print("=" * 60)

    follow_up_state = {
        "messages": [HumanMessage(content=question2)]
    }

    async for step in agent_app.astream(follow_up_state, config=config, stream_mode="updates"):
        for node_name, node_output in step.items():
            if "generated_code" in node_output:
                print("❌ 警告：不应该执行 Coder 节点！")
            if "messages" in node_output and node_output["messages"]:
                print(f"[{node_name}]: {node_output['messages'][-1].content[:200]}...")

    print("\n🎉 测试完成！")

if __name__ == "__main__":
    asyncio.run(main())
