import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Union


class TaskTraceRecorder:
    """Append-only JSONL recorder for one user task."""

    def __init__(self, trace_dir: str, session_id: str, task: str):
        self.trace_dir = Path(trace_dir)
        self.trace_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        short_id = uuid.uuid4().hex[:8]
        safe_session_id = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in session_id)
        self.file_path = self.trace_dir / f"{timestamp}_{safe_session_id}_{short_id}.jsonl"
        self._closed = False

        self._write_line(
            {
                "type": "trace_header",
                "trace_id": short_id,
                "session_id": session_id,
                "task": task,
                "cwd": os.getcwd(),
                "created_at": datetime.now().isoformat(timespec="seconds"),
            }
        )

    def append_event(self, event: Any) -> None:
        if self._closed:
            return

        if hasattr(event, "model_dump"):
            payload = event.model_dump(mode="json")
        else:
            payload = {"type": "raw_event", "value": str(event)}

        payload.setdefault("type", event.__class__.__name__)
        payload["recorded_at"] = datetime.now().isoformat(timespec="seconds")
        self._write_line(payload)

    def close(self, status: str = "done", summary: Optional[str] = None) -> None:
        if self._closed:
            return

        self._write_line(
            {
                "type": "trace_footer",
                "status": status,
                "summary": summary or "",
                "closed_at": datetime.now().isoformat(timespec="seconds"),
            }
        )
        self._closed = True

    def _write_line(self, payload: dict) -> None:
        with self.file_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(payload, ensure_ascii=False) + "\n")


def load_trace_records(trace_file: Union[str, Path]) -> list[dict]:
    path = Path(trace_file)
    records = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            if line.strip():
                records.append(json.loads(line))
    return records


def find_latest_trace(trace_dir: Union[str, Path]) -> Optional[Path]:
    path = Path(trace_dir)
    if not path.exists():
        return None

    traces = sorted(path.glob("*.jsonl"), key=lambda item: item.stat().st_mtime, reverse=True)
    return traces[0] if traces else None


def summarize_trace_file(trace_file: Union[str, Path]) -> dict:
    records = load_trace_records(trace_file)
    tool_calls = [record for record in records if record.get("type") == "tool_call_start"]
    tool_results = [record for record in records if record.get("type") == "tool_call_end"]
    verifications = [record for record in records if record.get("type") == "verification"]
    final_events = [record for record in records if record.get("type") == "final"]
    footer_events = [record for record in records if record.get("type") == "trace_footer"]
    header = next((record for record in records if record.get("type") == "trace_header"), {})

    failed_tools = [record for record in tool_results if record.get("is_error")]
    checkpoint_results = [
        record
        for record in tool_results
        if isinstance(record.get("details"), dict) and record["details"].get("checkpoint_id")
    ]
    rollback_results = [
        record
        for record in tool_results
        if isinstance(record.get("details"), dict) and record["details"].get("rollback_status")
    ]
    rollback_success = [
        record
        for record in rollback_results
        if not record.get("is_error") and record["details"].get("rollback_status") in {"restored", "deleted_new_file"}
    ]
    final_status = "unknown"
    final_summary = ""
    if final_events:
        final_status = str(final_events[-1].get("status", "unknown"))
        final_summary = str(final_events[-1].get("summary", ""))
    elif footer_events:
        final_status = str(footer_events[-1].get("status", "unknown"))
        final_summary = str(footer_events[-1].get("summary", ""))

    return {
        "trace_file": str(Path(trace_file)),
        "task": header.get("task", ""),
        "session_id": header.get("session_id", ""),
        "created_at": header.get("created_at", ""),
        "event_count": len(records),
        "turn_count": len([record for record in records if record.get("type") == "turn_start"]),
        "tool_call_count": len(tool_calls),
        "tool_names": sorted({record.get("tool_name", "") for record in tool_calls if record.get("tool_name")}),
        "failed_tool_count": len(failed_tools),
        "checkpoint_count": len(checkpoint_results),
        "rollback_count": len(rollback_results),
        "rollback_success_count": len(rollback_success),
        "verification_count": len(verifications),
        "verification_passed": sum(1 for record in verifications if record.get("passed")),
        "final_status": final_status,
        "final_summary": final_summary,
    }


def format_trace_summary(summary: dict) -> str:
    tool_names = ", ".join(summary.get("tool_names") or []) or "-"
    return "\n".join(
        [
            f"Trace: {summary.get('trace_file', '')}",
            f"Task: {summary.get('task', '')}",
            f"Session: {summary.get('session_id', '')}",
            f"Created: {summary.get('created_at', '')}",
            f"Turns: {summary.get('turn_count', 0)}",
            f"Events: {summary.get('event_count', 0)}",
            f"Tools: {summary.get('tool_call_count', 0)} ({tool_names})",
            f"Tool errors: {summary.get('failed_tool_count', 0)}",
            f"Checkpoints: {summary.get('checkpoint_count', 0)}",
            f"Rollbacks: {summary.get('rollback_success_count', 0)}/{summary.get('rollback_count', 0)} succeeded",
            f"Verification: {summary.get('verification_passed', 0)}/{summary.get('verification_count', 0)} passed",
            f"Final: {summary.get('final_status', 'unknown')} - {summary.get('final_summary', '')}",
        ]
    )
