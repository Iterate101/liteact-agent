import asyncio
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Optional

from src.models.messages import TextContent
from src.tools.base import AgentTool, AgentToolResult, AgentToolUpdateCallback
from src.tools.executor.sandbox import LocalSandbox


class RunTestsTool(AgentTool):
    """Run the repository's Python unittest suite without exposing arbitrary shell execution."""

    name: str = "run_tests"
    description: str = (
        "Run Python unittest tests inside the current workspace. "
        "Use this after code edits to verify behavior without composing an arbitrary shell command."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Test directory relative to the workspace root.",
                "default": "tests",
            },
            "pattern": {
                "type": "string",
                "description": "unittest discovery pattern.",
                "default": "test*.py",
            },
            "timeout": {
                "type": "integer",
                "description": "Maximum runtime in seconds.",
                "default": 60,
            },
        },
    }

    MAX_OUTPUT_SIZE = 32 * 1024

    def __init__(self, base_path: Optional[str] = None):
        self.base_path = Path(base_path or os.getcwd()).resolve()
        self.sandbox = LocalSandbox()

    def _resolve_test_path(self, path: str) -> Path:
        normalized = (path or "tests").replace("\\", "/")
        if normalized.startswith("/workspace/"):
            normalized = normalized[len("/workspace/"):].lstrip("/")

        raw_path = Path(normalized)
        target_path = raw_path.resolve() if raw_path.is_absolute() else (self.base_path / raw_path).resolve()
        try:
            target_path.relative_to(self.base_path)
        except ValueError:
            raise ValueError(f"Test path is outside workspace: {path}")
        return target_path

    def _build_command(self, test_path: Path, pattern: str) -> str:
        args = [
            sys.executable,
            "-B",
            "-m",
            "unittest",
            "discover",
            "-s",
            str(test_path),
            "-p",
            pattern or "test*.py",
        ]
        if os.name == "nt":
            return subprocess.list2cmdline(args)
        return shlex.join(args)

    async def execute(
        self,
        tool_call_id: str,
        params: dict,
        abort_signal: Optional[asyncio.Event] = None,
        on_partial_result: Optional[AgentToolUpdateCallback] = None,
    ) -> AgentToolResult:
        path = params.get("path", "tests")
        pattern = params.get("pattern", "test*.py")
        timeout = int(params.get("timeout", 60) or 60)

        try:
            test_path = self._resolve_test_path(path)
            if not test_path.exists():
                return self._error(f"Test path does not exist: {path}")
            if not test_path.is_dir():
                return self._error("run_tests expects a test directory, not a single file.")

            command = self._build_command(test_path, pattern)
            result = await self.sandbox.exec(command, timeout=timeout, cwd=str(self.base_path))
            combined_output = result.stdout + result.stderr
            if len(combined_output) > self.MAX_OUTPUT_SIZE:
                combined_output = (
                    f"[OUTPUT TRUNCATED - Showing last {self.MAX_OUTPUT_SIZE // 1024}KB]\n"
                    f"{combined_output[-self.MAX_OUTPUT_SIZE:]}"
                )

            status = "passed" if result.exit_code == 0 and not result.timed_out else "failed"
            summary = f"run_tests {status} (exit_code={result.exit_code}, timed_out={result.timed_out})"
            text = f"{summary}\n\nCommand: {command}\n\n{combined_output}".strip()
            return AgentToolResult(
                content=[TextContent(text=text)],
                details={
                    "command": command,
                    "cwd": str(self.base_path),
                    "exit_code": result.exit_code,
                    "timed_out": result.timed_out,
                    "status": status,
                },
                is_error=status != "passed",
            )
        except Exception as exc:
            return self._error(f"run_tests failed: {exc}")

    def _error(self, message: str) -> AgentToolResult:
        return AgentToolResult(
            content=[TextContent(text=f"Error: {message}")],
            details={"status": "error"},
            is_error=True,
        )
