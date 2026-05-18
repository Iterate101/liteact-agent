import asyncio
import sys
import os

# 加入根目录到搜索路径
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.models.messages import AgentContext
from src.agent.loop import ReActLoop

# 解决 Windows 终端编码问题
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

async def main():
    print("\n--- [核心心脏压力测试] Agent ReAct Loop ---")
    
    # 初始化对话上下文
    ctx = AgentContext(
        systemPrompt="你是一个 AI 编程专家。",
        messages=[]
    )
    
    # 启动推理循环
    loop_engine = ReActLoop()
    
    print("AI 正在起搏，准备进入自动驾驶模式...")
    
    # 异步迭代生成器发出的每一个事件 (Event Streaming)
    async for event in loop_engine.run_loop(ctx, max_turns=3):
        # 根据事件类型，打印出带有视觉反馈的日志
        if event.type == "turn_start":
            print("\n[STEP] --- 新的回合开启 ---")
            
        elif event.type == "message_delta":
            # 模拟终端流式打印文字
            print(f"> {event.content}")
            
        elif event.type == "tool_call_start":
            print(f"🛠️  启动工具: {event.tool_name} (ID: {event.tool_call_id})")
            print(f"   参数: {event.arguments}")
            
        elif event.type == "tool_call_end":
            print(f"✅ 工具执行完毕 (ID: {event.tool_call_id})")
            
        elif event.type == "turn_end":
            print("[DONE] 本轮对话结束。")

    print("\n--- [状态验证] 对话历史记录 ---")
    print(f"最终上下文消息条数: {len(ctx.messages)}")
    for i, m in enumerate(ctx.messages):
        print(f"[{i}] {m.role} 说: {str(m.content)[:60]}...")

    # 最后一点儿扫尾：清理模拟测试产生的 memo.txt
    if os.path.exists("memo.txt"):
        os.remove("memo.txt")

if __name__ == "__main__":
    asyncio.run(main())
