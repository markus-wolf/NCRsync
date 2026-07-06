"""TransferManager: owns the queue, runs downloads with cancel + auto-retry.

Failure policy (doc-04 §6): stop the queue on a non-transient failure unless
``continue_on_error``. Transient/network failures (rsync exit 10/12/30/35) are
auto-retried up to ``max_retries`` with a backoff delay; ``--partial``/``--append``
makes each retry resume the partial file.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Callable, Optional

from ..model.connection_profile import SshTarget
from ..model.transfer_job import JobStatus, TransferJob
from .progress_parser import Progress, parse_progress_line
from .rsync_caps import RsyncCaps
from .rsync_runner import TRANSIENT_EXIT_CODES, RsyncRunner, build_rsync_argv

log = logging.getLogger("ncrsync")


@dataclass
class TransferSettings:
    rsync_bin: str = "rsync"
    keepalive_opts: Optional[list[str]] = None
    timeout: int = 120
    bwlimit: int = 0
    append_verify_pref: bool = True
    protect_args_pref: bool = True
    continue_on_error: bool = False
    max_retries: int = 3
    retry_delay_seconds: int = 5


class TransferManager:
    def __init__(
        self,
        target: SshTarget,
        caps: RsyncCaps,
        settings: TransferSettings,
        *,
        on_line: Callable[[str], None] = lambda s: None,
        on_status: Callable[[], None] = lambda: None,
        on_progress: Callable[[TransferJob, Progress], None] = lambda j, p: None,
    ):
        self.target = target
        self.caps = caps
        self.settings = settings
        self.jobs: list[TransferJob] = []
        self._runner = RsyncRunner()
        self._stopping = False
        self._on_line = on_line
        self._on_status = on_status
        self._on_progress = on_progress

    # -- queue management --
    def add(self, remote_path: str, name: str, local_dest: str) -> bool:
        if any(j.remote_path == remote_path for j in self.jobs):
            return False
        self.jobs.append(TransferJob(remote_path=remote_path, local_dest=local_dest, name=name))
        self._on_status()
        return True

    def remove_at(self, index: int) -> Optional[TransferJob]:
        """Remove a job by index. A RUNNING job is refused - the subprocess
        would keep transferring invisibly; it must be cancelled first."""
        if 0 <= index < len(self.jobs):
            if self.jobs[index].status is JobStatus.RUNNING:
                return None
            j = self.jobs.pop(index)
            self._on_status()
            return j
        return None

    def clear(self) -> None:
        self.jobs.clear()
        self._on_status()

    def load_jobs(self, jobs: list[TransferJob]) -> None:
        self.jobs = jobs
        self._on_status()

    @property
    def pending(self) -> list[TransferJob]:
        return [j for j in self.jobs if j.status in (JobStatus.QUEUED, JobStatus.FAILED)]

    # -- execution --
    async def run_queue(self) -> None:
        self._stopping = False
        pending = self.pending
        if not pending:
            self._on_line("[queue empty - nothing to download]")
            return
        self._on_line(f"[starting {len(pending)} job(s)]")
        for job in pending:
            if self._stopping:
                break
            ok = await self._run_job(job)
            if not ok and not self.settings.continue_on_error:
                self._on_line("[stopping queue on failure - partial preserved]")
                break

    async def _run_job(self, job: TransferJob) -> bool:
        attempt = 0
        max_attempts = 1 + max(0, self.settings.max_retries)
        while attempt < max_attempts:
            attempt += 1
            job.attempts += 1
            job.status = JobStatus.RUNNING
            job.last_error = None
            self._on_status()
            argv = build_rsync_argv(
                self.target, job.remote_path, job.local_dest, self.caps,
                rsync_bin=self.settings.rsync_bin,
                keepalive_opts=self.settings.keepalive_opts,
                timeout=self.settings.timeout,
                bwlimit=self.settings.bwlimit,
                append_verify_pref=self.settings.append_verify_pref,
                protect_args_pref=self.settings.protect_args_pref,
            )
            rc = await self._runner.run(argv, self._make_sink(job))

            if rc == 0:
                job.status = JobStatus.COMPLETED
                self._on_line(f"[done] {job.name}")
                self._on_status()
                return True
            if self._runner.cancelled or rc == 130:
                job.status = JobStatus.CANCELLED
                self._on_line(f"[cancelled] {job.name} (partial kept)")
                self._on_status()
                return False
            # failure
            job.last_error = f"rsync rc={rc}"
            if rc in TRANSIENT_EXIT_CODES and attempt < max_attempts and not self._stopping:
                delay = self.settings.retry_delay_seconds * attempt
                self._on_line(
                    f"[retry] {job.name} failed (rc={rc}); retry {attempt}/{max_attempts - 1} in {delay}s"
                )
                job.status = JobStatus.QUEUED
                self._on_status()
                try:
                    await asyncio.sleep(delay)
                except asyncio.CancelledError:
                    break
                continue
            job.status = JobStatus.FAILED
            self._on_line(f"[failed] {job.name} (rc={rc})")
            self._on_status()
            return False
        # exhausted retries
        job.status = JobStatus.FAILED
        self._on_status()
        return False

    def _make_sink(self, job: TransferJob):
        def sink(line: str) -> None:
            self._on_line(line)
            prog = parse_progress_line(line)
            if prog is not None:
                self._on_progress(job, prog)
        return sink

    async def stop(self) -> None:
        """Cancel the active job and halt the queue."""
        self._stopping = True
        await self._runner.cancel()
