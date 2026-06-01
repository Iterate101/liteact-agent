import os
import asyncio
import time
from pathlib import Path
from typing import Literal, Optional
from .local import LocalDirectDriver
from .remote import RemoteShellDriver
from src.utils.lock_manager import global_path_lock
from src.tools.base import AgentTool, AgentToolResult, AgentToolUpdateCallback
from src.tools.checkpoint import PatchCheckpointStore
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
        self.mode = mode
        self.checkpoints = PatchCheckpointStore(base_path)
        if mode == "local":
            self.driver = LocalDirectDriver()
        else:
            self.driver = RemoteShellDriver()

    def _resolve_target_path(self, path: str) -> str:
        if not self.base_path:
            return path

        base = Path(self.base_path).resolve()
        normalized = (path or "").replace("\\", "/")
        if normalized.startswith("/workspace/"):
            rel_path = normalized[len("/workspace/"):].lstrip("/")
            target_path = (base / rel_path).resolve()
        else:
            raw_path = Path(path)
            target_path = raw_path.resolve() if raw_path.is_absolute() else (base / raw_path).resolve()

        try:
            target_path.relative_to(base)
        except ValueError:
            raise ValueError(f"路径越界：{path} 不在工作区 {base} 内。")

        return str(target_path)
            
    async def execute(
        self, 
        tool_call_id: str, 
        params: dict, 
        abort_signal: Optional[asyncio.Event] = None,
        on_partial_result: Optional[AgentToolUpdateCallback] = None
    ) -> AgentToolResult:
        """统一执行入口"""
        path = params.get("path", "")
        
        if self.base_path:
            try:
                params = dict(params)
                params["path"] = self._resolve_target_path(path)
            except Exception as e:
                return AgentToolResult(
                    content=[TextContent(text=f"错误：{str(e)}")],
                    details={"status": "error"},
                    is_error=True,
                )

        res = await self.write_file(abort_signal=abort_signal, **params)
        is_error = not res.get("success", False)
        error_msg = res.get("error", "")
        result_text = res.get("result", "写入完成")
        
        return AgentToolResult(
            content=[TextContent(text=error_msg if is_error else str(result_text))],
            details=res.get("details", {"status": "error" if is_error else "success"}),
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
            checkpoint = None
            
            # 2. 调度执行！
            try:
                if self.mode == "local":
                    checkpoint = self.checkpoints.create_checkpoint(
                        target_path=Path(path),
                        tool_name=self.name,
                    )
                result = await self.driver.write(path, content, abort_signal)
                if checkpoint is not None:
                    checkpoint = self.checkpoints.finalize_checkpoint(
                        checkpoint_id=checkpoint["checkpoint_id"],
                        target_path=Path(path),
                    )
                
                # 3. 统计并反馈 (Detailed Feedback)
                duration = time.time() - start_time
                bytes_count = len(content.encode('utf-8'))
                
                print(f"[LOG] File Written: {path} | Size: {bytes_count}B | Duration: {duration:.4f}s")
                details = {
                    "status": "success",
                    "bytes": bytes_count,
                    "duration_sec": round(duration, 4),
                }
                if checkpoint is not None:
                    details.update(
                        {
                            "checkpoint_id": checkpoint["checkpoint_id"],
                            "before_sha256": checkpoint["before_sha256"],
                            "after_sha256": checkpoint["after_sha256"],
                            "rollback_tool": "rollback_file",
                            "rollback_args": {"checkpoint_id": checkpoint["checkpoint_id"]},
                        }
                    )
                return {"success": True, "result": result, "details": details}
                
            except asyncio.CancelledError:
                print(f"[WAR] Write aborted for path: {path}")
                return {"success": False, "error": "写入被中止"}
            except Exception as e:
                # 完善的分类报错
                print(f"[ERR] Write failed for path: {path} | Reason: {str(e)}")
                return {"success": False, "error": f"文件系统写入异常: {str(e)}"}
