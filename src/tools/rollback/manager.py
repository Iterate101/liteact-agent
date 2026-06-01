import asyncio
from typing import Optional

from src.tools.base import AgentTool, AgentToolResult, AgentToolUpdateCallback, TextContent
from src.tools.checkpoint import PatchCheckpointStore


class RollbackFileManager(AgentTool):
    """Restore a file to the checkpoint created before an edit/write tool call."""

    name: str = "rollback_file"
    description: str = (
        "Restore a file from a LiteAct checkpoint. Prefer checkpoint_id from the previous "
        "edit_file/write_file result; if only path is supplied, the latest checkpoint for that path is used."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "checkpoint_id": {
                "type": "string",
                "description": "Checkpoint id returned by edit_file/write_file. Use 'latest' with path for the latest checkpoint.",
            },
            "path": {
                "type": "string",
                "description": "Optional workspace path used to restore the latest checkpoint for that file.",
            },
        },
    }

    def __init__(self, base_path: Optional[str] = None):
        self.store = PatchCheckpointStore(base_path)

    async def execute(
        self,
        tool_call_id: str,
        params: dict,
        abort_signal: Optional[asyncio.Event] = None,
        on_partial_result: Optional[AgentToolUpdateCallback] = None,
    ) -> AgentToolResult:
        checkpoint_id = params.get("checkpoint_id")
        path = params.get("path")
        try:
            metadata = self.store.rollback(checkpoint_id=checkpoint_id, path=path)
            relative_path = metadata.get("relative_path") or metadata.get("path")
            return AgentToolResult(
                content=[
                    TextContent(
                        text=(
                            f"Rolled back {relative_path} using checkpoint "
                            f"{metadata['checkpoint_id']} ({metadata['rollback_status']})."
                        )
                    )
                ],
                details={
                    "status": "success",
                    "rollback_status": metadata["rollback_status"],
                    "checkpoint_id": metadata["checkpoint_id"],
                    "path": metadata["path"],
                    "relative_path": metadata.get("relative_path", ""),
                    "before_sha256": metadata.get("before_sha256", ""),
                    "after_sha256": metadata.get("after_sha256", ""),
                    "current_sha256": metadata.get("current_sha256", ""),
                },
            )
        except Exception as exc:
            return AgentToolResult(
                content=[TextContent(text=f"Error: rollback failed: {exc}")],
                details={"status": "error", "reason": str(exc)},
                is_error=True,
            )
