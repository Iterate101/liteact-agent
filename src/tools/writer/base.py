from abc import ABC, abstractmethod
import asyncio

class BaseWriter(ABC):
    """
    【工具定义层】写入驱动的基类。
    所有具体的写入策略（本地或远程）都必须继承此类。
    """
    
    @abstractmethod
    async def write(self, path: str, content: str, abort_signal: asyncio.Event = None) -> str:
        """
        抽象写入接口。
        :param path: 目标路径
        :param content: 写入内容
        :param abort_signal: 中止信号 (asyncio.Event)，如果 set() 则立即中断
        :return: 成功信息或生成的命令
        """
        pass

    def check_abort(self, abort_signal: asyncio.Event):
        """
        辅助方法：检查信号量是否已中止。
        在大项目中，这种反复调用的检查逻辑最好写成通用的。
        """
        if abort_signal and abort_signal.is_set():
            # 抛出 asyncio 原生的取消异常，这能让整个链条都感知到中断
            raise asyncio.CancelledError("操作已由中止信号取消。")
