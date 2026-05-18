from typing import Literal, Optional, Any, Union, Annotated
from pydantic import BaseModel, Field
from src.models.messages import AgentMessage

class TurnStartEvent(BaseModel):
    """一个新回合开启"""
    type: Literal["turn_start"] = "turn_start"

class MessageDeltaEvent(BaseModel):
    """流式消息片段"""
    type: Literal["message_delta"] = "message_delta"
    content: str  # 本次新增的文本片段

class ToolCallStartEvent(BaseModel):
    """工具开始执行"""
    type: Literal["tool_call_start"] = "tool_call_start"
    tool_call_id: str
    tool_name: str
    arguments: str

class ToolCallEndEvent(BaseModel):
    """工具执行结束"""
    type: Literal["tool_call_end"] = "tool_call_end"
    tool_call_id: str
    result: Any
    is_error: bool = False

class TurnEndEvent(BaseModel):
    """回合结束，包含最终汇总的消息"""
    type: Literal["turn_end"] = "turn_end"
    message: AgentMessage

# 统一事件联合类型
AgentEvent = Annotated[
    Union[TurnStartEvent, MessageDeltaEvent, ToolCallStartEvent, ToolCallEndEvent, TurnEndEvent],
    Field(discriminator="type")
]
