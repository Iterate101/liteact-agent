import asyncio
import sys
import os
from typing import AsyncGenerator

# 加入根目录到搜索路径
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.ui.tui import AgentTUI
from src.agent.events import (
    TurnStartEvent, MessageDeltaEvent, 
    ToolCallStartEvent, ToolCallEndEvent, TurnEndEvent
)
from src.models.ai import AssistantMessage, TextContent, Usage

async def mock_event_stream() -> AsyncGenerator[any, None]:
    """模拟一个包含思考、正文和工具调用的复杂事件流"""
    yield TurnStartEvent()
    
    # 1. 模拟流式推理内容 (Thinking)
    thoughts = ["我在思考这个问题...", "我认为需要检查本地文件...", "准备调用 read_file 工具。"]
    for t in thoughts:
        await asyncio.sleep(0.3) # 模拟网络延迟
        yield MessageDeltaEvent(content=f"[Thinking] {t}")
    
    # 2. 模拟正文 Markdown
    body = ["\n## 代码审计报告\n", "经过分析，发现 `app.py` 逻辑正常。", "我现在去读取配置文件。"]
    for b in body:
        await asyncio.sleep(0.3)
        yield MessageDeltaEvent(content=b)
    
    # 3. 模拟工具调用 (Live Spinner 会出现)
    yield ToolCallStartEvent(tool_call_id="tc_01", tool_name="read_file", arguments="{}")
    await asyncio.sleep(1.0)
    yield ToolCallEndEvent(tool_call_id="tc_01", result="File content: config=123", is_error=False)
    
    # 4. 汇总
    yield MessageDeltaEvent(content="\n\n任务已完成！")
    yield TurnEndEvent(message=AssistantMessage(
        content=[TextContent(text="任务已完成！")],
        usage=Usage(input=12, output=8, total_tokens=20),
        model="mock-model",
        provider="mock-provider"
    ))

async def test_ui():
    print("--- [UI 视觉验收测试] ---")
    tui = AgentTUI()
    # 驱动渲染
    await tui.render_stream(mock_event_stream())
    print("\n[SUCCESS] UI 渲染闭环验证通过！没有发生 Pydantic/Rich 异常。")

if __name__ == "__main__":
    asyncio.run(test_ui())
