import asyncio
import os
import sys
from pathlib import Path

# 路径自适应
sys.path.append(os.getcwd())

from src.agent.memory_manager import MemoryManager
from src.models.ai import UserMessage, AssistantMessage, TextContent

async def test_memory_logic():
    test_db = "sessions/test_channel.jsonl"
    test_md = "sessions/BOOTSTRAP.md"
    
    # 清理旧数据
    if os.path.exists(test_db): os.remove(test_db)
    Path(test_md).write_text("# 核心指令\n- 永远以中文回复\n- 你是 LiteAct 助手", encoding="utf-8")

    manager = MemoryManager(test_db, test_md)
    
    print("--- 场景 1: 引导加载验证 ---")
    bootstrap = manager.load_bootstrap()
    print(f"✅ 成功加载引导内容: {bootstrap[0].content}")

    print("\n--- 场景 2: 消息链回溯验证 ---")
    # 模拟三次对话
    m1 = UserMessage(role="user", content="你是谁？")
    manager.append(m1)
    
    m2 = AssistantMessage(role="assistant", content=[TextContent(text="我是 LiteAct。")])
    manager.append(m2)
    
    m3 = UserMessage(role="user", content="你能帮我写代码吗？")
    manager.append(m3)
    
    chain = manager.get_context_chain()
    print(f"回溯链路深度: {len(chain)}")
    for i, m in enumerate(chain):
        print(f"  [{i}] {m.role}: {m.content}")

    print("\n--- 场景 3: LLM 自动历史压缩验证 ---")
    # 凑够 25 条消息
    for i in range(22):
        manager.append(UserMessage(role="user", content=f"测试消息 {i}"))
    
    # 模拟 LLM 摘要函数
    async def mock_summarizer(history):
        return f"此前已经进行了 {len(history)} 次测试对话，用户正在压力测试系统中。"

    await manager.compact_history(mock_summarizer, threshold=20)
    
    # 检查新生成的链路
    final_chain = manager.get_context_chain()
    print(f"压缩后链路深度: {len(final_chain)}")
    print(f"第一条消息类型: {final_chain[0].msg_type}")
    print(f"第一条内容摘要: {final_chain[0].content[0].text}")

if __name__ == "__main__":
    asyncio.run(test_memory_logic())
