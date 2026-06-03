import os
import sys

# 解决 Windows 终端中文乱码问题
sys.stdout.reconfigure(encoding='utf-8')

from langchain_core.messages import HumanMessage
from core.agent import get_agent_app

agent_app = get_agent_app()

# 确保输出目录存在
os.makedirs("./data/outputs", exist_ok=True)
csv_path = "./data/uploads/test.csv"

# 【绝命毒师：故意挖坑】
# 我们的 CSV 里面的列名明明叫“区域”。
# 但是我作为用户，故意胡说八道让它按“销售大区”分组画图，或者说一些模糊的指示。
# 我们来看看：大模型第一次生成代码肯定会报 KeyError，
# 然后它能不能被沙箱打回，自己看着报错反思，最终改对代码画出图来！
question = "帮我分析一下这份数据。画一个每个【销售大区】的总销售额柱状图，把图表存到 ./data/outputs/ 目录下。"

print("=" * 60)
print(f"👤 刁钻的用户提问: {question}")
print("=" * 60)

initial_state = {
    "messages": [HumanMessage(content=question)],
    "active_file_path": csv_path,
    "error_count": 0
}

# 💡 关键修改：告诉 Agent 我们的“存档卡槽号”是 1号
config = {"configurable": {"thread_id": "user_001"}}

print("\n▶️ [第一回合] 开始执行初始任务...")
# 第一次流式调用，传初始状态和 config
for step in agent_app.stream(initial_state, config=config, stream_mode="updates"):
    for node_name, node_output in step.items():
        if "messages" in node_output and node_output["messages"]:
             print(f"[{node_name}]: {node_output['messages'][-1].content[:150]}...")

print("\n" + "=" * 60)
print("👤 追问: 请把我刚才生成的那个柱状图，改成红色的柱子，再存一份新的。")
print("=" * 60)

# 💡 关键验证：第二次调用！
# 注意：这次我们不传 initial_state（不传历史消息，也不传 CSV 路径），只传一句新话和相同的 thread_id
# 看看 Agent 能不能自动从 Checkpointer 里把刚才的 State 读出来！
follow_up_state = {
    "messages": [HumanMessage(content="请把我刚才生成的那个柱状图，改成红色的柱子，再存一份新的，叫 red_bar.png。")]
}

print("\n▶️ [第二回合] 开始执行追问任务...")
for step in agent_app.stream(follow_up_state, config=config, stream_mode="updates"):
    for node_name, node_output in step.items():
        if "generated_code" in node_output:
             print("💻 [二次生成的代码]: \n")
             print(node_output["generated_code"])
        if "messages" in node_output and node_output["messages"]:
             print(f"[{node_name}]: {node_output['messages'][-1].content[:150]}...")

print("\n🎉 测试结束！请去看看 ./data/outputs/ 目录下，是不是多了一张红色的柱状图？")
