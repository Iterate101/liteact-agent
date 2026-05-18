import asyncio
import os
from contextlib import asynccontextmanager

class PathLockManager:
    """
    【并发管理器】基于文件路径的全局异步锁。
    确保针对同一个物理路径的 I/O 操作是按照顺序（串行）执行的。
    """
    
    def __init__(self):
        # 记录每个路径对应的锁对象
        self._locks = {}
        # 为了保护这个字典本身不发生冲突，我们也需要一个全局锁
        self._global_lock = asyncio.Lock()

    @asynccontextmanager
    async def lock_path(self, path: str):
        """
        异步上下文管理器。
        使用方式: async with manager.lock_path('/etc/hosts'): ...
        """
        # 1. 路径规范化 (Normalization)
        # 确保 '/tmp/a.txt' 和 '/tmp/../tmp/a.txt' 能指向同一个锁
        norm_path = os.path.abspath(os.path.normpath(path))
        
        # 2. 获取或创建针对该路径的专属锁 (Mutex)
        async with self._global_lock:
            if norm_path not in self._locks:
                self._locks[norm_path] = asyncio.Lock()
            target_lock = self._locks[norm_path]
        
        # 3. 开始排队买票 (Acquire Lock)
        # 这会让第二个想写这个路径的协程在此处挂起等待
        async with target_lock:
            yield
            
# 我们在包里维护一个全局单例实例 (Singleton Pattern)
global_path_lock = PathLockManager()
