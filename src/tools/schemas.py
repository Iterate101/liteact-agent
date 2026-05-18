from typing import Any, Dict, List

from src.tools.base import AgentTool
from src.tools.registry import build_default_tools


def to_openai_tool_schema(name: str, tool: AgentTool) -> Dict[str, Any]:
    """
    将项目内部的 AgentTool 转成 OpenAI tools schema。

    这里不再手写每个工具的参数说明，而是直接读取工具类自己的
    description 和 parameters。这样工具实现和工具说明不会维护两份。
    """
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": tool.description,
            "parameters": tool.parameters,
        },
    }


# schemas.py 保留为兼容入口，但数据来源统一改成默认工具注册表。
# 这样旧代码仍然可以导入 TOOLS_DEFINITIONS，同时避免静态 schema 和真实工具漂移。
_DEFAULT_TOOLS = build_default_tools()
TOOLS_DEFINITIONS_BY_NAME: Dict[str, Dict[str, Any]] = {
    name: to_openai_tool_schema(name, tool)
    for name, tool in _DEFAULT_TOOLS.items()
}

READ_FILE_SCHEMA = TOOLS_DEFINITIONS_BY_NAME["read_file"]
WRITE_FILE_SCHEMA = TOOLS_DEFINITIONS_BY_NAME["write_file"]
EDIT_FILE_SCHEMA = TOOLS_DEFINITIONS_BY_NAME["edit_file"]
EXECUTE_BASH_SCHEMA = TOOLS_DEFINITIONS_BY_NAME["execute_bash"]

TOOLS_DEFINITIONS: List[Dict[str, Any]] = list(TOOLS_DEFINITIONS_BY_NAME.values())
