import asyncio
import sys
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

# 加入根目录到搜索路径
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.models.ai import (
    UserMessage, AssistantMessage, ToolResultMessage,
    TextDelta, ToolCallDelta, UsageEvent, TextContent
)
from src.ai.providers.openai import OpenAIProvider

# 强制设置环境编码
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

class TestOpenAIProvider(unittest.IsolatedAsyncioTestCase):
    
    async def test_message_conversion(self):
        """验证我们的统一消息格式能正确转换为 OpenAI 要求的字典。"""
        provider = OpenAIProvider(api_key="mock_key")
        
        # 准备一个包含工具结果的消息列表
        messages = [
            UserMessage(content="帮我读文件"),
            ToolResultMessage(
                tool_call_id="c1",
                tool_name="read_file",
                content=[TextContent(text="File content here")]
            )
        ]
        
        converted = provider._convert_messages(messages)
        
        print("\n--- [测试 1: 消息转换验证] ---")
        self.assertEqual(converted[0]["role"], "user")
        self.assertEqual(converted[1]["role"], "tool")
        self.assertEqual(converted[1]["tool_call_id"], "c1")
        print("[SUCCESS] AgentMessage -> OpenAI Message 映射符合规范。")

    async def test_streaming_tool_call_accumulation(self):
        """验证分片返回的工具调用参数是否能被正确累加并解析。"""
        provider = OpenAIProvider(api_key="mock_key")
        
        # 模拟 OpenAI 的 Chunks 流
        # 我们模拟三个 Chunk：第一个给 ID，第二个给参数开头，第三个给参数结尾
        mock_chunks = [
            SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=None, reasoning_content=None, tool_calls=[
                SimpleNamespace(index=0, id="call_123", function=SimpleNamespace(name="read_file", arguments=None))
            ]))], usage=None),
            
            SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=None, reasoning_content=None, tool_calls=[
                SimpleNamespace(index=0, id=None, function=SimpleNamespace(name=None, arguments='{"path": "m'))
            ]))], usage=None),
            
            SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=None, reasoning_content=None, tool_calls=[
                SimpleNamespace(index=0, id=None, function=SimpleNamespace(name=None, arguments='ain.py"}'))
            ]))], usage=None),
            
            # 最后一帧发送用量
            SimpleNamespace(choices=[], usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15))
        ]

        # 模拟 AsyncOpenAI 的返回
        mock_response = AsyncMock()
        mock_response.__aiter__.return_value = mock_chunks
        provider.client.chat.completions.create = AsyncMock(return_value=mock_response)

        print("\n--- [测试 2: 流式增量累加验证] ---")
        events = []
        async for event in provider.stream(model="gpt-4o", messages=[]):
            events.append(event)
            if isinstance(event, ToolCallDelta):
                print(f"  识别到工具调用快照: {event.tool_call.arguments}")
            elif isinstance(event, UsageEvent):
                print(f"  识别到最终结算: {event.usage.total_tokens} tokens")

        # 验证最终捕获到了完整的 JSON
        tool_events = [e for e in events if isinstance(e, ToolCallDelta)]
        self.assertTrue(len(tool_events) > 0)
        self.assertEqual(tool_events[-1].tool_call.arguments["path"], "main.py")
        print("[SUCCESS] 分片 JSON 参数累加逻辑通过。")

if __name__ == "__main__":
    unittest.main()
