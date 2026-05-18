import os
import asyncio
import time
from typing import Literal, Optional
from .local import LocalDirectDriver
from .remote import RemoteShellDriver
from src.utils.lock_manager import global_path_lock
from src.tools.base import AgentTool, AgentToolResult, AgentToolUpdateCallback
from src.models.messages import TextContent

class FileWriteManager(AgentTool):
    """
    【总指挥部】管理所有写入逻辑。
    实现 AgentTool 协议。
    """
    
    name: str = "write_file"
    description: str = "将文本内容原子化地写入文件，支持高并发锁。"
    parameters: dict = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "The path to the file to write."},
            "content": {"type": "string", "description": "The text content to write to the file."}
        },
        "required": ["path", "content"]
    }

    def __init__(self, mode: Literal["local", "remote"] = "local", base_path: Optional[str] = None):
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
        """统一执行入口"""
        path = params.get("path", "")
        
        # 【沙箱加固逻辑】：将虚拟的 /workspace/ 转译为真实的宿主机路径
        if self.base_path and path.startswith("/workspace/"):
            rel_path = path[len("/workspace/"):].lstrip("/")
            params["path"] = os.path.join(self.base_path, rel_path)
            print(f"DEBUG: [沙箱转译] {path} -> {params['path']}")

        res = await self.write_file(abort_signal=abort_signal, **params)
        is_error = not res.get("success", False)
        error_msg = res.get("error", "")
        result_text = res.get("result", "写入完成")
        
        return AgentToolResult(
            content=[TextContent(text=error_msg if is_error else str(result_text))],
            is_error=is_error
        )
            
    async def write_file(self, path: str, content: str, abort_signal: asyncio.Event = None):
        """
        统一的写入入口。
        """
        # 1. 进行高并发排队 (Serialization)
        # 只有当前路径在没有人修改的情况下，我们才会继续推进
        async with global_path_lock.lock_path(path):
            start_time = time.time()
            
            # 2. 调度执行！
            try:
                result = await self.driver.write(path, content, abort_signal)
                
                # 3. 统计并反馈 (Detailed Feedback)
                duration = time.time() - start_time
                bytes_count = len(content.encode('utf-8'))
                
                print(f"[LOG] File Written: {path} | Size: {bytes_count}B | Duration: {duration:.4f}s")
                return {"success": True, "result": result}
                
            except asyncio.CancelledError:
                print(f"[WAR] Write aborted for path: {path}")
                return {"success": False, "error": "写入被中止"}
            except Exception as e:
                # 完善的分类报错
                print(f"[ERR] Write failed for path: {path} | Reason: {str(e)}")
                return {"success": False, "error": f"文件系统写入异常: {str(e)}"}
