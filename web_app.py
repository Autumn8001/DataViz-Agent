import streamlit as st
import requests
import json
import uuid
import os
import base64
import re

API_BASE = os.environ.get("API_BASE", "http://localhost:8000/api")


def render_markdown_with_local_images(content: str) -> str:
    """
    解析 Markdown 中的图片语法，如果指向本地文件，自动将其转化为 base64 以供 Streamlit 渲染
    """
    pattern = r"!\[([^\]]*)\]\(([^)]+)\)"

    def repl(match):
        alt_text = match.group(1)
        raw_path = match.group(2)
        local_path = raw_path.replace("\\", "/")

        if not (
            local_path.startswith("http://")
            or local_path.startswith("https://")
            or local_path.startswith("data:")
        ):
            if os.path.exists(local_path) and local_path.lower().endswith(
                (".png", ".jpg", ".jpeg", ".gif", ".webp")
            ):
                try:
                    with open(local_path, "rb") as f:
                        img_data = f.read()
                    b64 = base64.b64encode(img_data).decode("utf-8")
                    ext = local_path.split(".")[-1].lower()
                    if ext == "jpg":
                        ext = "jpeg"
                    return f"![{alt_text}](data:image/{ext};base64,{b64})"
                except Exception:
                    pass
        return match.group(0)

    return re.sub(pattern, repl, content)


# ── 1. 缓存 API 请求 ─────────────────────────────────────────────────────────
@st.cache_data(ttl=2)
def fetch_sessions():
    """获取所有历史会话列表，缓存在本地以防止频繁闪烁"""
    try:
        res = requests.get(f"{API_BASE}/sessions", timeout=5)
        if res.status_code == 200:
            return res.json().get("data", [])
    except Exception:
        pass
    return []


# ── 2. Streamlit 页面基础配置及 CSS 注入 ─────────────────────────────────────────
st.set_page_config(
    page_title="DataViz Agent",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
<style>
/* ── 隐藏必要多余元素，保持精美 ── */
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }
.stDeployButton { display: none; }

