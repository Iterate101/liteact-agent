import asyncio
from typing import Protocol, Optional, Any, Callable, Awaitable, List, Union, Annotated, runtime_checkable
from pydantic import BaseModel, Field
from src.models.messages import TextContent, ImageContent

class AgentToolResult(BaseModel):
    """
    【工具执行结果模型】
    统一所有工具的输出格式。
    """
    content: List[Union[TextContent, ImageContent]]
    details: Optional[Any] = None
    is_error: bool = False

# 定义回调函数类型：接收中间结果（通常是字符串），不返回任何内容
# 这是一个异步回调，格式为: async def on_partial(data: str) -> None
AgentToolUpdateCallback = Callable[[str], Awaitable[None]]

@runtime_checkable
class AgentTool(Protocol):
    """
    【工具协议契约】
    复刻 TS 版实现。任何具备 execute 异步方法的类均可视为 AgentTool。
    """
    
    name: str
    description: str
    parameters: dict # 【核心补全】：遵循 JSON Schema 格式的参数规格说明书

    async def execute(
        self, 
        tool_call_id: str, 
        params: dict, 
        abort_signal: Optional[asyncio.Event] = None,
        on_partial_result: Optional[AgentToolUpdateCallback] = None
    ) -> AgentToolResult:
        """
        核心执行逻辑。
        :param on_partial_result: 可选的异步回调，用于实时推送执行进度（如 Bash 输出）。
        """
        ...
