"""QueueStore: persist the transfer queue to queue.json (doc-06 §8)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from ..model.transfer_job import JobStatus, TransferJob
from .state_store import state_dir


class QueueStore:
    def __init__(self, base: Optional[Path] = None):
        self.base = base or state_dir()
        self.base.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return self.base / "queue.json"

    def save(self, host: str, remote_cwd: str, local_cwd: str,
             jobs: list[TransferJob]) -> None:
        data = {
            "version": 1,
            "host": host,
            "remote_cwd": remote_cwd,
            "local_cwd": local_cwd,
            "items": [j.to_dict() for j in jobs],
        }
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2))
        tmp.replace(self.path)  # atomic-ish replace

    def load(self) -> Optional[dict]:
        if not self.path.exists():
            return None
        try:
            data = json.loads(self.path.read_text())
        except (json.JSONDecodeError, OSError):
            return None
        data["jobs"] = [TransferJob.from_dict(d) for d in data.get("items", [])]
        return data

    @staticmethod
    def has_unfinished(data: Optional[dict]) -> bool:
        if not data:
            return False
        return any(j.status.is_unfinished() for j in data.get("jobs", []))

    def clear(self) -> None:
        if self.path.exists():
            self.path.unlink()
