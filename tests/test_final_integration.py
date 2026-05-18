import asyncio
import sys
import os
import json
from unittest.mock import AsyncMock, patch

# 加入根目录到搜索路径
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.agent.app import AgentSession
from src.agent.events import TurnEndEvent, MessageDeltaEvent, ToolCallEndEvent
from src.models.ai import TextDelta, ThinkingDelta, ToolCallDelta, UsageEvent, ToolCall, Usage

# 强制设置环境编码
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

async def test_agent_final_integration():
    print("\n--- [最终集成验收] LiteAct Full E2E Chain ---")
    
    # 1. 初始化
    session_id = "final_e2e"
    storage_path = "tests/sessions"
    session_file = f"{storage_path}/{session_id}.jsonl"
    if os.path.exists(session_file):
        os.remove(session_file)
        
    session = AgentSession(session_id, storage_path, model_id="gpt-4o")

    # 2. 模拟真实大模型的流式返回序列
    # 第一回合：思考 -> 请求读文件
    mock_events_1 = [
        ThinkingDelta(delta="我在思考..."),
        TextDelta(delta="我来读取一下目录。"),
        ToolCallDelta(tool_call=ToolCall(id="tc_read", name="read_file", arguments={"path": "src/agent/app.py", "limit": 5})),
        UsageEvent(usage=Usage(input=10, output=5, total_tokens=15))
    ]
    # 第二回合：告知任务完成
    mock_events_2 = [
        TextDelta(delta="我已经看过了，一切正常。"),
        UsageEvent(usage=Usage(input=20, output=10, total_tokens=30))
    ]

    # 我们通过 Patch 拦截 stream_chat，让它返回我们预设的流
    async def mock_ai_stream(*args, **kwargs):
        # 简单根据消息轮数返回不同的流
        messages = kwargs.get("messages", [])
        if len(messages) <= 2: # 包含 system 和 第一条 user
            for ev in mock_events_1: yield ev
        else:
            for ev in mock_events_2: yield ev

    print("\n[第一步] 模拟 AI 推理与工具回调...")
    with patch("src.agent.loop.stream_chat", side_effect=mock_ai_stream):
        async for event in session.prompt("请帮我进行代码审计"):
            if isinstance(event, MessageDeltaEvent):
                # 如果是思考内容，我们特殊标记打印
                if "[Thinking]" in event.content:
                    print(f"  [前端感知] AI 推理中: {event.content.replace('[Thinking]', '').strip()}")
                else:
                    print(f"  [前端感知] AI 回复中: {event.content}")
            elif isinstance(event, ToolCallEndEvent):
                print(f"  [后端感知] 工具执行完成: {event.tool_call_id}")
            elif isinstance(event, TurnEndEvent):
                print("  [回合结束] 当前轮次推理完毕。")

    # 3. 物理层深度校验
    print("\n[第二步] 物理存储与结构化校验...")
    if os.path.exists(session_file):
        with open(session_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            print(f"  找到持久化记忆文件，共记录了 {len(lines)} 条历史记录。")
            
            # 解析最后一条消息（Assistant）确认它不仅有 text，还有 thinking
            last_msg_entry = json.loads(lines[-1])
            if last_msg_entry["type"] == "message":
                msg = last_msg_entry["message"]
                print(f"  最新的消息角色为: {msg['role']}")
                
                # 统计内容块
                types = [c["type"] for c in msg["content"]]
                print(f"  消息包含的内容块类型: {', '.join(types)}")
                
                if "thinking" in types and "text" in types:
                    print("[SUCCESS] 思考链与文本链已成功通过多态协议持久化！")
    else:
        print("[FAIL] 持久化失败！")

if __name__ == "__main__":
    asyncio.run(test_agent_final_integration())
