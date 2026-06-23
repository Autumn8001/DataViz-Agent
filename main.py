import sys

# 强制标准输出与错误输出为 UTF-8 编码，解决 Windows 终端中文/Emoji 打印导致的 UnicodeEncodeError 闪退
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from contextlib import asynccontextmanager
from core.database import get_checkpointer, close_pool

# 1. 导入咱们刚才写好的推流接口
from api.chat_routes import router as chat_router
from api.upload_routes import (
    router as upload_router,
)  


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时延迟物理拉起连接池并检查表结构，确保导入快、加载轻
    print(" [Lifespan] 正在连接 Postgres 并进行建表检查...")
    get_checkpointer()
    print(" [Lifespan] Postgres 初始化及建表检查完成！")
    yield
    # 关闭时释放连接池，彻底终止后台轮询/存活监控工作线程
    print(" [Lifespan] 正在释放 Postgres 连接池...")
    close_pool()


# 2. 实例化 FastAPI 大厦
app = FastAPI(
    title="DataViz Agent API",
    description="大厂级企业数据分析与可视化智能体后端接口",
    version="1.0.0",
    lifespan=lifespan,
)

# 3. ️ 极其关键的配置：CORS 跨域资源共享（门卫大爷放行）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有前端访问（生产环境一定要改成具体的域名，防黑客）
    allow_credentials=True,
    allow_methods=["*"],  # 允许 GET, POST 等所有请求
    allow_headers=["*"],  # 允许携带任何 Header
)

# 4.  挂载路由：把写好的功能模块插到主板上
app.include_router(chat_router, prefix="/api")
app.include_router(upload_router, prefix="/api")  # 预留

from fastapi.staticfiles import StaticFiles
app.mount("/data", StaticFiles(directory="data"), name="data")



# 5. 写一个健康检查接口（探针）
@app.get("/")
async def root():
    return {"message": " DataViz Agent 后端引擎已点火！系统状态：完美运行！"}


if __name__ == "__main__":
    # 6. 点火启动命令！
    print("🟢 正在拉起 Uvicorn 高性能服务器...")
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)
