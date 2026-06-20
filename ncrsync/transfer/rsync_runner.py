"""RsyncRunner: build a safe rsync argv, run it async, stream output, cancel.

Path-safety rule (doc-03 §6): when ``-s``/``--protect-args`` is available the
rsync ``host:path`` source is passed RAW (no shell quoting). Only in the legacy
``< 3.0`` degraded mode is the path portion single-quoted so the remote shell
does not split it.
"""
from __future__ import annotations

import asyncio
import logging
import shlex
import signal
from typing import Awaitable, Callable, Optional

from ..model.connection_profile import SshTarget
from .rsync_caps import RsyncCaps, select_flags

log = logging.getLogger("ncrsync")

# rsync exit codes that indicate a transient/network problem worth auto-retrying
TRANSIENT_EXIT_CODES = {10, 12, 30, 35}

LineSink = Callable[[str], None]


def _format_source(target: SshTarget, remote_path: str, caps: RsyncCaps) -> str:
    if caps.protect_args:
        return f"{target.host}:{remote_path}"          # raw, -s protects it
    return f"{target.host}:{shlex.quote(remote_path)}"  # legacy degraded mode


def build_rsync_argv(
    target: SshTarget,
    remote_path: str,
    local_dest: str,
    caps: RsyncCaps,
    *,
    rsync_bin: str = "rsync",
    keepalive_opts: Optional[list[str]] = None,
    timeout: int = 120,
    bwlimit: int = 0,
    append_verify_pref: bool = True,
) -> list[str]:
    """Build the rsync argv for a single download."""
    source = _format_source(target, remote_path, caps)
    dest = local_dest if local_dest.endswith("/") else local_dest + "/"
    argv = [rsync_bin, "-av", "--human-readable", f"--timeout={timeout}"]
    argv += select_flags(caps, append_verify_pref=append_verify_pref)
    if bwlimit and bwlimit > 0:
        argv.append(f"--bwlimit={bwlimit}")
    argv += ["-e", target.rsync_e_value(keepalive_opts)]
    argv += [source, dest]
    return argv


class RsyncRunner:
    """Runs one rsync subprocess at a time and exposes cancellation."""

    def __init__(self) -> None:
        self._proc: Optional[asyncio.subprocess.Process] = None
        self._cancelled = False

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    async def run(self, argv: list[str], on_line: LineSink) -> int:
        """Run rsync, streaming output lines to on_line. Returns exit code.

        Returns 130 if cancelled, 127 if rsync is missing.
        """
        self._cancelled = False
        log.info("$ %s", shlex.join(argv))
        try:
            self._proc = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
        except FileNotFoundError:
            on_line("[rsync executable not found]")
            return 127
        proc = self._proc
        assert proc.stdout is not None
        buf = ""
        try:
            while True:
                chunk = await proc.stdout.read(4096)
                if not chunk:
                    break
                # progress2 overwrites with \r; normalize for line logging
                buf += chunk.decode(errors="replace").replace("\r", "\n")
                *lines, buf = buf.split("\n")
                for line in lines:
                    if line.strip():
                        on_line(line)
            if buf.strip():
                on_line(buf)
        finally:
            rc = await proc.wait()
            self._proc = None
        if self._cancelled:
            return 130
        return rc

    async def cancel(self) -> None:
        """SIGINT, wait briefly, then escalate to SIGTERM/kill. Keeps partial file."""
        proc = self._proc
        if proc is None or proc.returncode is not None:
            return
        self._cancelled = True
        try:
            proc.send_signal(signal.SIGINT)
        except ProcessLookupError:
            return
        try:
            await asyncio.wait_for(proc.wait(), timeout=3.0)
            return
        except asyncio.TimeoutError:
            pass
        try:
            proc.terminate()
            await asyncio.wait_for(proc.wait(), timeout=2.0)
        except (asyncio.TimeoutError, ProcessLookupError):
            try:
                proc.kill()
            except ProcessLookupError:
                pass
