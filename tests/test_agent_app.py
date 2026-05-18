import asyncio
import sys
import os
import json
import pytest

# 加入根目录到搜索路径
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.agent.app import AgentSession
from src.agent.events import TurnEndEvent, ToolCallStartEvent, ToolCallEndEvent

# 强制设置环境编码
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

@pytest.mark.live_e2e
@pytest.mark.skipif(
    os.environ.get("LITEACT_RUN_LIVE_E2E") != "1",
    reason="需要显式设置 LITEACT_RUN_LIVE_E2E=1 才运行真实模型端到端测试。",
)
async def test_agent_session_e2e():
    print("\n--- [端到端集成测试] AgentSession Facade ---")
    
    # 1. 初始化会话管理
    session_id = "test_e2e"
    storage_path = "tests/sessions"
    
    # 如果存在历史记录，清理干净，每次从头开始测试
    if os.path.exists(f"{storage_path}/{session_id}.jsonl"):
        os.remove(f"{storage_path}/{session_id}.jsonl")
        
    session = AgentSession(session_id, storage_path)
    
    print(f"会话已启动，ID: {session_id}")
    
    # 2. 发起第一轮任务
    print("\n[第一步] 用户发起任务：'分析并写笔记'...")
    event_count = 0
    async for event in session.prompt("分析并写笔记"):
        event_count += 1
        if isinstance(event, ToolCallStartEvent):
            print(f"  [事件广播] 工具开始执行: {event.tool_name} (ID: {event.tool_call_id})")
        elif isinstance(event, ToolCallEndEvent):
            print(f"  [事件广播] 工具执行完毕: (ID: {event.tool_call_id})")
        elif isinstance(event, TurnEndEvent):
            print(f"  [事件广播] 轮次推理结束，AI 说了: {event.message.content[0].text[:20]}...")

    # 3. 验证持久化层是否“雁过留痕”
    print("\n[第二步] 物理层持久化校验...")
    session_file = f"{storage_path}/{session_id}.jsonl"
    if os.path.exists(session_file):
        with open(session_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            print(f"  找到持久化文件，共记录了 {len(lines)} 条历史项目 (JSONL)。")
            
            # 第一行总是 SessionHeader
            # 后续应该是 UserMessage, ToolResult, AssistantMessage...
            roles = []
            for line in lines[1:]: # 跳过 Header
                entry = json.loads(line)
                if "message" in entry:
                    roles.append(entry["message"]["role"])
            
            print(f"  消息路径: {' -> '.join(roles)}")
            
            if "user" in roles and "assistant" in roles:
                print("[SUCCESS] 上下文链路完整且成功落盘。")
            else:
                print("[FAIL] 链路缺失： user 或 assistant 角色数据未持久化。")
    else:
        print("[FAIL] 找不到持久化文件，Agent 失去了记忆！")

if __name__ == "__main__":
    asyncio.run(test_agent_session_e2e())
