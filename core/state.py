from typing import TypedDict, Annotated, List
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    active_file_path: str
    dataframe_columns: List[str]
    generated_code: str
    execution_error: str
    error_count: int

    # [V2 认知预处理层新增字段]
    schema_hypothesis: str  # 大模型对数据的试探性探索结果
    requires_human_approval: bool  # 是否因为数据太复杂/模糊，需要触发“人在回路”拦截
    user_summary: str  # 供用户查看的简明数据探针总结报告
