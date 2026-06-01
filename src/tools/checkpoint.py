import hashlib
import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional


class PatchCheckpointStore:
    """Text-file checkpoints used by edit/write tools and rollback_file."""

    def __init__(self, workspace_root: Optional[str] = None):
        self.workspace_root = Path(workspace_root).resolve() if workspace_root else Path.cwd().resolve()
        self.root_dir = self.workspace_root / ".liteact" / "checkpoints"
        self.content_dir = self.root_dir / "contents"
        self.metadata_dir = self.root_dir / "metadata"

    def create_checkpoint(self, target_path: Path, tool_name: str) -> dict:
        target = self._validate_target_path(target_path)
        self._ensure_dirs()

        checkpoint_id = uuid.uuid4().hex[:12]
        existed = target.exists()
        before_text = target.read_text(encoding="utf-8") if existed else ""
        content_file = self.content_dir / f"{checkpoint_id}.before.txt"
        content_file.write_text(before_text, encoding="utf-8")

        metadata = {
            "checkpoint_id": checkpoint_id,
            "tool_name": tool_name,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "workspace_root": str(self.workspace_root),
            "path": str(target),
            "relative_path": self._relative_path(target),
            "existed": existed,
            "before_sha256": self._sha256(before_text) if existed else "",
            "before_size": len(before_text.encode("utf-8")) if existed else 0,
            "after_sha256": "",
            "after_size": 0,
            "content_file": str(content_file),
            "status": "created",
        }
        self._write_metadata(metadata)
        return metadata

    def finalize_checkpoint(self, checkpoint_id: str, target_path: Path) -> dict:
        metadata = self.get_checkpoint(checkpoint_id)
        target = self._validate_target_path(target_path)
        after_text = target.read_text(encoding="utf-8") if target.exists() else ""
        metadata.update(
            {
                "path": str(target),
                "relative_path": self._relative_path(target),
                "after_sha256": self._sha256(after_text) if target.exists() else "",
                "after_size": len(after_text.encode("utf-8")) if target.exists() else 0,
                "status": "ready",
            }
        )
        self._write_metadata(metadata)
        return metadata

    def rollback(self, checkpoint_id: Optional[str] = None, path: Optional[str] = None) -> dict:
        metadata = self.resolve_checkpoint(checkpoint_id=checkpoint_id, path=path)
        target = self._validate_target_path(Path(metadata["path"]))
        content_file = Path(metadata["content_file"])

        if metadata.get("existed"):
            before_text = content_file.read_text(encoding="utf-8")
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = target.with_suffix(target.suffix + ".rollback.tmp")
            try:
                with tmp_path.open("w", encoding="utf-8") as file:
                    file.write(before_text)
                    file.flush()
                    os.fsync(file.fileno())
                os.replace(tmp_path, target)
            finally:
                if tmp_path.exists():
                    tmp_path.unlink()
            rollback_status = "restored"
        else:
            if target.exists():
                target.unlink()
            rollback_status = "deleted_new_file"

        current_text = target.read_text(encoding="utf-8") if target.exists() else ""
        metadata.update(
            {
                "rollback_status": rollback_status,
                "rolled_back_at": datetime.now().isoformat(timespec="seconds"),
                "current_sha256": self._sha256(current_text) if target.exists() else "",
                "status": "rolled_back",
            }
        )
        self._write_metadata(metadata)
        return metadata

    def resolve_checkpoint(self, checkpoint_id: Optional[str] = None, path: Optional[str] = None) -> dict:
        if checkpoint_id and checkpoint_id != "latest":
            return self.get_checkpoint(checkpoint_id)
        if path:
            return self.find_latest_for_path(path)
        if checkpoint_id == "latest":
            return self.find_latest()
        raise ValueError("checkpoint_id or path is required")

    def find_latest(self) -> dict:
        metadata_files = sorted(
            self.metadata_dir.glob("*.json"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        if not metadata_files:
            raise FileNotFoundError("No checkpoints found")
        return json.loads(metadata_files[0].read_text(encoding="utf-8"))

    def find_latest_for_path(self, path: str) -> dict:
        target = self._resolve_user_path(path)
        metadata_files = sorted(
            self.metadata_dir.glob("*.json"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        for metadata_file in metadata_files:
            metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
            if Path(metadata.get("path", "")).resolve() == target:
                return metadata
        raise FileNotFoundError(f"No checkpoint found for path: {path}")

    def get_checkpoint(self, checkpoint_id: str) -> dict:
        path = self.metadata_dir / f"{checkpoint_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"Checkpoint not found: {checkpoint_id}")
        return json.loads(path.read_text(encoding="utf-8"))

    def _resolve_user_path(self, path: str) -> Path:
        normalized = (path or "").replace("\\", "/")
        if normalized.startswith("/workspace/"):
            target = self.workspace_root / normalized[len("/workspace/"):].lstrip("/")
        else:
            raw_path = Path(path)
            target = raw_path if raw_path.is_absolute() else self.workspace_root / raw_path
        return self._validate_target_path(target)

    def _validate_target_path(self, target_path: Path) -> Path:
        target = target_path.resolve()
        try:
            target.relative_to(self.workspace_root)
        except ValueError as exc:
            raise ValueError(f"Path escapes workspace: {target}") from exc
        return target

    def _relative_path(self, target_path: Path) -> str:
        try:
            return str(target_path.resolve().relative_to(self.workspace_root))
        except ValueError:
            return str(target_path)

    def _ensure_dirs(self) -> None:
        self.content_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_dir.mkdir(parents=True, exist_ok=True)

    def _write_metadata(self, metadata: dict) -> None:
        self._ensure_dirs()
        path = self.metadata_dir / f"{metadata['checkpoint_id']}.json"
        path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    def _sha256(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()
