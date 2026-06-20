"""TransferJob and JobStatus: one queued/running download."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"

    def is_unfinished(self) -> bool:
        # running is treated as interrupted on reload (doc-06 §9)
        return self in (JobStatus.QUEUED, JobStatus.FAILED, JobStatus.RUNNING)


@dataclass
class TransferJob:
    remote_path: str
    local_dest: str
    name: str
    status: JobStatus = JobStatus.QUEUED
    last_error: Optional[str] = None
    attempts: int = 0

    def to_dict(self) -> dict:
        return {
            "remote_path": self.remote_path,
            "local_dest": self.local_dest,
            "name": self.name,
            "status": self.status.value,
            "last_error": self.last_error,
            "attempts": self.attempts,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TransferJob":
        name = d.get("name") or d["remote_path"].rsplit("/", 1)[-1]
        try:
            status = JobStatus(d.get("status", "queued"))
        except ValueError:
            status = JobStatus.QUEUED
        # a job written as 'running' was interrupted -> treat as queued for resume
        if status is JobStatus.RUNNING:
            status = JobStatus.QUEUED
        return cls(
            remote_path=d["remote_path"],
            local_dest=d["local_dest"],
            name=name,
            status=status,
            last_error=d.get("last_error"),
            attempts=d.get("attempts", 0),
        )
