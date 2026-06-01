import asyncio
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.agent.app import AgentSession
from src.agent.events import FinalEvent, PlanEvent, StepStartEvent, ToolCallEndEvent, VerificationEvent
from src.agent.loop import ReActLoop
from src.agent.trace import find_latest_trace, format_trace_summary, summarize_trace_file
from src.models.ai import TextDelta, Usage, UsageEvent
from src.models.messages import TextContent
from src.tools.schemas import TOOLS_DEFINITIONS
from src.tools.editor.manager import FileEditManager
from src.tools.rollback.manager import RollbackFileManager
from src.tools.writer.manager import FileWriteManager
from src.ui.tui import AgentTUI


class TestRuntimeTraceAndTools(unittest.IsolatedAsyncioTestCase):
    async def test_agent_session_writes_task_trace(self):
        async def fake_stream(*args, **kwargs):
            yield TextDelta(delta="Trace ready.")
            yield UsageEvent(usage=Usage(input=1, output=2, total_tokens=3))

        with tempfile.TemporaryDirectory() as tmpdir:
            session = AgentSession(
                session_id="trace_test",
                storage_path=tmpdir,
                model_id="fake-model",
                api_type="fake-provider",
                system_prompt="test",
            )

            seen_types = []
            with patch("src.agent.loop.stream_chat", side_effect=fake_stream):
                async for event in session.prompt("say hello"):
                    seen_types.append(type(event))

            self.assertIn(PlanEvent, seen_types)
            self.assertIn(StepStartEvent, seen_types)
            self.assertIn(VerificationEvent, seen_types)
            self.assertIn(FinalEvent, seen_types)

            trace_files = list((Path(tmpdir) / "traces").glob("*.jsonl"))
            self.assertEqual(len(trace_files), 1)
            trace_events = [
                json.loads(line)["type"]
                for line in trace_files[0].read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertIn("trace_header", trace_events)
            self.assertIn("plan", trace_events)
            self.assertIn("final", trace_events)

            latest_trace = find_latest_trace(Path(tmpdir) / "traces")
            self.assertEqual(latest_trace, trace_files[0])

            summary = summarize_trace_file(trace_files[0])
            self.assertEqual(summary["task"], "say hello")
            self.assertEqual(summary["final_status"], "done")
            self.assertEqual(summary["verification_passed"], 1)
            formatted = format_trace_summary(summary)
            self.assertIn("Task: say hello", formatted)
            self.assertIn("Final: done", formatted)

    async def test_default_coding_tools_and_command_safety(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            loop = ReActLoop(workspace_root=tmpdir)

            for tool_name in [
                "read_file",
                "write_file",
                "edit_file",
                "execute_bash",
                "list_files",
                "search_text",
                "search_files",
                "run_tests",
                "rollback_file",
            ]:
                self.assertIn(tool_name, loop.tools)

            schema_tool_names = {
                item["function"]["name"]
                for item in TOOLS_DEFINITIONS
            }
            self.assertEqual(schema_tool_names, set(loop.tools.keys()))

            tui = AgentTUI()
            formatted = tui._format_tool_result(
                "edit_file",
                ToolCallEndEvent(
                    tool_call_id="tc_edit",
                    result=[TextContent(text="成功修改文件 sample.py。")],
                    details={
                        "status": "success",
                        "checkpoint_id": "abc123",
                        "rollback_tool": "rollback_file",
                        "rollback_args": {"checkpoint_id": "abc123"},
                    },
                ),
            )
            self.assertIn("checkpoint_id: abc123", formatted)
            self.assertIn('rollback_file {"checkpoint_id": "abc123"}', formatted)

            blocked = await loop.tools["execute_bash"].execute(
                tool_call_id="danger",
                params={"command": "git reset --hard", "timeout": 5},
            )
            self.assertTrue(blocked.is_error)
            self.assertEqual(blocked.details["status"], "blocked")

            outside = await loop.tools["run_tests"].execute(
                tool_call_id="outside",
                params={"path": "../tests"},
            )
            self.assertTrue(outside.is_error)

    async def test_edit_file_diff_preview_and_write_details(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "sample.py"
            test_file.write_text("def value():\n    return 1\n", encoding="utf-8")
            editor = FileEditManager(base_path=tmpdir)

            preview = await editor.execute(
                tool_call_id="preview",
                params={
                    "path": "sample.py",
                    "target": "    return 1",
                    "replacement": "    return 2",
                    "preview_only": True,
                },
            )
            self.assertFalse(preview.is_error)
            self.assertIn("-    return 1", preview.details["diff"])
            self.assertIn("+    return 2", preview.details["diff"])
            self.assertIn("return 1", test_file.read_text(encoding="utf-8"))

            result = await editor.execute(
                tool_call_id="write",
                params={
                    "path": "sample.py",
                    "target": "    return 1",
                    "replacement": "    return 2",
                },
            )
            self.assertFalse(result.is_error)
            self.assertEqual(result.details["status"], "success")
            self.assertIn("checkpoint_id", result.details)
            self.assertIn("before_sha256", result.details)
            self.assertIn("after_sha256", result.details)
            self.assertIn("return 2", test_file.read_text(encoding="utf-8"))

            rollback = RollbackFileManager(base_path=tmpdir)
            rollback_result = await rollback.execute(
                tool_call_id="rollback",
                params={"checkpoint_id": result.details["checkpoint_id"]},
            )
            self.assertFalse(rollback_result.is_error)
            self.assertEqual(rollback_result.details["rollback_status"], "restored")
            self.assertIn("return 1", test_file.read_text(encoding="utf-8"))
            self.assertNotIn("return 2", test_file.read_text(encoding="utf-8"))

    async def test_write_file_creates_checkpoint_and_latest_path_rollback(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "notes.txt"
            test_file.write_text("before\n", encoding="utf-8")
            writer = FileWriteManager(base_path=tmpdir)

            result = await writer.execute(
                tool_call_id="write",
                params={"path": "notes.txt", "content": "after\n"},
            )
            self.assertFalse(result.is_error)
            self.assertIn("checkpoint_id", result.details)
            self.assertEqual(test_file.read_text(encoding="utf-8"), "after\n")

            rollback = RollbackFileManager(base_path=tmpdir)
            rollback_result = await rollback.execute(
                tool_call_id="rollback",
                params={"path": "notes.txt"},
            )
            self.assertFalse(rollback_result.is_error)
            self.assertEqual(rollback_result.details["rollback_status"], "restored")
            self.assertEqual(test_file.read_text(encoding="utf-8"), "before\n")


if __name__ == "__main__":
    unittest.main()
