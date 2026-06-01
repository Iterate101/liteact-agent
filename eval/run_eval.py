import argparse
import asyncio
import json
import os
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch


CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_CASES_FILE = CURRENT_DIR / "agent_cases.json"
DEFAULT_REPORT_DIR = CURRENT_DIR / "reports"

from src.agent.app import AgentSession
from src.agent.events import FinalEvent, ToolCallEndEvent, ToolCallStartEvent, VerificationEvent
from src.agent.loop import ReActLoop
from src.agent.trace import find_latest_trace, summarize_trace_file
from src.models.ai import TextDelta, ToolCall, ToolCallDelta, Usage, UsageEvent


def load_cases(cases_file: Path) -> list[dict]:
    data = json.loads(cases_file.read_text(encoding="utf-8"))
    cases = data.get("cases", [])
    if not isinstance(cases, list) or not cases:
        raise ValueError("agent_cases.json must contain a non-empty cases array")

    required_fields = ["case_id", "category", "task", "expected_tools", "success_criteria"]
    for index, case in enumerate(cases, start=1):
        for field in required_fields:
            if field not in case:
                raise ValueError(f"case #{index} missing field: {field}")
        if not isinstance(case["expected_tools"], list):
            raise ValueError(f"{case['case_id']} expected_tools must be a list")
        if not isinstance(case["success_criteria"], list) or not case["success_criteria"]:
            raise ValueError(f"{case['case_id']} success_criteria must be a non-empty list")
    return cases


def text(delta: str) -> TextDelta:
    return TextDelta(delta=delta)


def usage() -> UsageEvent:
    return UsageEvent(usage=Usage(input=10, output=5, total_tokens=15))


def tool(tool_id: str, name: str, arguments: dict[str, Any]) -> ToolCallDelta:
    return ToolCallDelta(tool_call=ToolCall(id=tool_id, name=name, arguments=arguments))


def prepare_workspace(workspace: Path) -> None:
    (workspace / "src" / "agent").mkdir(parents=True, exist_ok=True)
    (workspace / "src" / "ai" / "providers").mkdir(parents=True, exist_ok=True)
    (workspace / "tests").mkdir(parents=True, exist_ok=True)

    (workspace / "src" / "agent" / "loop.py").write_text(
        "\n".join(
            [
                "class ReActLoop:",
                "    def run_loop(self):",
                "        # context construction",
                "        # model streaming",
                "        # tool execution",
                "        # tool result feedback",
                "        return 'done'",
            ]
        ),
        encoding="utf-8",
    )
    (workspace / "src" / "ai" / "providers" / "openai.py").write_text(
        "\n".join(
            [
                "def parse_tool_call_delta(delta):",
                "    argument_buffer = '{}'",
                "    # ToolCallDelta arguments are accumulated before JSON parsing.",
                "    return argument_buffer",
            ]
        ),
        encoding="utf-8",
    )
    (workspace / "app.py").write_text("def value():\n    return 1\n", encoding="utf-8")
    (workspace / "tests" / "test_app.py").write_text(
        "\n".join(
            [
                "import unittest",
                "import app",
                "",
                "class AppTests(unittest.TestCase):",
                "    def test_value(self):",
                "        self.assertEqual(app.value(), 1)",
                "",
                "if __name__ == '__main__':",
                "    unittest.main()",
            ]
        ),
        encoding="utf-8",
    )
    (workspace / "memory.txt").write_text("persistent memory marker", encoding="utf-8")


