import shlex
import asyncio
import mimetypes
from typing import Optional
from .types import ReadOperations

class RemoteShellDriver(ReadOperations):
    """
    【远程/指令驱动】
    实现 ReadOperations 协议。
    核心：生成安全的 Bash 指令，由外部 Agent 在其它环境中执行。
    """
    
    async def read_file(self, path: str, abort_signal: Optional[asyncio.Event] = None) -> str:
        # 特别注意：远程读取器返回的是一段“待执行指令”字符串，而非二进制内容本身
        safe_path = shlex.quote(path)
        
        # 我们根据常见的后缀来判断是文本还是图片
        mime, _ = mimetypes.guess_type(path)
        is_image = mime and any(x in mime for x in ['jpg', 'png', 'webp', 'gif', 'jpeg'])
        
        if is_image:
            # 图片使用 base64 指令转换输出
            return f"cat {safe_path} | base64"
        else:
            # 文本使用标准的 cat (分页逻辑由 Manager 层拼装指令)
            return f"cat {safe_path}"

    async def access(self, path: str) -> str:
        # 生成检查指令
        safe_path = shlex.quote(path)
        return f"test -f {safe_path} && echo 'EXISTS'"

    async def detect_mime_type(self, path: str) -> Optional[str]:
        # 远程环境下，驱动层返回静态猜测，真正精准探测可后续通过 file 指令实现
        mime, _ = mimetypes.guess_type(path)
        return mime

    def generate_pagination_command(self, path: str, offset: int, limit: int) -> str:
        """
        专门为分页生成的 Bash 指令。
        tail -n +X: 从第 X 行开始
        head -n Y: 只读前 Y 行
        """
        safe_path = shlex.quote(path)
        return f"wc -l {safe_path} && tail -n +{offset} {safe_path} | head -n {limit}"
