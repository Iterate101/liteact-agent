import json
import sys
import os

# 加入根目录到搜索路径
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.models.messages import (
    UserMessage, AssistantMessage, ToolCall, 
    TextContent, ToolResultMessage, AgentContext
)

def test_message_serialization():
    """验证：从 JSON 还原为 Pydantic 对象，再序列化回来"""
    print("\n--- [测试 1] 复杂对话序列化验证 ---")
    
    # 模拟一段来自 Agent 的原始 JSON (包含文本和工具请求)
    raw_json = {
        "role": "assistant",
        "content": [
            {"type": "text", "text": "好的，我为你找一下文件。"},
            {"type": "toolCall", "id": "call_123", "name": "read_file", "arguments": "{\"path\": \"test.py\"}"}
        ]
    }
    
    print("1. 原始 JSON 数据已就绪。")
    
    # --- 魔法时刻：Pydantic 自动识别并解析 ---
    # 它会根据 role 自动决定使用 AssistantMessage 类
    msg = AssistantMessage.model_validate(raw_json)
    
    print(f"2. 成功解析为对象！角色: {msg.role}")
    print(f"   工具请求名: {msg.content[1].name}") # [1] 是 ToolCall
    
    # 再次转回 JSON 字符串
    json_out = msg.model_dump_json(indent=2)
    print("3. 重新序列化后的结果:")
    print(json_out)

def test_context_validation():
    """验证：上下文管理器是否能装载不同角色的消息列表"""
    print("\n--- [测试 2] 上下文容器验证 ---")
    
    ctx = AgentContext(
        systemPrompt="你是一个 AI 编程助手。",
        messages=[
            UserMessage(content="你好！"),
            AssistantMessage(content=[TextContent(text="你好，有什么可以帮你的？")]),
            ToolResultMessage(
                toolCallId="call_abc",
                toolName="read_file",
                content=[TextContent(text="文件内容：print('hello')")]
            )
        ]
    )
    
    print(f"成功装载上下文！消息条数: {len(ctx.messages)}")
    print(f"第一条消息角色: {ctx.messages[0].role}")
    print(f"最后一条消息角色: {ctx.messages[-1].role}")

if __name__ == "__main__":
    test_message_serialization()
    test_context_validation()
