from typing import Protocol, Optional, runtime_checkable
import asyncio

@runtime_checkable
class ReadOperations(Protocol):
    """
    【协议层】定义读取引擎的标准契约。
    任何实现了以下方法的类都可以被视为有效的读取引擎。
    """
    
    async def read_file(self, path: str, abort_signal: Optional[asyncio.Event] = None) -> bytes:
        """读取文件完整二进制内容"""
        ...

    async def access(self, path: str) -> bool:
        """检查路径是否存在且可读"""
        ...

    async def detect_mime_type(self, path: str) -> Optional[str]:
        """检测文件的媒体类型 (MIME Type)"""
        ...
