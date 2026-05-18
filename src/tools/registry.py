from typing import Callable, Dict

from src.tools.base import AgentTool
from src.tools.editor.manager import FileEditManager
from src.tools.executor.manager import ShellExecutor
from src.tools.reader.manager import FileReadManager
from src.tools.writer.manager import FileWriteManager


# 默认工具工厂表是 ReActLoop 的内置工具来源。
# 用工厂而不是复用同一个实例，是为了让每个 ReActLoop 都有独立的工具状态。
DefaultToolFactory = Callable[[], AgentTool]

DEFAULT_TOOL_FACTORIES: Dict[str, DefaultToolFactory] = {
    "read_file": FileReadManager,
    "write_file": FileWriteManager,
    "edit_file": FileEditManager,
    "execute_bash": ShellExecutor,
}


def build_default_tools() -> Dict[str, AgentTool]:
    """创建 LiteAct Agent 默认启用的本地工具集。"""
    return {
        tool_name: factory()
        for tool_name, factory in DEFAULT_TOOL_FACTORIES.items()
    }
