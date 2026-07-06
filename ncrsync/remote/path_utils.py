"""Remote path helpers and the find-based listing command/parser.

Path-safety rule (doc-03 §6): remote *shell* commands are shell-quoted here.
The rsync ``host:path`` source is built elsewhere and must NOT be shell-quoted.
"""
from __future__ import annotations

import posixpath
import shlex

from ..model.file_entry import FileEntry, Kind

# find -printf escapes (\t \n) are interpreted by find on the remote, so they
# are sent as literal backslash sequences. Minute precision matches the local
# pane (%TS would add fractional seconds).
_FIND_PRINTF = r"%y\t%s\t%TY-%Tm-%Td %TH:%TM\t%M\t%f\n"


def build_remote_list_cmd(remote_cwd: str) -> str:
    """Remote shell command string; remote_cwd is shell-quoted (shell context)."""
    q = shlex.quote(remote_cwd)
    return (
        f"cd {q} && "
        f"find . -maxdepth 1 -mindepth 1 -printf '{_FIND_PRINTF}' "
        f"2>/dev/null || (cd {q} && ls -la)"
    )


def parse_find_output(text: str, remote_cwd: str) -> list[FileEntry]:
    """Parse the tab-separated find output. ls -la fallback lines are skipped."""
    entries: list[FileEntry] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        cols = line.split("\t")
        if len(cols) != 5:
            continue  # ls -la fallback or noise; ignored in this version
        ftype, size, mtime, perms, name = cols
        kind: Kind
        if ftype == "d":
            kind = "dir"
        elif ftype == "f":
            kind = "file"
        elif ftype == "l":
            kind = "symlink"
        else:
            kind = "other"
        try:
            size_int = int(size)
        except ValueError:
            size_int = None
        entries.append(
            FileEntry(
                name=name,
                path=posixpath.normpath(posixpath.join(remote_cwd, name)),
                kind=kind,
                size=size_int,
                mtime=mtime,
                permissions=perms,
            )
        )
    return entries


def remote_resolve(remote_cwd: str, arg: str) -> str:
    """Resolve a cd argument against the remote cwd (absolute or relative)."""
    new = arg if arg.startswith("/") else posixpath.join(remote_cwd, arg)
    return posixpath.normpath(new)
