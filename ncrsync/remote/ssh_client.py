"""Async SSH command runner."""
from __future__ import annotations

import asyncio
import shlex

from ..model.connection_profile import SshTarget


class SshError(Exception):
    pass


async def run_ssh(target: SshTarget, remote_command: str) -> tuple[int, str, str]:
    """Run a command on the remote shell. Returns (returncode, stdout, stderr).

    Raises SshError if ssh itself is missing.
    """
    argv = target.ssh_argv(remote_command)
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise SshError("ssh executable not found") from exc
    out, err = await proc.communicate()
    return (
        proc.returncode if proc.returncode is not None else -1,
        out.decode(errors="replace"),
        err.decode(errors="replace"),
    )


def ssh_command_repr(target: SshTarget, remote_command: str) -> str:
    """Reproducible shell form of an ssh command, for logging."""
    return shlex.join(target.ssh_argv(remote_command))
