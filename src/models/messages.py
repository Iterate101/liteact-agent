# 这个文件现在只是 src.models.ai 的一个别名映射，
# 以确保所有旧代码不需要修改导入路径也能正常运行。
# 所有的核心定义现在都转移到了 src/models/ai.py 中。

from .ai import (
    TextContent, 
    ImageContent, 
    ToolCall, 
    UserMessage, 
    AssistantMessage, 
    ToolResultMessage, 
    AgentMessage, 
    AgentContext
)
