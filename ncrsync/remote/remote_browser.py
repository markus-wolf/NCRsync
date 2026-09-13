"""RemoteBrowser: remote cwd management + directory listing over SSH."""
from __future__ import annotations

import logging
import posixpath
import shlex

from ..model.connection_profile import SshTarget
from ..model.file_entry import FileEntry, sort_entries
from ..transfer.resume_policy import DestInfo
from . import path_utils
from .ssh_client import SshError, run_ssh, ssh_command_repr

log = logging.getLogger("ncrsync")


class RemoteBrowser:
    def __init__(self, target: SshTarget, cwd: str = "/"):
        self.target = target
        self.cwd = cwd

    def resolve(self, arg: str) -> str:
        return path_utils.remote_resolve(self.cwd, arg)

    def set_cwd(self, path: str) -> None:
        self.cwd = path

    def parent(self) -> str:
        self.cwd = posixpath.normpath(posixpath.join(self.cwd, ".."))
        return self.cwd

    async def mkdir(self, name: str) -> str:
        """Create a directory on the remote side, relative to the cwd.

        ``-p`` makes an existing directory a no-op rather than an error, and
        ``--`` stops a name beginning with a dash being read as an option.
        """
        path = self.resolve(name)
        cmd = f"mkdir -p -- {shlex.quote(path)}"
        log.info("$ %s", ssh_command_repr(self.target, cmd))
        rc, _out, err = await run_ssh(self.target, cmd)
        if rc != 0:
            raise SshError(f"remote mkdir failed (rc={rc}): {err.strip()}")
        return path

    async def stat_many(self, paths: list[str]) -> dict[str, DestInfo]:
        """Size and allocated blocks for several remote paths in one round trip.

        Feeds the resume policy for uploads, where the destination lives on the
        far side of the link. Batched deliberately: one call for a whole queue
        rather than one per job, which on a slow link is the difference between
        one round trip and fifty.

        Every requested path appears in the result; those that do not exist (or
        could not be stat-ed, including a remote without GNU find) report as
        absent, which makes the policy decline to append.
        """
        # start pessimistic: not inspected is not the same as not present
        out_map = {p: DestInfo(exists=False, known=False) for p in paths}
        if not paths:
            return out_map
        quoted = " ".join(shlex.quote(p) for p in paths)
        # -printf is GNU-only, so establish that first: exit 127 says we cannot
        # trust an empty result and every path stays unknown.
        # %s logical size, %b disk space used in 512-byte blocks
        cmd = (
            "find --version >/dev/null 2>&1 || exit 127; "
            f"find {quoted} -maxdepth 0 -printf '%p\\t%s\\t%b\\n' 2>/dev/null"
        )
        log.info("$ %s", ssh_command_repr(self.target, cmd))
        try:
            rc, out, _err = await run_ssh(self.target, cmd)
        except SshError as exc:
            log.info("remote stat failed: %s", exc)
            return out_map
        if rc == 127:
            log.info("remote has no GNU find; upload destinations stay unknown")
            return out_map
        # find ran, so an absent path really is absent
        out_map = {p: DestInfo(exists=False, known=True) for p in paths}
        # a missing path makes find exit non-zero while still printing the rest,
        # so parse the output regardless of the exit code
        for line in out.splitlines():
            cols = line.split("\t")
            if len(cols) != 3 or cols[0] not in out_map:
                continue
            try:
                size, blocks = int(cols[1]), int(cols[2])
            except ValueError:
                continue
            out_map[cols[0]] = DestInfo(exists=True, size=size, allocated=blocks * 512)
        return out_map

    async def list_dir(self) -> list[FileEntry]:
        """List the current remote directory. Raises SshError on failure."""
        cmd = path_utils.build_remote_list_cmd(self.cwd)
        log.info("$ %s", ssh_command_repr(self.target, cmd))
        rc, out, err = await run_ssh(self.target, cmd)
        if rc != 0:
            raise SshError(f"remote list failed (rc={rc}): {err.strip()}")
        return sort_entries(path_utils.parse_find_output(out, self.cwd))
