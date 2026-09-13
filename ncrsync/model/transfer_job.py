"""TransferJob, Direction and JobStatus: one queued/running transfer."""
from __future__ import annotations

import posixpath
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional


class Direction(str, Enum):
    DOWNLOAD = "download"   # remote -> local
    UPLOAD = "upload"       # local -> remote


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
    """One file or directory moving between the two panes.

    ``remote_path`` and ``local_path`` name the endpoint on each side. The
    source side holds a full path to the item being transferred; the
    destination side holds the directory it lands in. Which is which follows
    ``direction``, so for a download ``remote_path`` is the file and
    ``local_path`` the target directory, and for an upload it is the reverse.
    """

    remote_path: str
    local_path: str
    name: str
    direction: Direction = Direction.DOWNLOAD
    status: JobStatus = JobStatus.QUEUED
    last_error: Optional[str] = None
    attempts: int = 0
    #: Was something already at the destination when this job first ran?
    #: False -> the partial there is ours and may be appended to.
    #: True  -> it came from elsewhere; never append onto it.
    #: None  -> not yet determined (set on first run; None in older queue.json).
    dest_preexisting: Optional[bool] = None

    # -- endpoints ----------------------------------------------------------
    @property
    def remote_is_source(self) -> bool:
        return self.direction is Direction.DOWNLOAD

    @property
    def source_path(self) -> str:
        """Full path of the item being transferred, on its own side."""
        return self.remote_path if self.remote_is_source else self.local_path

    @property
    def dest_dir(self) -> str:
        """Directory the item lands in, on the far side."""
        return self.local_path if self.remote_is_source else self.remote_path

    @property
    def dest_path(self) -> str:
        """Full path the transfer will write. Remote paths stay POSIX."""
        base = self.name.rstrip("/")
        if self.remote_is_source:
            return str(Path(self.dest_dir) / base)
        return posixpath.join(self.dest_dir, base)

    @property
    def is_directory(self) -> bool:
        return self.name.endswith("/")

    # -- persistence --------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "remote_path": self.remote_path,
            "local_path": self.local_path,
            "name": self.name,
            "direction": self.direction.value,
            "status": self.status.value,
            "last_error": self.last_error,
            "attempts": self.attempts,
            "dest_preexisting": self.dest_preexisting,
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
        try:
            direction = Direction(d.get("direction", Direction.DOWNLOAD.value))
        except ValueError:
            direction = Direction.DOWNLOAD
        return cls(
            remote_path=d["remote_path"],
            # queue.json v1 called this local_dest and only held downloads
            local_path=d.get("local_path", d.get("local_dest", "")),
            name=name,
            direction=direction,
            status=status,
            last_error=d.get("last_error"),
            attempts=d.get("attempts", 0),
            # absent in queue.json written before this field existed; None
            # makes the resume policy treat the destination as unknown origin
            dest_preexisting=d.get("dest_preexisting"),
        )
