import asyncio
from typing import AsyncGenerator, Optional
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.markdown import Markdown
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text
from rich import box

from src.agent.events import (
    AgentEvent, TurnStartEvent, MessageDeltaEvent, 
    ToolCallStartEvent, ToolCallEndEvent, TurnEndEvent
)

class AgentTUI:
    """
    【极客视觉引擎】
    利用 Rich 库实现具备流式渲染能力的终端界面。
    """
    
    def __init__(self):
        # 【核心修正】：强制 UTF-8 编码，防止 Windows GBK 环境下 emoji 导致崩溃
        import sys
        if sys.stdout.encoding.lower() != 'utf-8':
            try:
                sys.stdout.reconfigure(encoding='utf-8')
            except:
                pass
        self.console = Console(force_terminal=True)
        # 内部缓存，用于拼接流式数据
        self._current_text = ""
        self._current_thinking = ""
        self._active_tools = {} # 记录正在运行的工具

    def _make_display(self) -> Panel:
        """根据当前状态构建实时显示布局"""
        
        # 1. 思考区 (Panel)
        thinking_panel = Panel(
            Text(self._current_thinking, style="italic grey50"),
            title="[bold blue]🤔 Thinking[/bold blue]",
            border_style="blue",
            box=box.ROUNDED,
            # 这里的 height 不再写死，让它随内容自适应（或按需设 max_height）
        )
        
        # 2. 状态区 (Tools)
        tool_status = Table.grid(padding=(0, 1))
        for tool_id, tool_name in self._active_tools.items():
            tool_status.add_row(Spinner("dots", text=f"Executing {tool_name}..."), Text(tool_id, style="dim"))
            
        # 3. 正文区 (Markdown)
        main_content = Markdown(self._current_text or "...")
        
        # 组装
        content_group = []
        if self._current_thinking:
            content_group.append(thinking_panel)
        content_group.append(main_content)
        if self._active_tools:
            content_group.append(Panel(tool_status, title="⚡ Tools", border_style="yellow"))
            
        # 【核心修正】：移除 Layout，直接返回 Panel。
        return Panel(
            Group(*content_group),
            title="[bold green]LiteAct Agent[/bold green]",
            border_style="green"
        )

    async def render_stream(self, event_stream: AsyncGenerator[AgentEvent, None]):
        """核心流式渲染处理器"""
        self._current_text = ""
        self._current_thinking = ""
        self._active_tools = {}
        usage_reports = []

        with Live(self._make_display(), console=self.console, refresh_per_second=10) as live:
            async for event in event_stream:
                if isinstance(event, MessageDeltaEvent):
                    if "[Thinking]" in event.content:
                        self._current_thinking += event.content.replace("[Thinking]", "").strip()
                    else:
                        self._current_text += event.content
                    live.update(self._make_display())

                elif isinstance(event, ToolCallStartEvent):
                    self._active_tools[event.tool_call_id] = event.tool_name
                    live.update(self._make_display())

                elif isinstance(event, ToolCallEndEvent):
                    if event.tool_call_id in self._active_tools:
                        del self._active_tools[event.tool_call_id]
                    live.update(self._make_display())

                elif isinstance(event, TurnEndEvent):
                    usage = getattr(event.message, "usage", None)
                    if self._has_usage_tokens(usage):
                        usage_reports.append(usage)

        # 【双重保险】：当 Live 面板关闭后，在普通控制台流中再次打印一次最终全文
        # 这确保了长文本能够融入终端的正常滚动历史中，不会被截断
        self.console.print(Markdown(self._current_text or "..."))
        self.console.print("[dim]------------------------------------------------[/dim]\n")
        if usage_reports:
            self.show_usage_summary(usage_reports)

    def _usage_value(self, usage, field: str) -> int:
        """安全读取 usage 字段，避免不同 Provider 缺字段时 UI 崩溃"""
        return int(getattr(usage, field, 0) or 0)

    def _has_usage_tokens(self, usage) -> bool:
        """判断本轮消息是否真的带有 Token 统计"""
        if not usage:
            return False
        return any(
            self._usage_value(usage, field) > 0
            for field in ("input", "output", "cache_read", "cache_write", "total_tokens")
        )

    def show_usage(self, usage):
        """显示单次模型调用的 Token 消耗报告"""
        self.show_usage_summary([usage])

    def show_usage_summary(self, usages):
        """汇总并显示本次用户请求触发的所有模型调用 Token 消耗"""
        input_tokens = sum(self._usage_value(usage, "input") for usage in usages)
        output_tokens = sum(self._usage_value(usage, "output") for usage in usages)
        cache_read = sum(self._usage_value(usage, "cache_read") for usage in usages)
        cache_write = sum(self._usage_value(usage, "cache_write") for usage in usages)
        total_tokens = sum(self._usage_value(usage, "total_tokens") for usage in usages)

        table = Table(title="💎 Usage Report", box=box.SIMPLE)
        table.add_column("Type", style="cyan")
        table.add_column("Amount", style="magenta")
        table.add_row("Model Calls", str(len(usages)))
        table.add_row("Input Tokens", str(input_tokens))
        table.add_row("Output Tokens", str(output_tokens))
        if cache_read or cache_write:
            table.add_row("Cache Read Tokens", str(cache_read))
            table.add_row("Cache Write Tokens", str(cache_write))
        table.add_row("Total Tokens", str(total_tokens))
        self.console.print(table)
