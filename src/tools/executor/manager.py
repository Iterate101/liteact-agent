import asyncio
import os
from typing import Optional
from src.tools.executor.sandbox import Sandbox, LocalSandbox, ExecResult
from src.tools.base import AgentTool, AgentToolResult, AgentToolUpdateCallback, TextContent

class ShellExecutor(AgentTool):
    """
    【流式执行驱动 - 沙箱集成版】
    实现 AgentTool 协议。通过 Sandbox 抽象层支持本地与容器化多环境执行。
    """
    
    name: str = "execute_bash"
    description: str = (
        "在当前操作系统的本地 Shell 中执行命令，并返回输出结果。"
        "如果运行在 Windows，请优先使用 python、dir、type 等 Windows 可用命令。"
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "The command line to execute in the shell."}
        },
        "required": ["command"]
    }
    
    # 工业级截断设置：只保留最新的 32KB 数据给 Agent
    MAX_OUTPUT_SIZE = 32 * 1024 

    def __init__(self, sandbox: Optional[Sandbox] = None, cwd: Optional[str] = None):
        # 默认使用本地沙箱
        self.sandbox = sandbox or LocalSandbox()
        self.cwd = cwd

    def _normalize_command(self, command: str) -> str:
        """根据当前系统做轻量命令兼容，减少模型把 Linux 命令直接发到 Windows 的失败率"""
        if os.name != "nt":
            return command

        stripped = command.strip()
        if stripped == "python3":
            return "python"
        if stripped.startswith("python3 "):
            return "python " + stripped[len("python3 "):]
        return command

    async def execute(
        self, 
        tool_call_id: str, 
        params: dict, 
        abort_signal: Optional[asyncio.Event] = None,
        on_partial_result: Optional[AgentToolUpdateCallback] = None
    ) -> AgentToolResult:
        command = params.get("command", "")
        command = self._normalize_command(command)
        # 默认 30 秒超时，这是对 Agent 稳定性的重要保障
        timeout = params.get("timeout", 30)
        
        try:
            # 1. 委托给沙箱执行并传入 cwd
            result: ExecResult = await self.sandbox.exec(command, timeout=timeout, cwd=self.cwd)

            # 2. 实时结果上报（如果沙箱返回了输出）
            if on_partial_result and result.stdout:
                await on_partial_result(result.stdout)

            # 3. 结果汇总与截断策略
            all_output = result.stdout + result.stderr
            
            # 这里的逻辑就是 TS 中的“Tail Truncation”
            final_text = all_output
            if len(all_output) > self.MAX_OUTPUT_SIZE:
                # 保留最后的 MAX_OUTPUT_SIZE 字节
                truncated_content = all_output[-self.MAX_OUTPUT_SIZE:]
                final_text = (
                    f"[OUTPUT TRUNCATED - Showing last {self.MAX_OUTPUT_SIZE//1024}KB]\n"
                    f"... (earlier output removed) ...\n"
                    f"{truncated_content}"
                )

            # 4. 返回结构化结果
            return AgentToolResult(
                content=[TextContent(text=final_text)],
                details={
                    "exit_code": result.exit_code, 
                    "timed_out": result.timed_out,
                    "original_size": len(all_output)
                },
                is_error=result.exit_code != 0
            )

        except Exception as e:
            return AgentToolResult(
                content=[TextContent(text=f"系统级故障: {str(e)}")],
                is_error=True
            )
