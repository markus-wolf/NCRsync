"""RemoteBrowser: remote cwd management + directory listing over SSH."""
from __future__ import annotations

import logging
import posixpath

from ..model.connection_profile import SshTarget
from ..model.file_entry import FileEntry, sort_entries
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

    async def list_dir(self) -> list[FileEntry]:
        """List the current remote directory. Raises SshError on failure."""
        cmd = path_utils.build_remote_list_cmd(self.cwd)
        log.info("$ %s", ssh_command_repr(self.target, cmd))
        rc, out, err = await run_ssh(self.target, cmd)
        if rc != 0:
            raise SshError(f"remote list failed (rc={rc}): {err.strip()}")
        return sort_entries(path_utils.parse_find_output(out, self.cwd))
