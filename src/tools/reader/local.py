import os
import asyncio
import mimetypes
from pathlib import Path
from typing import Optional
from .types import ReadOperations

class LocalDirectDriver(ReadOperations):
    """
    【本地直接驱动】
    实现 ReadOperations 协议。直接使用磁盘 I/O。
    """
    
    async def read_file(self, path: str, abort_signal: Optional[asyncio.Event] = None) -> bytes:
        # 1. 检查取消信号
        if abort_signal and abort_signal.is_set():
            raise asyncio.CancelledError("读取操作已中止。")
            
        p = Path(path).resolve()
        MAX_SAFE_READ = 50 * 1024  # 50KB 安全上限
        
        # 2. 采用流式读取模式 (Streaming)
        content = bytearray()
        try:
            with open(p, 'rb') as f:
                # 每次只读 8KB 缓冲区，直到达到上限或文件结束
                while len(content) < MAX_SAFE_READ:
                    chunk = f.read(8192)
                    if not chunk:
                        break
                    content.extend(chunk)
                    
                    # 在长耗时 I/O 间隙检查信号
                    if abort_signal and abort_signal.is_set():
                        raise asyncio.CancelledError()
            
            return bytes(content[:MAX_SAFE_READ])
        except Exception as e:
            raise e

    async def access(self, path: str) -> bool:
        p = Path(path).resolve()
        return p.exists() and p.is_file() and os.access(p, os.R_OK)

    async def detect_mime_type(self, path: str) -> Optional[str]:
        # mimetypes 能认出绝大多数常见的 jpg, png, gif, webp
        mime, _ = mimetypes.guess_type(path)
        return mime
