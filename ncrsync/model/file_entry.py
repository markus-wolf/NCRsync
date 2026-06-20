"""FileEntry: a single remote or local directory entry."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

Kind = Literal["file", "dir", "symlink", "other"]


@dataclass
class FileEntry:
    name: str
    path: str  # absolute path in its own namespace (remote or local)
    kind: Kind
    size: Optional[int] = None
    mtime: Optional[str] = None
    permissions: Optional[str] = None


def human_size(n: Optional[int]) -> str:
    """Format a byte count like rsync's --human-readable (1024-based)."""
    if n is None:
        return ""
    size = float(n)
    for unit in ("B", "K", "M", "G", "T", "P"):
        if size < 1024 or unit == "P":
            if unit == "B":
                return f"{int(size)}{unit}"
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{n}"


def sort_entries(entries: list[FileEntry]) -> list[FileEntry]:
    """Sort directories first, then files/symlinks, then others; case-insensitive."""
    rank = {"dir": 0, "file": 1, "symlink": 1, "other": 2}
    return sorted(entries, key=lambda e: (rank.get(e.kind, 2), e.name.lower()))