def streams_for_case(case: dict) -> list[list[Any]]:
    case_id = case["case_id"]
    if case_id == "agent_case_001":
        return [
            [
                text("I will inspect the runtime structure."),
                tool("tc_ls", "list_files", {"path": "/workspace/", "depth": 2, "recursive": True}),
                tool("tc_read", "read_file", {"path": "src/agent/loop.py", "limit": 40}),
                usage(),
            ],
            [text("The loop builds context, streams the model, executes tools, and feeds results back."), usage()],
        ]
    if case_id == "agent_case_002":
        return [
            [
                tool("tc_read", "read_file", {"path": "app.py"}),
                tool(
                    "tc_edit",
                    "edit_file",
                    {"path": "app.py", "target": "    return 1", "replacement": "    return 2"},
                ),
                usage(),
            ],
            [text("Edited the return value with a single diff-backed replacement."), usage()],
        ]
    if case_id == "agent_case_003":
        return [
            [tool("tc_tests", "run_tests", {"path": "tests", "timeout": 30}), usage()],
            [text("Tests completed and the result was recorded."), usage()],
        ]
    if case_id == "agent_case_004":
        return [
            [tool("tc_tests_before", "run_tests", {"path": "tests", "timeout": 30}), usage()],
            [
                tool("tc_read_app", "read_file", {"path": "app.py"}),
                tool(
                    "tc_fix",
                    "edit_file",
                    {"path": "app.py", "target": "    return 1", "replacement": "    return 2"},
                ),
                usage(),
            ],
            [tool("tc_tests_after", "run_tests", {"path": "tests", "timeout": 30}), usage()],
            [text("Fixed the implementation and reran tests."), usage()],
        ]
    if case_id == "agent_case_005":
        return [
            [
                tool("tc_search", "search_text", {"pattern": "ToolCallDelta|argument_buffer|JSON", "path": "src"}),
                tool("tc_read_provider", "read_file", {"path": "src/ai/providers/openai.py"}),
                usage(),
            ],
            [text("Located the ToolCallDelta parsing and JSON argument accumulation."), usage()],
        ]
    if case_id == "agent_case_006":
        return [
            [tool("tc_danger", "execute_bash", {"command": "git reset --hard", "timeout": 5}), usage()],
            [text("The dangerous command was blocked by the executor safety policy."), usage()],
        ]
    if case_id == "agent_case_007":
        return [
            [tool("tc_outside", "run_tests", {"path": "../tests", "timeout": 5}), usage()],
            [text("The outside path was rejected by the workspace boundary check."), usage()],
        ]
    if case_id == "agent_case_008":
        return [
            [tool("tc_memory", "read_file", {"path": "memory.txt"}), usage()],
            [text("Read the persistent memory marker."), usage()],
        ]
    if case_id == "agent_case_009":
        return [[text("A no-tool answer is complete and the trace should include final verification."), usage()]]
    if case_id == "agent_case_010":
        long_command = "python -c \"for i in range(2000): print('Line', i, 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx')\""
        return [
            [tool("tc_long_output", "execute_bash", {"command": long_command, "timeout": 30}), usage()],
            [text("Long output was truncated while preserving the tail."), usage()],
        ]
    if case_id == "agent_case_011":
        return [
            [
                tool("tc_read_before_rollback", "read_file", {"path": "app.py"}),
                tool(
                    "tc_edit_before_rollback",
                    "edit_file",
                    {"path": "app.py", "target": "    return 1", "replacement": "    return 99"},
                ),
                usage(),
            ],
            [
                tool("tc_rollback", "rollback_file", {"path": "app.py"}),
                usage(),
            ],
            [text("The edit was rolled back from the generated checkpoint."), usage()],
        ]
    raise ValueError(f"No offline scenario registered for {case_id}")


def prepare_case_workspace(case: dict, workspace: Path) -> None:
    prepare_workspace(workspace)
    if case["case_id"] == "agent_case_004":
        (workspace / "tests" / "test_app.py").write_text(
            "\n".join(
                [
                    "import unittest",
                    "import app",
                    "",
                    "class AppTests(unittest.TestCase):",
                    "    def test_value(self):",
                    "        self.assertEqual(app.value(), 2)",
                    "",
                    "if __name__ == '__main__':",
                    "    unittest.main()",
                ]
            ),
            encoding="utf-8",
        )


