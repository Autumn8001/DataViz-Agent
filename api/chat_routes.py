from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import json
from langchain_core.messages import HumanMessage, AIMessage
from core.database import get_pool
from core.agent import get_agent_app

router = APIRouter()


# 严格校验前端传过来的数据格式
class ChatRequest(BaseModel):
    message: str
    file_path: str = ""  # 如果用户传了文件，这里就会有路径
    thread_id: str  # 💡 必须让前端传一个存档号过来，不然怎么找记忆？


@router.post("/chat")
async def chat_endpoint(request: ChatRequest):
    """接收前端对话请求，并返回 SSE 流式推流响应"""

    # 核心：造一个“源源不断的产水器”（异步生成器）
    async def event_generator():
        # 1. 组装初始黑板状态
        initial_state = {
            "messages": [HumanMessage(content=request.message)]}

        if request.file_path:
            initial_state["active_file_path"] = request.file_path

        # 组装记忆卡槽配置
        config = {"configurable": {"thread_id": request.thread_id}}

        try:
            # 动态获取已处于运行 asyncio 循环内的 agent_app 实例
            agent_app = get_agent_app()

            # 💡 核心修复：检查图是否在中断状态（比如卡在 human_node 之前）
            state = await agent_app.aget_state(config)
            if state.next:
                # 恢复执行：将当前用户的输入作为人类的指令，更新到 human_node 的输入中
                await agent_app.aupdate_state(
                    config, {"messages": [HumanMessage(content=request.message)]}
                )
                event_stream = agent_app.astream_events(
                    None, config=config, version="v2"
                )
                yield f"data: {json.dumps({'type': 'status', 'content': ' 人在回路反馈接收成功，正在恢复运行并修正分析策略...'})}\n\n"
            else:
                # 正常全新的运行
                event_stream = agent_app.astream_events(
                    initial_state, config=config, version="v2"
                )

            # 2. 启动全景监控摄像头 (astream_events)
            async for event in event_stream:
                event_type = event["event"]
                node_name = event.get("name", "")

                #  双轨推流之【轨道 A】：大模型正在疯狂吐字 (Token级推流)
                if event_type == "on_chat_model_stream":
                    # 只允许带有 "final_analyzer" 标签的模型输出，拦截掉 Coder 的 Python 代码（含有 # 注释），避免前端 UI 布局崩塌成巨大标题！
                    if "final_analyzer" in event.get("tags", []):
                        chunk = event["data"]["chunk"]
                        if chunk.content:
                            # 必须严格遵守 SSE 协议格式：以 data: 开头，以 \n\n 结尾！
                            yield f"data: {json.dumps({'type': 'token', 'content': chunk.content})}\n\n"

                #  双轨推流之【轨道 B】：节点状态流转 (给前端报信，显示绿灯)
                elif event_type == "on_chain_start":
                    # 如果系统进入了咱们定义的四大节点，立刻通知前端！
                    if node_name in [
                        "planner_node",
                        "coder_node",
                        "executor_node",
                        "analyzer_node",
                    ]:
                        yield f"data: {json.dumps({'type': 'status', 'content': f'⚙️ 系统正在执行节点: {node_name} ...'})}\n\n"

                #  隐藏轨道之【轨道 C】：拦截核心节点的关键产物（图片、代码）
                elif event_type == "on_chain_end":
                    # 1. 拦截沙箱生成的图片
                    if node_name == "executor_node":
                        from langchain_core.messages import AIMessage

                        output_dict = event["data"].get("output", {})
                        if isinstance(output_dict, dict) and "messages" in output_dict:
                            for msg in output_dict["messages"]:
                                # 如果找到了我们强行塞进去的图片暗号，伪装成 Token 强制推给前端！
                                if isinstance(msg, AIMessage) and "![" in str(
                                    msg.content
                                ):
                                    yield f"data: {json.dumps({'type': 'token', 'content': f'\n\n{msg.content}\n\n'})}\n\n"

                    elif node_name == "coder_node":
                        output_dict = event["data"].get("output", {})
                        if (
                            isinstance(output_dict, dict)
                            and "generated_code" in output_dict
                        ):
                            code = output_dict["generated_code"]
                            if code:
                                code_markdown = f"\n\n** 💻 AI 编写的分析代码 (点击展开查看)：**\n<details>\n<summary>点击展开/折叠查看 Python 分析代码</summary>\n\n```python\n{code}\n```\n</details>\n\n"
                                yield f"data: {json.dumps({'type': 'token', 'content': code_markdown})}\n\n"


                    # 3. 拦截数据探针生成的探针报告并分发给前端，让用户掌握数据底细
                    elif node_name == "profiler_node":
                        output_dict = event["data"].get("output", {})
                        if (
                            isinstance(output_dict, dict)
                            and "user_summary" in output_dict
                        ):
                            user_summary = output_dict["user_summary"]
                            if user_summary:
                                report_markdown = f"\n\n🔍 **【数据探针检测报告】**\n\n{user_summary}\n\n"
                                yield f"data: {json.dumps({'type': 'token', 'content': report_markdown})}\n\n"

            # 💡 运行结束后，再次检查是否卡在 human_node 之前（即被中断了）
            final_state = await agent_app.aget_state(config)
            if final_state.next and "human_node" in final_state.next:
                # 作为一个特殊的消息 Token 发送给前端，从而永久保留在聊天记录中！
                interrupt_msg = "\n\n️ **[人在回路中断拦截]**\n数据探针检测到数据中存在模糊字段或大面积缺失。系统已自动挂起拦截。\n👉 **请在下方输入框中提供指导纠偏指令（如：指定某列是日期列，或者如何处理缺失值），然后发送。系统将自动恢复运行。**"
                yield f"data: {json.dumps({'type': 'token', 'content': interrupt_msg})}\n\n"

        except Exception as e:
            # 如果系统崩溃，优雅地把报错推给前端，并打印堆栈到控制台！
            import traceback

            traceback.print_exc()
            yield f"data: {json.dumps({'type': 'error', 'content': f'服务器内部错误: {str(e)}'})}\n\n"

        # 3. 水流干了，发送结束信号让前端挂断电话
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    # 4. 把产水器接上 StreamingResponse 水管，明确告诉浏览器这是 SSE 流！
    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/sessions")
