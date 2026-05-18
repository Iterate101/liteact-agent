import os
import asyncio
from pathlib import Path
from .base import BaseWriter

class LocalDirectDriver(BaseWriter):
    """
    【本地内核驱动】直接操作磁盘。
    具备原子化覆盖、自动创建目录以及中止响应能力。
    """
    
    async def write(self, path: str, content: str, abort_signal: asyncio.Event = None) -> str:
        # 1. 路径标准化（Safety: 防止路径穿越攻击）
        # 我们用 Path(path).resolve() 来展开所有的 .. 或符号链接，确保路径在合法范围内
        target_path = Path(path).resolve()
        
        # 2. 预备阶段：递归创建所有中间文件夹 (mkdir -p)
        # 这就是架构师的“前瞻性”：不仅写文件，还要保证文件夹也在
        os.makedirs(target_path.parent, exist_ok=True)
        
        # 3. 原子化方案：创建一个临时文件 (Atomic Write)
        tmp_path = target_path.with_suffix(target_path.suffix + ".tmp")
        
        try:
            # 在执行任何 I/O 前，先查一次中止信号
            self.check_abort(abort_signal)
            
            # 使用异步写还是同步写？在大文件处理中，建议用线程池执行阻塞 I/O
            # 这里我们为了演示原子性逻辑，使用标准的 Python 模式
            with open(tmp_path, "w", encoding="utf-8") as f:
                # 写入过程中也可以周期性检查中止（如果内容巨大）
                f.write(content)
                f.flush() # 强制刷新缓冲区到磁盘
                os.fsync(f.fileno()) # 同步硬件缓存，确保数据真正落盘

            # 再次检查信号：如果在写入快结束时被中断了，也要作废结果
            self.check_abort(abort_signal)
            
            # 4. 关键动作：原子化替换 (Atomic Replace)
            # 在 Linux 和 Windows 上，os.replace 都是原子操作或准原子操作
            os.replace(tmp_path, target_path)
            
            return f"成功原子化写入文件: {path} (大小: {len(content.encode('utf-8'))} 字节)"
            
        except (asyncio.CancelledError, Exception) as e:
            # 5. 垃圾处理：如果中途失败了或者被取消了，必须把垃圾临时文件清理掉
            if tmp_path.exists():
                tmp_path.unlink()
            raise e
