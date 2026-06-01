import asyncio
from typing import Optional, Callable, Awaitable
from src.tools.base import AgentTool, AgentToolResult, AgentToolUpdateCallback, TextContent

class AttachTool(AgentTool):
    """
    【附件分发器】
    允许 Agent 将沙箱内的文件（如生成的 CSV、图表、分析报告）上传并投递到 Slack 对话频道中。
    """
    
    name: str = "attach_file"
    description: str = "将指定路径的文件作为附件上传并分享到 Slack。常用于发送分析报告、图片、生成的代码等。"
    parameters: dict = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "The path to the file inside the sandbox (e.g., /workspace/report.png)."},
            "label": {"type": "string", "description": "Optional: A title or description for the file."}
        },
        "required": ["path"]
    }

    def __init__(self, upload_fn: Optional[Callable[[str, Optional[str]], Awaitable[None]]] = None):
        # 这是一个由 AgentRunner 注入的异步回调函数
        # 签名为 (filePath, title) -> None
        self.upload_fn = upload_fn

    async def execute(
        self, 
        tool_call_id: str, 
        params: dict, 
        abort_signal: Optional[asyncio.Event] = None,
        on_partial_result: Optional[AgentToolUpdateCallback] = None
    ) -> AgentToolResult:
        file_path = params.get("path")
        label = params.get("label")

        if not self.upload_fn:
             return AgentToolResult(
                content=[TextContent(text="Error: 上传功能不可用（未初始化）")],
                is_error=True
            )

        try:
            # 1. 广播通知：开始投递附件
            if on_partial_result:
                await on_partial_result(f"_→ 正在投递附件: `{file_path}`..._")

            # 2. 调用外部注入的上传机制（内部包含路径转译逻辑）
            await self.upload_fn(file_path, label)

            return AgentToolResult(
                content=[TextContent(text=f"✅ 附件 `{file_path}` 已成功上传并分享。")],
                details={"path": file_path, "label": label}
            )

        except Exception as e:
            return AgentToolResult(
                content=[TextContent(text=f"❌ 附件投递失败: {str(e)}")],
                is_error=True
            )
