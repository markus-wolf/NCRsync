"""doctor: environment checks (doc-01 §3.9, doc-06 §10).

Checks local rsync, SSH connectivity, remote rsync, destination writability, and
reports the effective rsync capability tier (incl. the <3.0 degraded warning).
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Callable

from ..model.connection_profile import SshTarget
from ..transfer.rsync_caps import compute_caps, parse_rsync_version

Report = Callable[[str], None]


async def _run(argv: list[str]) -> tuple[int, str]:
    try:
        p = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        out, _ = await p.communicate()
        return (p.returncode if p.returncode is not None else -1, out.decode(errors="replace"))
    except FileNotFoundError:
        return 127, "not found"


async def run_doctor(target: SshTarget, rsync_bin: str, local_dest: Path,
                     report: Report) -> None:
    report("doctor: running checks...")

    # local rsync
    rc, out = await _run([rsync_bin, "--version"])
    local_ver = parse_rsync_version(out)
    first = out.splitlines()[0] if out.strip() else "?"
    report(f"  local rsync:  {'ok' if rc == 0 else 'MISSING'}  {first}")

    # ssh connectivity
    rc, out = await _run(target.ssh_argv("echo ncrsync-ok"))
    ssh_ok = "ncrsync-ok" in out
    report(f"  ssh connect:  {'ok' if ssh_ok else 'FAILED'}  ({target.host})")
    if not ssh_ok:
        report(f"    {out.strip()[:200]}")

    # remote rsync
    remote_ver = None
    if ssh_ok:
        rc, out = await _run(target.ssh_argv("rsync --version 2>/dev/null | head -1"))
        remote_ver = parse_rsync_version(out)
        report(f"  remote rsync: {out.strip() if out.strip() else 'unknown'}")

    # capability tier
    caps = compute_caps(local_ver, remote_ver)
    report(f"  rsync tier:   {caps.tier}  (effective {'.'.join(map(str, caps.effective))})")
    if caps.degraded:
        report("    WARNING: effective rsync < 3.0 - '-s/--protect-args' unavailable.")
        report("    Paths with spaces or special chars (e.g. brackets) may fail.")
        report("    Recommend upgrading the remote rsync.")
    elif not caps.append_verify and caps.append:
        report("    note: --append-verify deprecated here; using --append for resume.")

    # destination writability
    writable = os.access(local_dest, os.W_OK)
    report(f"  dest write:   {'yes' if writable else 'NO'}  ({local_dest})")
    report("doctor: done.")
