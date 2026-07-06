"""LocalBrowser: local cwd management, listing, and mkdir."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ..model.file_entry import FileEntry, sort_entries


def list_local(local_cwd: Path, show_hidden: bool = True) -> list[FileEntry]:
    entries: list[FileEntry] = []
    for child in local_cwd.iterdir():
        if not show_hidden and child.name.startswith("."):
            continue
        try:
            st = child.stat()
        except OSError:
            continue
        if child.is_dir():
            kind = "dir"
        elif child.is_symlink():
            kind = "symlink"
        elif child.is_file():
            kind = "file"
        else:
            kind = "other"
        entries.append(
            FileEntry(
                name=child.name,
                path=str(child.resolve()),
                kind=kind,
                size=st.st_size if kind == "file" else None,
                mtime=datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M"),
            )
        )
    return entries


class LocalBrowser:
    def __init__(self, cwd: Path, show_hidden: bool = True):
        self.cwd = cwd
        self.show_hidden = show_hidden

    def list_dir(self) -> list[FileEntry]:
        return sort_entries(list_local(self.cwd, self.show_hidden))

    def change_dir(self, arg: str) -> bool:
        new = (self.cwd / arg) if not arg.startswith("/") else Path(arg)
        new = new.expanduser()
        if new.is_dir():
            self.cwd = new.resolve()
            return True
        return False

    def parent(self) -> Path:
        self.cwd = self.cwd.parent
        return self.cwd

    def mkdir(self, name: str) -> Path:
        target = (self.cwd / name).expanduser()
        target.mkdir(parents=True, exist_ok=True)
        return target
