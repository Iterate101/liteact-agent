import os
import asyncio
import base64
from typing import Literal, Optional, Dict, Union
from .local import LocalDirectDriver
from .remote import RemoteShellDriver
from src.tools.base import AgentTool, AgentToolResult, AgentToolUpdateCallback
from src.models.messages import TextContent, ImageContent

class FileReadManager(AgentTool):
    """
    【总指挥部】管理所有读取逻辑。
    实现 AgentTool 协议。
    """
    
    name: str = "read_file"
    description: str = "读取文件内容，支持分页、截断和多模态转换。"
    parameters: dict = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "The path to the file to read."},
            "offset": {"type": "integer", "description": "Line number to start reading from (1-indexed).", "default": 1},
            "limit": {"type": "integer", "description": "Maximum number of lines to read.", "default": 800}
        },
        "required": ["path"]
    }
    MAX_LINES = 800
    MAX_BYTES = 50 * 1024

    def __init__(self, mode: Literal["local", "remote"] = "local", base_path: Optional[str] = None):
        self.mode = mode
        self.base_path = base_path
        if mode == "local":
            self.driver = LocalDirectDriver()
        else:
            self.driver = RemoteShellDriver()

    async def execute(
        self, 
        tool_call_id: str, 
        params: dict, 
        abort_signal: Optional[asyncio.Event] = None,
        on_partial_result: Optional[AgentToolUpdateCallback] = None
    ) -> AgentToolResult:
        """作为 AgentTool 协议的唯一入口"""
        path = params.get("path", "")
        
        # 【沙箱加固逻辑】：将虚拟的 /workspace/ 转译为真实的宿主机路径
        if self.base_path and path.startswith("/workspace/"):
            rel_path = path[len("/workspace/"):].lstrip("/")
            params["path"] = os.path.join(self.base_path, rel_path)
            print(f"DEBUG: [沙箱转译] {path} -> {params['path']}")

        res = await self.read_file(abort_signal=abort_signal, **params)
        
        # 将原始 Dict 包装成协议要求的 AgentToolResult
        is_error = res.get("is_error", False)
        if res["type"] == "image":
            content = [ImageContent(data=res["content"], mime_type=res["mime"])]
        else:
            content = [TextContent(text=res["content"])]
            
        return AgentToolResult(
            content=content, 
            details={"total_lines": res.get("total_lines")},
            is_error=is_error # 【关键】：将错误状态透传给推理引擎
        )

    async def read_file(self, path: str, offset: int = 1, limit: int = 800, abort_signal: Optional[asyncio.Event] = None) -> Union[Dict, str]:
        """
        核心读取方法。
        """
        # 1. 模式分流
        if self.mode == "remote":
            # 如果是文本文件且有分页需求，我们生成高级的 wc + tail 指令
            mime = await self.driver.detect_mime_type(path)
            if mime and "image" in mime:
                return await self.driver.read_file(path, abort_signal)
            
            # 使用 RemoteShellDriver 独有的分页指令生成方案
            return self.driver.generate_pagination_command(path, offset, min(limit, self.MAX_LINES))

        # 2. 本地模式：执行精密读取与截断
        if not await self.driver.access(path):
            # 【容错加固】：不再抛出异常，而是温和地通知 Agent
            return {"type": "text", "content": f"错误：文件不存在或路径权限不足: {path}", "is_error": True}

        # 检测类型
        mime = await self.driver.detect_mime_type(path)
        is_image = mime and "image" in mime
        
        # --- 图片处理 (Multi-modal) ---
        if is_image:
            data = await self.driver.read_file(path, abort_signal)
            b64 = base64.b64encode(data).decode('utf-8')
            return {"type": "image", "content": b64, "mime": mime}

        # --- 文本分页处理 (Pagination & Safety) ---
        raw_data = await self.driver.read_file(path, abort_signal)
        # 将二进制解码为文本，忽略解码错误以防止乱码崩溃
        text = raw_data.decode('utf-8', errors='ignore')
        lines = text.splitlines()
        total_lines = len(lines)
        
        # 计算分页窗口
        start_idx = offset - 1
        end_idx = min(start_idx + min(limit, self.MAX_LINES), total_lines)
        
        selected_lines = lines[start_idx:end_idx]
        current_content = "\n".join(selected_lines)
        
        # 执行字节数限制 (Safety Truncation)
        truncated = False
        if len(current_content.encode('utf-8')) > self.MAX_BYTES:
            # 简单截字（在大项目中可进一步优化按行截断）
            current_content = current_content[:self.MAX_BYTES]
            truncated = True

        # 若读到的行没到最后，也属于截断
        if end_idx < total_lines:
            truncated = True

        # --- 生成智能反馈 (Smart Feedback) ---
        if truncated:
            next_offset = end_idx + 1
            footer = (
                f"\n\n--- [ACTION REQUIRED] ---\n"
                f"内容因安全限制（50KB或800行）被截断。\n"
                f"当前显示: {offset}-{end_idx} 行 (总计 {total_lines} 行)。\n"
                f"若需继续阅读，请回复 'read_file(path=\"{path}\", offset={next_offset})'。"
            )
            current_content += footer

        return {"type": "text", "content": current_content, "total_lines": total_lines}
