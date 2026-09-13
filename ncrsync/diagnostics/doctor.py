"""doctor: environment checks (doc-01 §3.9, doc-06 §10).

Checks local rsync, SSH connectivity, remote rsync, the effective rsync
capability tier (incl. the <3.0 degraded warning), and writability and free
space on both sides - the local directory receives downloads, the remote one
receives uploads.
"""
from __future__ import annotations

import asyncio
import os
import shlex
import shutil
from pathlib import Path
from typing import Callable, Optional

from ..model.connection_profile import SshTarget
from ..model.file_entry import human_size
from ..transfer.rsync_caps import compute_caps, parse_rsync_version
from ..version import resolve as resolve_version

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


def parse_df_available(text: str) -> Optional[int]:
    """Available bytes from the data line of ``df -Pk``.

    POSIX (-P) output is: filesystem, 1024-blocks, used, available, capacity,
    mount point. Either the filesystem name or the mount point may contain
    spaces, so neither end is a safe place to count from. The capacity field
    always ends in '%', and available is the field immediately before it.
    """
    lines = [ln for ln in text.strip().splitlines() if ln.strip()]
    if not lines:
        return None
    fields = lines[-1].split()
    for i, f in enumerate(fields):
        if f.endswith("%") and i > 0:
            try:
                return int(fields[i - 1]) * 1024
            except ValueError:
                return None
    return None


async def run_doctor(target: SshTarget, rsync_bin: str, local_dest: Path,
                     report: Report, remote_dir: Optional[str] = None) -> None:
    report("doctor: running checks...")
    report(f"  ncrsync:      {resolve_version().long()}")

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

    # local side: where downloads land
    writable = os.access(local_dest, os.W_OK)
    report(f"  local write:  {'yes' if writable else 'NO'}  ({local_dest})")
    try:
        report(f"  local free:   {human_size(shutil.disk_usage(local_dest).free)}")
    except OSError:
        report("  local free:   unknown")

    # remote side: where uploads land
    if ssh_ok and remote_dir:
        q = shlex.quote(remote_dir)
        _rc, out = await _run(target.ssh_argv(
            f"test -w {q} && echo ncrsync-writable || echo ncrsync-readonly"
        ))
        rw = "yes" if "ncrsync-writable" in out else "NO"
        report(f"  remote write: {rw}  ({remote_dir})")
        _rc, out = await _run(target.ssh_argv(f"df -Pk {q} 2>/dev/null"))
        avail = parse_df_available(out)
        report(f"  remote free:  {human_size(avail) if avail is not None else 'unknown'}")
    report("doctor: done.")