/* ── 极简 Claude 质感背景底色 ── */
.stApp { background-color: #f5f4ef; }
.main { background-color: #f5f4ef; }

/* ── 侧边栏（Sidebar）美化 ── */
section[data-testid="stSidebar"] {
    background: #ffffff;
    border-right: 1px solid #e8e8e8;
}
section[data-testid="stSidebar"] > div:first-child {
    padding: 20px 14px;
}

/* ── 按钮样式重构（圆角、过渡） ── */
.stButton > button {
    border-radius: 10px;
    border: 1px solid #e5e5e5;
    background: white;
    color: #333;
    font-size: 13px;
    transition: all 0.15s;
    text-align: left;
    padding: 8px 12px;
}
.stButton > button:hover {
    background: #f5f5f5;
    border-color: #ccc;
}

/* ── 输入框美化 ── */
[data-testid="stTextInput"] input {
    background: white !important;
    border: 1px solid #e8e8e8 !important;
    border-radius: 8px !important;
    font-size: 13px !important;
    color: #333 !important;
    box-shadow: none !important;
}
[data-testid="stTextInput"] input:focus {
    border-color: #ccc !important;
    box-shadow: none !important;
}

/* ── 底部聊天输入框扁平化 ── */
[data-testid="stChatInput"] {
    background: #efefef !important;
    border-radius: 16px !important;
    border: none !important;
    padding: 6px 6px 6px 4px !important;
    box-shadow: none !important;
}
[data-testid="stChatInput"] textarea {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    font-size: 14px !important;
    color: #333 !important;
    padding: 10px 14px !important;
}
[data-testid="stChatInput"] button {
    background: #3d3d3d !important;
    border-radius: 10px !important;
    border: none !important;
    width: 38px !important;
    height: 38px !important;
    margin: auto 2px !important;
    transition: background 0.15s !important;
}
[data-testid="stChatInput"] button:hover {
    background: #1a1a1a !important;
}
[data-testid="stChatInput"] button svg {
    fill: white !important;
    color: white !important;
}

/* ── 隐藏原生消息卡片边框，打造极简流式输出 ── */
[data-testid="stChatMessage"] {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
}

/* ── 详细展开/折叠面板 ── */
[data-testid="stExpander"] {
    background: white !important;
    border: 1px solid #e8e8e8 !important;
    border-radius: 10px !important;
    box-shadow: none !important;
}
[data-testid="stExpander"] summary {
    color: #444 !important;
    font-size: 13px !important;
    font-weight: 500 !important;
}

/* ── 文件上传拖拽框 ── */
[data-testid="stFileUploader"] {
    background: white;
    border-radius: 10px;
    border: 1px dashed #ddd;
    padding: 4px;
}
[data-testid="stFileUploader"] section {
    background: transparent !important;
    border: none !important;
}

/* ── 分割线 ── */
hr { border-color: #ebebeb !important; margin: 10px 0 !important; }

/* ── 主阅读区居中宽度 ── */
.main .block-container {
    max-width: 860px;
    padding: 2rem 2rem 5rem;
    margin: 0 auto;
}

/* ── 侧边栏字体标签 ── */
.sidebar-label {
    font-size: 10px;
    font-weight: 700;
    color: #aaa;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    margin: 16px 0 8px 2px;
}
</style>
""",
    unsafe_allow_html=True,
)

# ── 3. Session State 初始化 ──────────────────────────────────────────────────
defaults = {
    "thread_id": str(uuid.uuid4()),
    "messages": [],
    "file_path": "",
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v


def load_history(thread_id: str):
    """根据 thread_id 向后端抓取聊天记录"""
    st.session_state.thread_id = thread_id
    try:
        res = requests.get(f"{API_BASE}/history/{thread_id}", timeout=5)
        if res.status_code == 200:
            st.session_state.messages = res.json().get("data", [])
    except Exception:
        st.session_state.messages = []


# ── 4. 侧边栏布局与会话切换 ──────────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        """
    <div style="display:flex;align-items:center;gap:10px;padding-bottom:16px;border-bottom:1px solid #f0f0f0;">
        <div style="width:28px;height:28px;background:linear-gradient(135deg,#ff8008,#ffc837);border-radius:50%;flex-shrink:0;"></div>
        <div>
            <div style="font-size:13px;font-weight:700;color:#1a1a1a;">DataViz Agent</div>
            <div style="font-size:11px;color:#666;"></div>
        </div>
    </div>
    """,
        unsafe_allow_html=True,
    )

    # 按钮 + 新对话
    if st.button("+ 新对话", use_container_width=True):
        st.session_state.thread_id = str(uuid.uuid4())
        st.session_state.messages = []
        st.session_state.file_path = ""
        st.rerun()

    # 对话搜索
    st.markdown('<div class="sidebar-label">历史对话</div>', unsafe_allow_html=True)
    search_query = st.text_input(
        "",
        placeholder="搜索对话...",
        label_visibility="collapsed",
        key="history_search",
    )

    # 列表展示
    sessions = fetch_sessions()
    if search_query:
        sessions = [
            s for s in sessions if search_query.lower() in s.get("title", "").lower()
        ]

    if not sessions:
        st.caption("暂无历史对话")
    else:
        for s in sessions:
            title = s["title"]
            is_active = s["session_id"] == st.session_state.thread_id
            btn_label = f"💬 {title}"
            if is_active:
                btn_label = f" {title} (当前)"

            if st.button(btn_label, key=s["session_id"], use_container_width=True):
                load_history(s["session_id"])
                st.rerun()

    st.divider()

    # 管理选项
    with st.expander("🛠️ 管理选项"):
        st.markdown(
            '<div class="sidebar-label">CSV 数据源</div>', unsafe_allow_html=True
        )
        uploaded_file = st.file_uploader(
            "上传你要分析的 CSV 数据", type=["csv"], label_visibility="collapsed"
        )
        if uploaded_file is not None:
            os.makedirs("data/uploads", exist_ok=True)
            st.session_state.file_path = f"data/uploads/{uploaded_file.name}"
            with open(st.session_state.file_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            st.success(f"已就绪: {uploaded_file.name}")
        elif st.session_state.file_path:
            st.caption(f"当前数据: {os.path.basename(st.session_state.file_path)}")

        st.divider()
        st.markdown('<div class="sidebar-label">会话清理</div>', unsafe_allow_html=True)

        if st.button("🗑️ 删除当前会话", use_container_width=True):
            try:
                requests.delete(
                    f"{API_BASE}/history/{st.session_state.thread_id}", timeout=5
                )
                st.session_state.thread_id = str(uuid.uuid4())
                st.session_state.messages = []
                st.session_state.file_path = ""
                fetch_sessions.clear()  # 物理清除本地 st 缓存
                st.success("会话已成功删除")
                st.rerun()
            except Exception as e:
                st.error(f"删除失败: {e}")

# ── 5. 主区域内容展示 ──────────────────────────────────────────────────────────
if not st.session_state.messages:
    st.markdown(
        """
    <div style="text-align:center;padding:120px 0 40px;">
        <h1 style="font-size:2.5rem;font-weight:800;color:#2d2d2d;margin-bottom:12px;letter-spacing:-0.5px;"> DataViz Agent</h1>
        <p style="font-size:1.05rem;color:#666;max-width:520px;margin:0 auto 24px;line-height:1.6;">
            支持人在回路（HITL）动态指令修正、黑盒代码自动折叠透明化的多租户数据库记忆分析专家。
        </p>
    </div>
    """,
        unsafe_allow_html=True,
    )
else:
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(
                render_markdown_with_local_images(msg["content"]),
                unsafe_allow_html=True,
            )

# ── 6. 聊天输入与后端双轨推流 ───────────────────────────────────────────────────
if prompt := st.chat_input("请输入你的数据分析需求或纠偏反馈..."):
    # 4.1 打印用户输入
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # 4.2 SSE 接收
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        status_placeholder = st.empty()
        full_response = ""

        try:
            response = requests.post(
                f"{API_BASE}/chat",
                json={
                    "message": prompt,
                    "file_path": st.session_state.file_path,
                    "thread_id": st.session_state.thread_id,
                },
                stream=True,
            )

            for line in response.iter_lines():
                if line:
                    decoded_line = line.decode("utf-8")
                    if decoded_line.startswith("data: "):
                        data_json = json.loads(decoded_line[6:])

                        # 轨道 A: 吐字 Token
                        if data_json["type"] == "token":
                            full_response += data_json["content"]
                            message_placeholder.markdown(
                                render_markdown_with_local_images(full_response) + "",
                                unsafe_allow_html=True,
                            )

                        # 轨道 B: 节点状态播报
                        elif data_json["type"] == "status":
                            status_placeholder.info(data_json["content"])

                        # 轨道 C: 系统错误反馈
                        elif data_json["type"] == "error":
                            st.error(data_json["content"])

                        elif data_json["type"] == "done":
                            break

            # 收尾，移除打字机光标
            message_placeholder.markdown(
                render_markdown_with_local_images(full_response), unsafe_allow_html=True
            )
            status_placeholder.empty()

            # 追加到消息列表
            st.session_state.messages.append(
                {"role": "assistant", "content": full_response}
            )
            fetch_sessions.clear()  # 触发会话列表缓存更新，更新左侧列表标题
            st.rerun()

        except Exception as e:
            st.error(f"后端未启动或发生崩溃: {e}")
