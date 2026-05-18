import asyncio
import sys
import os
from typing import Optional
from rich.prompt import Prompt
from rich.console import Console
from rich.panel import Panel

# 对齐导入路径
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from src.agent.app import AgentSession
from src.ui.tui import AgentTUI

def build_cli_system_prompt() -> str:
    """构造 CLI 专用系统提示词，告诉模型当前真实命令环境"""
    if os.name == "nt":
        return (
            "你是 LiteAct，一个运行在 Windows 工作区中的 Coding Agent。\n"
            "当你需要执行命令时，请使用 execute_bash 工具。\n"
            "当前 Shell 是 Windows 命令环境：运行 Python 文件请使用 `python file.py`，不要使用 `python3 file.py`。\n"
            "查看目录请使用 `dir`，查看文件请使用 `type file.py`，不要使用 `ls`、`head`、`cat`、`which` 这类 Unix 命令。\n"
            "如果工具返回 exit_code=9009，通常表示命令不存在，请换成 Windows 可用命令重试。\n"
        )
    return (
        "你是 LiteAct，一个运行在本地工作区中的 Coding Agent。\n"
        "当你需要执行命令时，请使用 execute_bash 工具，并根据当前操作系统选择可用命令。\n"
    )

async def main():
    # 【核心修正】：强制 UTF-8，确保能显示火箭 🚀 等极客图标
    if sys.stdout.encoding.lower() != 'utf-8':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except:
            pass
    console = Console(force_terminal=True)
    console.print("\n[bold green]🚀 LiteAct Agent 启动！[/bold green]\n", justify="center")
    
    # 1. 动态自适应模式 (Auto-Adaptive Mode)
    # 默认优先检测通义千问，也允许通过 API_TYPE 显式指定模型供应商。
    ds_key = os.environ.get("DASHSCOPE_API_KEY")
    oa_key = os.environ.get("OPENAI_API_KEY")
    api_type_override = os.environ.get("API_TYPE", "").strip()
    
    api_type = api_type_override or ("dashscope" if ds_key else "openai-responses")
    model_id = os.environ.get("MODEL_ID") or ("qwen-max" if api_type == "dashscope" else "gpt-4o")
    session_id = os.environ.get("SESSION_ID") or ("qwen_session" if api_type == "dashscope" else "default_cli")

    if api_type == "dashscope" and not ds_key:
        console.print("[bold yellow][Warning][/bold yellow] 当前 API_TYPE=dashscope，但未检测到 DASHSCOPE_API_KEY。")
        console.print("请设置: [bold cyan]$env:DASHSCOPE_API_KEY=\"...\"[/bold cyan]")
        return
    if api_type == "openai-responses" and not oa_key:
        console.print("[bold yellow][Warning][/bold yellow] 当前 API_TYPE=openai-responses，但未检测到 OPENAI_API_KEY。")
        console.print("请设置: [bold cyan]$env:OPENAI_API_KEY=\"...\"[/bold cyan]")
        return
    if not ds_key and not oa_key:
        console.print("[bold yellow][Warning][/bold yellow] 未检测到 API Key。")
        console.print("通义千问需: [bold cyan]$env:DASHSCOPE_API_KEY=\"...\"[/bold cyan]")
        console.print("或者 OpenAI 需: [bold cyan]$env:OPENAI_API_KEY=\"...\"[/bold cyan]")
        return
    
    # 2. 实例化视觉手脚与记忆大脑
    tui = AgentTUI()
    session = AgentSession(
        session_id=session_id, 
        storage_path="sessions",
        model_id=model_id,
        api_type=api_type,
        system_prompt=build_cli_system_prompt()
    )

    console.print(f"[dim]已加载会话: {session_id} | 当前模型驱动: {api_type} ({model_id})[/dim]\n")

    # 4. 对话无限循环
    while True:
        try:
            # 使用 Rich 的 Prompt 引导用户输入
            user_input = Prompt.ask("\n[bold cyan]User[/bold cyan]")
            normalized_input = user_input.strip().lower()
            
            if normalized_input in ["q", "exit", "quit", "退出"]:
                console.print("[yellow]感谢使用 LiteAct，江湖再见！[/yellow]")
                break
            
            if not normalized_input:
                continue

            # 5. 驱动 ReAct 推理流，并将流交给 TUI 渲染
            # 这里调用了我们之前集成的 AgentSession.prompt()
            # 它内部会自动：加载历史 -> Transformer 修补 -> stream_chat 调用 -> 工具执行 -> 持久化
            await tui.render_stream(session.prompt(user_input))

        except KeyboardInterrupt:
            console.print("\n[yellow]程序已手动中断。[/yellow]")
            break
        except Exception as e:
            import traceback
            console.print(f"\n[bold red][Crash][/bold red] 发生了意外错误: {repr(e)}")
            console.print(Panel(traceback.format_exc(), title="Traceback", border_style="red"))
            break

if __name__ == "__main__":
    # Windows 环境下的异步事件循环处理（防止退出报错）
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