async def get_chat_sessions():
    """获取所有历史会话列表，包括标题与最后活动时间"""
    try:
        pool = get_pool()
        agent_app = get_agent_app()

        # 1. 快速查询数据库中所有唯一的 thread_id 以及最新时间戳
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT thread_id, MAX(checkpoint->>'ts') as latest_ts
                    FROM public.checkpoints
                    GROUP BY thread_id
                    ORDER BY latest_ts DESC
                    LIMIT 50
                """)
                rows = cur.fetchall()

        sessions = []
        for row in rows:
            thread_id = row[0]
            ts = row[1]
            formatted_time = ts[:19].replace("T", " ") if ts else "未知时间"

            # 2. 调用 aget_state 高效拉取消息标题
            config = {"configurable": {"thread_id": thread_id}}
            state = await agent_app.aget_state(config)
            messages = state.values.get("messages", [])

            title = ""
            if messages:
                # 寻找第一个 HumanMessage 提取内容
                for msg in messages:
                    if isinstance(msg, HumanMessage) or (
                        hasattr(msg, "type") and msg.type == "human"
                    ):
                        title = str(msg.content)
                        break
                if not title:
                    # 备用方案：第一条非空消息
                    for msg in messages:
                        if hasattr(msg, "content") and msg.content:
                            title = str(msg.content)
                            break

            if title:
                title = title[:20] + "..." if len(title) > 20 else title
            else:
                title = f"未命名会话 ({thread_id[:8]})"

            sessions.append(
                {"session_id": thread_id, "title": title, "created_at": formatted_time}
            )

        return {"status": "success", "data": sessions}
    except Exception as e:
        import traceback

        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history/{thread_id}")
async def get_session_history(thread_id: str):
    """获取指定会话的完整聊天历史记录"""
    try:
        agent_app = get_agent_app()
        config = {"configurable": {"thread_id": thread_id}}
        state = await agent_app.aget_state(config)
        messages = state.values.get("messages", [])

        history_list = []
        for msg in messages:
            content = getattr(msg, "content", "")
            # 区分角色
            if isinstance(msg, HumanMessage) or (
                hasattr(msg, "type") and msg.type == "human"
            ):
                role = "user"
            else:
                role = "assistant"

            # 过滤掉系统内部路由标签消息，只展示有意义的内容给用户
            if content and not any(
                tag in str(content)
                for tag in ["<内部路由标签>", "<沙箱执行成功>", "<沙箱执行失败>"]
            ):
                history_list.append({"role": role, "content": content})

        return {"status": "success", "data": history_list}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/history/{thread_id}")
async def delete_session_history(thread_id: str):
    """物理删除指定 thread_id 的所有 checkpoint 记录"""
    try:
        pool = get_pool()
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM public.checkpoints WHERE thread_id = %s", (thread_id,)
                )
                cur.execute(
                    "DELETE FROM public.checkpoint_blobs WHERE thread_id = %s",
                    (thread_id,),
                )
                cur.execute(
                    "DELETE FROM public.checkpoint_writes WHERE thread_id = %s",
                    (thread_id,),
                )
        return {
            "status": "success",
            "message": f"会话 {thread_id} 已成功从数据库物理删除。",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
