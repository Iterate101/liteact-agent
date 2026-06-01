from typing import Literal, Optional, Any, Union, Annotated, List
from pydantic import BaseModel, Field
from src.models.messages import AgentMessage

class PlanEvent(BaseModel):
    """任务级计划记录，写入 trace 用于复盘一次 Agent 运行。"""
    type: Literal["plan"] = "plan"
    task: str
    tools: List[str]
    max_turns: int

class TurnStartEvent(BaseModel):
    """一个新回合开启"""
    type: Literal["turn_start"] = "turn_start"

class StepStartEvent(BaseModel):
    """一次 ReAct 推理步骤开始"""
    type: Literal["step_start"] = "step_start"
    turn: int
    summary: str

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
    details: Optional[Any] = None
    is_error: bool = False

class VerificationEvent(BaseModel):
    """工具执行后的轻量验证结果"""
    type: Literal["verification"] = "verification"
    turn: int
    passed: bool
    summary: str

class TurnEndEvent(BaseModel):
    """回合结束，包含最终汇总的消息"""
    type: Literal["turn_end"] = "turn_end"
    message: AgentMessage

class FinalEvent(BaseModel):
    """任务级最终状态"""
    type: Literal["final"] = "final"
    status: Literal["done", "error", "max_turns"]
    turns: int
    summary: str

class ErrorEvent(BaseModel):
    """任务级错误事件"""
    type: Literal["error"] = "error"
    turn: Optional[int] = None
    message: str
    recoverable: bool = False

# 统一事件联合类型
AgentEvent = Annotated[
    Union[
        PlanEvent,
        TurnStartEvent,
        StepStartEvent,
        MessageDeltaEvent,
        ToolCallStartEvent,
        ToolCallEndEvent,
        VerificationEvent,
        TurnEndEvent,
        FinalEvent,
        ErrorEvent,
    ],
    Field(discriminator="type")
]