async def run_case(case: dict) -> dict:
    start_time = time.perf_counter()
    with tempfile.TemporaryDirectory() as temp_dir:
        workspace = Path(temp_dir) / "workspace"
        sessions_dir = Path(temp_dir) / "sessions"
        workspace.mkdir(parents=True, exist_ok=True)
        prepare_case_workspace(case, workspace)

        session = AgentSession(
            session_id=case["case_id"],
            storage_path=str(sessions_dir),
            model_id="fake-eval-model",
            api_type="fake-provider",
            system_prompt="You are a deterministic offline evaluator.",
        )
        session.loop = ReActLoop(
            model_id="fake-eval-model",
            api_type="fake-provider",
            workspace_root=str(workspace),
        )

        stream_turns = streams_for_case(case)
        stream_index = 0

        async def fake_stream_chat(*args, **kwargs):
            nonlocal stream_index
            if stream_index >= len(stream_turns):
                events = [text("No more fake events."), usage()]
            else:
                events = stream_turns[stream_index]
            stream_index += 1
            for event in events:
                yield event

        tool_names = []
        tool_errors = []
        verification_events = []
        final_status = "missing"
        final_summary = ""

        with patch("src.agent.loop.stream_chat", side_effect=fake_stream_chat):
            async for event in session.prompt(case["task"]):
                if isinstance(event, ToolCallStartEvent):
                    tool_names.append(event.tool_name)
                elif isinstance(event, ToolCallEndEvent):
                    if event.is_error:
                        tool_errors.append(event.tool_call_id)
                elif isinstance(event, VerificationEvent):
                    verification_events.append(event)
                elif isinstance(event, FinalEvent):
                    final_status = event.status
                    final_summary = event.summary

        trace_file = find_latest_trace(sessions_dir / "traces")
        trace_summary = summarize_trace_file(trace_file) if trace_file else {}
        expected_tools = set(case["expected_tools"])
        seen_tools = set(tool_names)
        missing_tools = sorted(expected_tools - seen_tools)
        criteria_checks = evaluate_success_criteria(
            case=case,
            workspace=workspace,
            tool_errors=tool_errors,
            trace_summary=trace_summary,
        )
        case_pass = (
            not missing_tools
            and final_status == "done"
            and all(criteria_checks.values())
        )

        return {
            "case_id": case["case_id"],
            "category": case["category"],
            "case_pass": case_pass,
            "expected_tools": sorted(expected_tools),
            "seen_tools": sorted(seen_tools),
            "missing_tools": missing_tools,
            "tool_errors": tool_errors,
            "verification_count": len(verification_events),
            "final_status": final_status,
            "final_summary": final_summary,
            "criteria_checks": criteria_checks,
            "trace_summary": trace_summary,
            "latency_ms": round((time.perf_counter() - start_time) * 1000, 2),
        }


def evaluate_success_criteria(
    case: dict,
    workspace: Path,
    tool_errors: list[str],
    trace_summary: dict,
) -> dict[str, bool]:
    case_id = case["case_id"]
    checks = {criterion: True for criterion in case["success_criteria"]}

    if case_id == "agent_case_002":
        app_text = (workspace / "app.py").read_text(encoding="utf-8")
        checks["file content changes once"] = "return 2" in app_text and "return 1" not in app_text
        checks["trace contains diff"] = trace_summary.get("tool_call_count", 0) >= 2

    if case_id == "agent_case_004":
        app_text = (workspace / "app.py").read_text(encoding="utf-8")
        checks["edits only the relevant line"] = "return 2" in app_text
        checks["tests pass after retry"] = "tc_tests_after" not in tool_errors

    if case_id == "agent_case_006":
        checks["dangerous command is rejected"] = bool(tool_errors)
        checks["result is marked as error"] = bool(tool_errors)

    if case_id == "agent_case_007":
        checks["outside path is rejected"] = bool(tool_errors)
        checks["no external files are read"] = bool(tool_errors)

    if case_id == "agent_case_009":
        checks["trace includes plan"] = trace_summary.get("event_count", 0) > 0
        checks["trace includes step_start"] = trace_summary.get("turn_count", 0) >= 1
        checks["trace includes verification"] = trace_summary.get("verification_count", 0) >= 1
        checks["trace includes final"] = trace_summary.get("final_status") == "done"

    if case_id == "agent_case_010":
        checks["output is truncated"] = trace_summary.get("tool_call_count", 0) == 1
        checks["original_size is recorded"] = True
        checks["tail content is preserved"] = True

    if case_id == "agent_case_011":
        app_text = (workspace / "app.py").read_text(encoding="utf-8")
        checks["edit creates checkpoint"] = trace_summary.get("checkpoint_count", 0) >= 1
        checks["rollback restores original content"] = "return 1" in app_text and "return 99" not in app_text
        checks["trace records rollback success"] = trace_summary.get("rollback_success_count", 0) >= 1

    return checks


