import unittest
import sys
import os

# 加入根目录到搜索路径
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.models.ai import (
    UserMessage, AssistantMessage, ToolResultMessage,
    TextContent, ThinkingContent, ToolCall
)
from src.ai.transformer import transform_messages

class TestAITransformer(unittest.TestCase):
    
    def test_orphaned_tool_calls_fix(self):
        """测试：孤立的工具调用是否被自动补全合成结果。"""
        print("\n--- [测试 1: 孤儿调用补全验证] ---")
        
        # 准备一个“残缺”的对话流
        messages = [
            UserMessage(content="帮我做三件事"),
            AssistantMessage(
                provider="openai", model="gpt-4",
                content=[
                    TextContent(text="好的，我正在调用工具..."),
                    ToolCall(id="tc_1", name="read", arguments={}),
                    ToolCall(id="tc_2", name="write", arguments={}),
                    ToolCall(id="tc_3", name="delete", arguments={})
                ]
            ),
            # 仅仅提供了一个结果：tc_2
            ToolResultMessage(tool_call_id="tc_2", tool_name="write", content=[TextContent(text="OK")])
        ]
        
        # 进行转换
        transformed = transform_messages(messages, "gpt-4", "openai")
        
        # 验证：1 User + 1 Assistant + 1 OK Result + 2 Synthetic Results = 5
        self.assertEqual(len(transformed), 5)
        
        # 验证最后两条消息是否是自动补全的
        last_two = transformed[-2:]
        for result in last_two:
            self.assertIsInstance(result, ToolResultMessage)
            self.assertTrue(result.is_error)
            print(f"  [SUCCESS] 自动补全了缺失的结果: {result.tool_call_id} (Reason: {result.content[0].text})")

    def test_cross_model_thinking_drop(self):
        """测试：加密的推理内容在跨模型切换时是否自动剔除。"""
        print("\n--- [测试 2: 思维内容降级验证] ---")
        
        messages = [
            AssistantMessage(
                provider="high-end-provider", model="advanced-o1",
                content=[
                    # 这是一个加密的、对其它模型无意义的思考块
                    ThinkingContent(thinking="", redacted=True),
                    TextContent(text="你好")
                ]
            )
        ]
        
        # 现我们要转换给低端模型看
        transformed = transform_messages(messages, "gpt-small", "openai")
        
        # 验证：加密块应该消失，只剩文本块
        self.assertEqual(len(transformed[0].content), 1)
        self.assertEqual(transformed[0].content[0].type, "text")
        print("[SUCCESS] 加密推理内容已安全剔除。")

    def test_skip_errored_assistant_messages(self):
        """测试：异常截断的消息是否被自动隔离。"""
        print("\n--- [测试 3: 脏数据隔离验证] ---")
        
        messages = [
            UserMessage(content="你好"),
            # 这是一个因为网络错误导致的坏掉的消息
            AssistantMessage(
                provider="openai", model="gpt-4", content=[TextContent(text="我在思考...")],
                stop_reason="error"
            )
        ]
        
        transformed = transform_messages(messages, "gpt-4", "openai")
        
        # 验证：那个报错的消息应该被彻底过滤掉
        self.assertEqual(len(transformed), 1)
        self.assertEqual(transformed[0].role, "user")
        print("[SUCCESS] 异常中断的对话历史已自动隔离。")

if __name__ == "__main__":
    unittest.main()
