from typing import Annotated, Any

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class UniversalAgentState(TypedDict):
    """Unified graph state across all agent routing nodes."""
    messages: Annotated[list[BaseMessage], add_messages]
    active_tools: list[str]
    system_logs: list[str]
    retry_count: int
    error_flag: bool
    error_log: list[dict[str, Any]]