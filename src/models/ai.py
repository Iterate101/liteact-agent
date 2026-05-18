from typing import List, Union, Literal, Optional, Any, Annotated, Dict
from pydantic import BaseModel, Field, ConfigDict

# --- 第一阶段：内容原子 (Content Atoms) ---
# 这些是构成每一条消息的小砖块

class TextContent(BaseModel):
    """【文本切片】AI 的回答或用户的输入"""
    type: Literal["text"] = "text"
    text: str

class ThinkingContent(BaseModel):
    """【思考逻辑】如 DeepSeek 或 Claude 的思维链 (Chain of Thought)"""
    type: Literal["thinking"] = "thinking"
    thinking: str
    redacted: bool = False # 是否因安全原因被脱敏

class ImageContent(BaseModel):
    """【多模态图片】Base64 编码的图像数据"""
    type: Literal["image"] = "image"
    data: str      # base64 数据
    mime_type: str # 如 image/jpeg

class ToolCall(BaseModel):
    """【工具调用请求】由 AI 在助手消息中发起"""
    type: Literal["toolCall"] = "toolCall"
    id: str
    name: str
    arguments: Dict[str, Any]

# 助手能发出的所有内容块
AssistantContent = Annotated[
    Union[TextContent, ThinkingContent, ToolCall],
    Field(discriminator="type")
]

# --- 第二阶段：用量统计 (Usage Accounting) ---

class CostInfo(BaseModel):
    """【金钱消耗】精确统计每一次 API 调用的成本"""
    input: float = 0
    output: float = 0
    cache_read: float = 0
    cache_write: float = 0
    total: float = 0

class Usage(BaseModel):
    """【资源消耗】Token 统计详情"""
    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_write: int = 0
    total_tokens: int = 0
    cost: CostInfo = Field(default_factory=CostInfo)

# --- 第三阶段：核心角色消息 (Core Messages) ---

import uuid

class UserMessage(BaseModel):
    """【人类视角】来自外部输入的原始信息"""
    role: Literal["user"] = "user"
    content: Union[str, List[Union[TextContent, ImageContent]]]
    uuid: str = Field(default_factory=lambda: str(uuid.uuid4()))
    parent_uuid: Optional[str] = None
    msg_type: str = "regular" # [regular | compaction]
    timestamp: int = Field(default_factory=lambda: 0)

class AssistantMessage(BaseModel):
    """【助手视角】由 AI 推理产生的结果"""
    role: Literal["assistant"] = "assistant"
    content: List[AssistantContent]
    uuid: str = Field(default_factory=lambda: str(uuid.uuid4()))
    parent_uuid: Optional[str] = None
    msg_type: str = "regular"
    usage: Usage = Field(default_factory=Usage)
    stop_reason: Literal["stop", "length", "toolUse", "error", "aborted"] = "stop"
    model: str = ""
    provider: str = ""
    timestamp: int = Field(default_factory=lambda: 0)

class ToolResultMessage(BaseModel):
    """【执行反馈】将工具执行的结果喂回给模型"""
    role: Literal["toolResult"] = "toolResult"
    tool_call_id: str
    tool_name: str
    content: List[Union[TextContent, ImageContent]]
    uuid: str = Field(default_factory=lambda: str(uuid.uuid4()))
    parent_uuid: Optional[str] = None
    msg_type: str = "regular"
    is_error: bool = False
    details: Optional[Any] = None
    timestamp: int = Field(default_factory=lambda: 0)

# 对话流中的全量消息联合体
AgentMessage = Annotated[
    Union[UserMessage, AssistantMessage, ToolResultMessage],
    Field(discriminator="role")
]

# --- 第四阶段：统一流式事件 (Unified Streaming Events) ---
# 无论底层是 WebSocket 还是 SSE，发送给 UI 层或 Logic 层的必须是以下四种事件。

class TextDelta(BaseModel):
    """文本片段增量"""
    type: Literal["text"] = "text"
    delta: str

class ThinkingDelta(BaseModel):
    """思考逻辑增量"""
    type: Literal["thinking"] = "thinking"
    delta: str

class ToolCallDelta(BaseModel):
    """工具请求增量（或全量快照）"""
    type: Literal["tool_call"] = "tool_call"
    tool_call: ToolCall

class UsageEvent(BaseModel):
    """最终用量结算"""
    type: Literal["usage"] = "usage"
    usage: Usage

# 这是你要求的统一事件生成流所生成的对象
StreamEvent = Annotated[
    Union[TextDelta, ThinkingDelta, ToolCallDelta, UsageEvent],
    Field(discriminator="type")
]

class AgentContext(BaseModel):
    """
    【对话上下文】
    封装了系统提示词以及整个 AgentSession 的历史消息流水。
    """
    # 兼容旧代码里的 systemPrompt，同时推荐新代码使用 Python 风格的 system_prompt。
    model_config = ConfigDict(populate_by_name=True)

    system_prompt: str = Field(default="", alias="systemPrompt")
    messages: List[AgentMessage] = Field(default_factory=list)
    max_iterations: int = 10  # 【新增】：防止推理死循环的安全阈值
