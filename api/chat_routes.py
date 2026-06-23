from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import json
import time
import os
from langchain_core.messages import HumanMessage, AIMessage
from core.database import get_pool
from core.agent import get_agent_app
from core.auth import get_current_user

router = APIRouter()


# 严格校验前端传过来的数据格式
class ChatRequest(BaseModel):
    message: str
    file_path: str | None = ""  # 如果用户传了文件，这里就会有路径
    thread_id: str  # 💡 必须让前端传一个存档号过来，不然怎么找记忆？


@router.post("/chat")
async def chat_endpoint(
    request: ChatRequest,
    current_user: dict = Depends(get_current_user)
):
    """接收前端对话请求，并返回 SSE 流式推流响应（注入 JWT 用户和 thread_id 隔离）"""
    
    user_id = current_user["user_id"]
    tenant_id = current_user.get("tenant_id", "default")
    thread_id = request.thread_id
    
    # 🛡️ 安全硬隔离：基于 agent_sessions 关系表的多租户越权审计
    pool = get_pool()
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT user_id FROM agent_sessions WHERE thread_id = %s", (thread_id,))
            row = cur.fetchone()
            if row:
                # 存在会话记录，强行核实是否属于当前用户
                if row[0] != user_id:
                    raise HTTPException(
                        status_code=403,
                        detail="权限拒绝：当前的 thread_id 并不属于您，越权已被拦截。"
                    )
            else:
                # 全新会话，前置命名协议校验并自动写入关系表
                if not thread_id.startswith(f"user_{user_id}_"):
                    raise HTTPException(
                        status_code=403,
                        detail="权限拒绝：新会话 thread_id 必须以所属 user_id 为前缀。"
                    )
                # 插入绑定关系记录
                msg_snippet = request.message[:30] if request.message else "新分析对话"
                cur.execute(
                    "INSERT INTO agent_sessions (thread_id, user_id, tenant_id, title) VALUES (%s, %s, %s, %s) ON CONFLICT (thread_id) DO NOTHING",
                    (thread_id, user_id, tenant_id, msg_snippet)
                )

    # 🛡️ 物理路径防穿越校验 (使用 Path.resolve() 绝对路径与 is_relative_to 安全防线)
    req_file_path = request.file_path or ""
    if req_file_path:
        from pathlib import Path
        try:
            # 绝对化基准 uploads 隔离目录和目标物理文件路径，杜绝 ../ 物理回溯
            base_uploads_dir = Path("data/uploads").resolve()
            user_uploads_dir = (base_uploads_dir / str(user_id)).resolve()
            target_path = Path(req_file_path).resolve()
            
            # 校验 target_path 必须落在该用户的 uploads 隔离子目录下
            if not target_path.is_relative_to(user_uploads_dir):
                raise HTTPException(
                    status_code=403,
                    detail="权限拒绝：文件路径越权访问拦截。"
                )
        except Exception:
            raise HTTPException(
                status_code=403,
                detail="权限拒绝：文件路径非法或越权访问拦截。"
            )

    # 核心：造一个“源源不断的产水器”（异步生成器）
    async def event_generator():
        node_start_times = {}
        # 1. 组装初始黑板状态
        initial_state = {
            "messages": [HumanMessage(content=request.message)],
            "user_id": user_id
        }

        if req_file_path:
            initial_state["active_file_path"] = req_file_path

        # 组装记忆卡槽配置
        config = {"configurable": {"thread_id": thread_id}}

        try:
            # 动态获取已处于运行 asyncio 循环内的 agent_app 实例
            agent_app = get_agent_app()

            # 💡 检查图是否在中断状态（比如卡在 human_node 之前）
            state = await agent_app.aget_state(config)
            if not req_file_path:
                saved_file_path = state.values.get("active_file_path") or ""
                if saved_file_path: 
                    initial_state["active_file_path"] = saved_file_path
            
            if state.next:
                # 恢复执行：将当前用户的输入作为人类的指令，更新到 human_node 的输入中
                await agent_app.aupdate_state(
                    config, {
                        "messages": [HumanMessage(content=request.message)],
                        "user_id": user_id
                    }
                )
                event_stream = agent_app.astream_events(
                    None, config=config, version="v2"
                )
                yield f"data: {json.dumps({'type': 'status', 'content': ' 人在回路反馈接收成功，正在恢复运行并修正分析策略...'})}\n\n"
                yield f"data: {json.dumps({'type': 'trace', 'content': '已接收人类纠偏反馈，正在从中断点恢复执行'})}\n\n"
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
                    # 只允许带有 "final_analyzer" 标签的模型输出，拦截掉 Coder 的 Python 代码
                    if "final_analyzer" in event.get("tags", []):
                        chunk = event["data"]["chunk"]
                        if chunk.content:
                            yield f"data: {json.dumps({'type': 'token', 'content': chunk.content})}\n\n"

                #  双轨推流之【轨道 B】：节点状态流转
                elif event_type == "on_chain_start":
                    if node_name:
                        node_start_times[node_name] = time.perf_counter()
                    if node_name in [
                        "profiler_node",
                        "planner_node",
                        "quick_tool_node",
                        "coder_node",
                        "executor_node",
                        "analyzer_node",
                    ]:
                        yield f"data: {json.dumps({'type': 'status', 'content': f'⚙️ 系统正在执行节点: {node_name} ...'})}\n\n"
                    trace_text = {
                        "profiler_node": "正在检查数据结构与字段含义",
                        "planner_node": "正在识别用户意图并选择处理路径",
                        "quick_tool_node": "正在调用轻量数据工具",
                        "coder_node": "正在生成 Python 分析代码",
                        "executor_node": "正在执行沙箱代码",
                        "analyzer_node": "正在生成最终回复",
                    }.get(node_name)

                    if trace_text:
                        trace_payload = {
                            "node": node_name,
                            "status": "start",
                            "message": trace_text,
                        }
                        yield f"data: {json.dumps({'type': 'trace', 'content': trace_payload}, ensure_ascii=False)}\n\n"

                #  隐藏轨道之【轨道 C】：拦截关键产物
                elif event_type == "on_chain_end":
                    elapsed = time.perf_counter() - node_start_times.get(node_name, time.perf_counter())
                    trace_text = {
                        "profiler_node": "数据探针完成",
                        "planner_node": "意图识别完成",
                        "quick_tool_node": "轻量工具调用完成",
                        "coder_node": "Python 分析代码生成完成",
                        "executor_node": "沙箱执行完成",
                        "analyzer_node": "最终回复生成完成",
                    }.get(node_name)

                    if trace_text:
                        trace_payload = {
                            "node": node_name,
                            "status": "end",
                            "message": trace_text,
                            "duration": round(elapsed, 2),
                        }
                        yield f"data: {json.dumps({'type': 'trace', 'content': trace_payload}, ensure_ascii=False)}\n\n"
                    
                    if node_name == "executor_node":
                        output_dict = event["data"].get("output", {})
                        if isinstance(output_dict, dict) and "messages" in output_dict:
                            for msg in output_dict["messages"]:
                                if isinstance(msg, AIMessage) and "![" in str(msg.content):
                                    yield f"data: {json.dumps({'type': 'token', 'content': f'\n\n{msg.content}\n\n'})}\n\n"

                    elif node_name == "coder_node":
                        output_dict = event["data"].get("output", {})
                        if isinstance(output_dict, dict) and "generated_code" in output_dict:
                            code = output_dict["generated_code"]
                            if code:
                                code_markdown = f"\n\n** 💻 AI 编写的分析代码 (点击展开查看)：**\n<details>\n<summary>点击展开/折叠查看 Python 分析代码</summary>\n\n```python\n{code}\n```\n</details>\n\n"
                                yield f"data: {json.dumps({'type': 'token', 'content': code_markdown})}\n\n"

                    elif node_name == "profiler_node":
                        output_dict = event["data"].get("output", {})
                        if isinstance(output_dict, dict) and "user_summary" in output_dict:
                            user_summary = output_dict["user_summary"]
                            if user_summary:
                                report_markdown = f"\n\n🔍 **【数据探针检测报告】**\n\n{user_summary}\n\n"
                                yield f"data: {json.dumps({'type': 'token', 'content': report_markdown})}\n\n"

            # 💡 运行结束后，再次检查是否卡在 human_node 之前（即被中断了）
            final_state = await agent_app.aget_state(config)
            if final_state.next and "human_node" in final_state.next:
                interrupt_msg = "\n\n️ **[人在回路中断拦截]**\n数据探针检测到数据中存在模糊字段或大面积缺失。系统已自动挂起拦截。\n👉 **请在下方输入框中提供指导纠偏指令（如：指定某列是日期列，或者如何处理缺失值），然后发送。系统将自动恢复运行。**"
                yield f"data: {json.dumps({'type': 'token', 'content': interrupt_msg})}\n\n"

        except Exception as e:
            import traceback
            traceback.print_exc()
            yield f"data: {json.dumps({'type': 'error', 'content': f'服务器内部错误: {str(e)}'})}\n\n"

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/sessions")
async def get_chat_sessions(current_user: dict = Depends(get_current_user)):
    """获取当前用户的历史会话列表（从关系表高效拉取并实现硬隔离）"""
    user_id = current_user["user_id"]
    try:
        pool = get_pool()
        sessions = []
        with pool.connection() as conn:
            with conn.cursor() as cur:
                # 关联查询 checkpoints 最大 ts 及 agent_sessions 表，规避模糊前缀查询性能漏洞
                cur.execute("""
                    SELECT s.thread_id, s.title, s.created_at, MAX(c.checkpoint->>'ts') as latest_ts
                    FROM agent_sessions s
                    LEFT JOIN public.checkpoints c ON s.thread_id = c.thread_id
                    WHERE s.user_id = %s
                    GROUP BY s.thread_id, s.title, s.created_at
                    ORDER BY COALESCE(MAX(c.checkpoint->>'ts'), s.created_at::text) DESC
                    LIMIT 50
                """, (user_id,))
                rows = cur.fetchall()

        for row in rows:
            thread_id = row[0]
            title = row[1] or f"分析会话 ({thread_id[:8]})"
            created_at = row[2]
            latest_ts = row[3]
            formatted_time = latest_ts[:19].replace("T", " ") if latest_ts else created_at.strftime("%Y-%m-%d %H:%M:%S")

            sessions.append(
                {"session_id": thread_id, "title": title, "created_at": formatted_time}
            )

        return {"status": "success", "data": sessions}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history/{thread_id}")