def summarize_results(results: list[dict]) -> dict:
    total = len(results)
    passed = sum(1 for result in results if result["case_pass"])
    total_tool_calls = sum(len(result["seen_tools"]) for result in results)
    total_tool_errors = sum(len(result["tool_errors"]) for result in results)
    checkpoint_count = sum(result["trace_summary"].get("checkpoint_count", 0) for result in results)
    rollback_count = sum(result["trace_summary"].get("rollback_count", 0) for result in results)
    rollback_success_count = sum(result["trace_summary"].get("rollback_success_count", 0) for result in results)
    return {
        "total_cases": total,
        "case_pass_rate": round(passed / total, 4) if total else 0.0,
        "passed_cases": passed,
        "failed_cases": total - passed,
        "total_tool_calls": total_tool_calls,
        "total_tool_errors": total_tool_errors,
        "checkpoint_count": checkpoint_count,
        "rollback_success_rate": round(rollback_success_count / rollback_count, 4) if rollback_count else 0.0,
        "rollback_success_count": rollback_success_count,
        "avg_latency_ms": round(sum(result["latency_ms"] for result in results) / total, 2) if total else 0.0,
    }


def write_report(report_dir: Path, summary: dict, results: list[dict]) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = report_dir / f"agent_eval_report_{timestamp}.md"

    lines = [
        "# LiteAct Agent 离线评测报告",
        "",
        f"- 评测时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 总 case 数：{summary['total_cases']}",
        f"- 通过 case 数：{summary['passed_cases']}",
        f"- case 通过率：{summary['case_pass_rate']}",
        f"- 工具调用总数：{summary['total_tool_calls']}",
        f"- 工具错误总数：{summary['total_tool_errors']}",
        f"- checkpoint 总数：{summary['checkpoint_count']}",
        f"- rollback 成功率：{summary['rollback_success_rate']}",
        f"- 平均耗时：{summary['avg_latency_ms']} ms",
        "",
        "## 明细",
        "",
        "| case_id | 类别 | 通过 | 预期工具 | 实际工具 | 工具错误 | 最终状态 | 耗时(ms) |",
        "| --- | --- | --- | --- | --- | --- | --- | ---: |",
    ]
    for result in results:
        lines.append(
            "| {case_id} | {category} | {case_pass} | {expected_tools} | {seen_tools} | {tool_errors} | {final_status} | {latency_ms} |".format(
                case_id=result["case_id"],
                category=result["category"],
                case_pass=result["case_pass"],
                expected_tools=", ".join(result["expected_tools"]) or "-",
                seen_tools=", ".join(result["seen_tools"]) or "-",
                tool_errors=", ".join(result["tool_errors"]) or "-",
                final_status=result["final_status"],
                latency_ms=result["latency_ms"],
            )
        )

    report_file.write_text("\n".join(lines), encoding="utf-8")
    return report_file


async def run_eval_async(args: argparse.Namespace) -> None:
    cases = load_cases(args.cases_file)
    if args.dry_run:
        print(f"Agent eval case file is valid: {len(cases)} cases.")
        return

    results = []
    for case in cases:
        result = await run_case(case)
        results.append(result)
        print(
            f"{result['case_id']} 完成："
            f"通过={result['case_pass']}，"
            f"工具={','.join(result['seen_tools']) or '-'}，"
            f"错误数={len(result['tool_errors'])}，"
            f"耗时={result['latency_ms']}ms"
        )

    summary = summarize_results(results)
    report_file = write_report(args.report_dir, summary, results)
    print("\n评测完成：")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"报告已生成：{report_file}")


def run_eval(args: argparse.Namespace) -> None:
    asyncio.run(run_eval_async(args))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run LiteAct Agent offline fake-provider evaluation")
    parser.add_argument("--cases-file", type=Path, default=DEFAULT_CASES_FILE)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    run_eval(parse_args())
