import shlex
import os
import asyncio
from .base import BaseWriter

class RemoteShellDriver(BaseWriter):
    """
    【远程/沙箱驱动】
    场景：用于发送给外部环境（Docker/SSH）执行指令。
    核心：生成安全的 Bash 指令、内容转义（Escape）。
    """
    
    async def write(self, path: str, content: str, abort_signal: asyncio.Event = None) -> str:
        # 1. 检查中止信号
        self.check_abort(abort_signal)
        
        # 2. 极致转义：处理内容中的单引号等特殊字符
        # shlex.quote 会自动包裹单引号，处理 $、` 等 Shell 敏感字符
        # 这是为了防止 Shell 注入（Injection）
        safe_content = shlex.quote(content)
        
        # 3. 准备目标路径和所在目录
        # 我们同样要确保目录也得顺便创建了
        target_dir = shlex.quote(os.path.dirname(path))
        safe_path = shlex.quote(path)
        
        # 4. 生成“一次性任务”指令串
        # mkdir -p: 确保目录存在
        # printf '%s': 它是比 echo 更可靠的输出方式，原封不动地保持换行
        # >: 指向目标文件
        bash_command = (
            f"mkdir -p {target_dir} && "
            f"printf '%s' {safe_content} > {safe_path}"
        )
        
        # 注意：这个驱动不执行，只输出指令，让 Agent 决定在哪个 Shell 里运行它
        return f"[BASH_COMMAND]\n{bash_command}"
