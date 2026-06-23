import os
import asyncio
from dotenv import load_dotenv
from psycopg_pool import ConnectionPool
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
)
import os
import asyncio
from dotenv import load_dotenv
from psycopg_pool import ConnectionPool
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
)
from typing import AsyncIterator, Iterator

# 1. 自动加载 .env 里的 POSTGRES_URI
load_dotenv()
DB_URI = os.getenv("POSTGRES_URI")

# 采用单例懒加载模式，避免在模块导入 (import) 时触发物理连接和启动后台线程，从而加快 startup/reload 速度，并防止进程退出时线程挂起
_pool = None
_sync_saver = None
_checkpointer = None


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            conninfo=DB_URI, max_size=10, kwargs={"autocommit": True}
        )
    return _pool


# 4.  核心适配器：自定义异步包装器，将同步的 I/O 操作分流到线程池执行，完美契合 LangGraph 的异步 API
class AsyncPostgresSaverWrapper(BaseCheckpointSaver):
    def __init__(self, sync_saver: PostgresSaver):
        super().__init__(serde=sync_saver.serde)
        self.sync_saver = sync_saver

    async def aget_tuple(self, config: dict) -> CheckpointTuple | None:
        return await asyncio.to_thread(self.sync_saver.get_tuple, config)

    async def aput(
        self,
        config: dict,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: dict,
    ) -> dict:
        return await asyncio.to_thread(
            self.sync_saver.put, config, checkpoint, metadata, new_versions
        )

    async def aput_writes(self, config: dict, writes: list, task_id: str) -> None:
        return await asyncio.to_thread(
            self.sync_saver.put_writes, config, writes, task_id
        )

    async def alist(
        self,
        config: dict,
        *,
        filter: dict = None,
        before: dict = None,
        limit: int = None,
    ) -> AsyncIterator[CheckpointTuple]:
        # 将同步列表查询放入线程池，并生成异步生成器
        sync_list = await asyncio.to_thread(
            self.sync_saver.list, config, filter=filter, before=before, limit=limit
        )
        for item in sync_list:
            yield item

    def get_tuple(self, config: dict) -> CheckpointTuple | None:
        return self.sync_saver.get_tuple(config)

    def put(
        self,
        config: dict,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: dict,
    ) -> dict:
        return self.sync_saver.put(config, checkpoint, metadata, new_versions)

    def put_writes(self, config: dict, writes: list, task_id: str) -> None:
        self.sync_saver.put_writes(config, writes, task_id)

    def list(
        self,
        config: dict,
        *,
        filter: dict = None,
        before: dict = None,
        limit: int = None,
    ) -> Iterator[CheckpointTuple]:
        return self.sync_saver.list(config, filter=filter, before=before, limit=limit)


def get_checkpointer() -> AsyncPostgresSaverWrapper:
    """
    延迟获取且单例化 Checkpointer，确保在 asyncio 运行期或 lifespan 启动期才物理连接数据库
    """
    global _checkpointer, _sync_saver
    if _checkpointer is None:
        p = get_pool()
        _sync_saver = PostgresSaver(p)
        _sync_saver.setup()
        
        # 建立 agent_sessions 关系表，用于硬核校验 thread_id 与用户的归属关系
        try:
            with p.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS agent_sessions (
                            thread_id VARCHAR(255) PRIMARY KEY,
                            user_id VARCHAR(255) NOT NULL,
                            tenant_id VARCHAR(255) NOT NULL,
                            title VARCHAR(255),
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        );
                    """)
            print(" [Database] agent_sessions 表校验与建表完成。")
        except Exception as e:
            print(f"⚠️ [Database] 初始化 agent_sessions 表异常: {e}")

        _checkpointer = AsyncPostgresSaverWrapper(_sync_saver)
    return _checkpointer


def close_pool():
    """
    在生命周期结束时手动调用，优雅关闭连接池，彻底杀掉后台 worker 线程，防止退出挂起
    """
    global _pool
    if _pool is not None:
        try:
            _pool.close()
            print(" [Database] Postgres 连接池优雅释放完成。")
        except Exception as e:
            print(f"️ [Database] 关闭连接池异常: {e}")
        _pool = None