async def get_session_history(
    thread_id: str,
    current_user: dict = Depends(get_current_user)
):
    """获取指定会话的完整聊天历史记录（防越权，基于关系表双重验审）"""
    user_id = current_user["user_id"]
    
    # 🛡️ 安全校验：在 agent_sessions 关系表中核查此 thread_id 归属
    pool = get_pool()
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT user_id FROM agent_sessions WHERE thread_id = %s", (thread_id,))
            row = cur.fetchone()
            if not row or row[0] != user_id:
                raise HTTPException(
                    status_code=403,
                    detail="权限拒绝：不能查看不属于您名下的会话记录。"
                )

    try:
        agent_app = get_agent_app()
        config = {"configurable": {"thread_id": thread_id}}
        state = await agent_app.aget_state(config)
        messages = state.values.get("messages", [])

        history_list = []
        for msg in messages:
            content = getattr(msg, "content", "")
            if isinstance(msg, HumanMessage) or (
                hasattr(msg, "type") and msg.type == "human"
            ):
                role = "user"
            else:
                role = "assistant"

            if content and not any(
                tag in str(content)
                for tag in ["<内部路由标签>", "<沙箱执行成功>", "<沙箱执行失败>"]
            ):
                history_list.append({"role": role, "content": content})

        return {
            "status": "success",
            "data": history_list,
            "active_file_path": state.values.get("active_file_path") or "",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/history/{thread_id}")
async def delete_session_history(
    thread_id: str,
    current_user: dict = Depends(get_current_user)
):
    """物理删除属于当前用户的指定会话记录（防越权，级联清理关系表）"""
    user_id = current_user["user_id"]
    
    try:
        pool = get_pool()
        with pool.connection() as conn:
            with conn.cursor() as cur:
                # 🛡️ 安全校验：在数据库层面核验当前会话的物理所有权
                cur.execute("SELECT user_id FROM agent_sessions WHERE thread_id = %s", (thread_id,))
                row = cur.fetchone()
                if not row or row[0] != user_id:
                    raise HTTPException(
                        status_code=403,
                        detail="权限拒绝：不能删除不属于您名下的会话记录。"
                    )

                # 1. 删除 checkpoints
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
                # 2. 删除会话关系记录
                cur.execute(
                    "DELETE FROM public.agent_sessions WHERE thread_id = %s",
                    (thread_id,),
                )
        return {
            "status": "success",
            "message": f"会话 {thread_id} 已成功从数据库物理删除。",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
