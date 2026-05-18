import sys
import os
import json
from pydantic import TypeAdapter

# 加入根目录到搜索路径
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.models.ai import (
    UserMessage, AssistantMessage, AgentMessage, 
    TextDelta, ThinkingDelta, ToolCallDelta, UsageEvent, StreamEvent
)

def test_message_polymorphism():
    print("\n--- [1. 消息多态解析测试] ---")
    
    # 模拟从数据库或日志中读取的原始字典列表
    raw_data = [
        {
            "role": "user",
            "content": "帮我看看这个代码",
            "timestamp": 12345
        },
        {
            "role": "assistant",
            "content": [
                {"type": "thinking", "thinking": "用户需要代码审查..."},
                {"type": "text", "text": "好的，我看了一下。"},
                {"type": "toolCall", "id": "tc_1", "name": "read_file", "arguments": {"path": "main.py"}}
            ],
            "model": "claude-3-5-sonnet",
            "provider": "anthropic"
        }
    ]

    # 使用 Pydantic 的 TypeAdapter 批量解析
    adapter = TypeAdapter(list[AgentMessage])
    messages = adapter.validate_python(raw_data)
    
    print(f"解析成功！共识别出 {len(messages)} 条消息。")
    print(f"第 1 条是: {type(messages[0]).__name__} (角色: {messages[0].role})")
    print(f"第 2 条是: {type(messages[1]).__name__} (包含 {len(messages[1].content)} 个内容块)")
    
    # 验证嵌套的 ToolCall
    last_block = messages[1].content[-1]
    if last_block.type == "toolCall":
        print(f"成功识别工具请求: {last_block.name}(arguments={last_block.arguments})")

def test_stream_event_unification():
    print("\n--- [2. 统一流式事件解析测试] ---")
    
    # 模拟四个不同类型的流式事件帧
    events_mock = [
        {"type": "text", "delta": "Hello"},
        {"type": "thinking", "delta": "Thinking process..."},
        {"type": "tool_call", "tool_call": {"id": "c1", "name": "bash", "arguments": {"cmd": "ls"}}},
        {"type": "usage", "usage": {"input": 100, "output": 50, "total_tokens": 150}}
    ]
    
    adapter = TypeAdapter(list[StreamEvent])
    parsed_events = adapter.validate_python(events_mock)
    
    for i, ev in enumerate(parsed_events):
        print(f"帧 {i+1} 类型: {ev.type} -> 解析为: {type(ev).__name__}")
        if ev.type == "text":
            print(f"  内容: {ev.delta}")
        elif ev.type == "usage":
            print(f"  结算: 总计 {ev.usage.total_tokens} tokens")

if __name__ == "__main__":
    try:
        test_message_polymorphism()
        test_stream_event_unification()
        print("\n[SUCCESS] AI 协议契约完全对齐，严谨性验证通过！")
    except Exception as e:
        print(f"\n[FAIL] 契约解析失败: {str(e)}")
