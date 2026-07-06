"""Thin DataTable-based pane widgets and a shared render helper.

These hold no SSH/rsync logic - they only display FileEntry rows and remember
the entries backing each row so the app can map cursor -> entry.
"""
from __future__ import annotations

from rich.text import Text
from textual.widgets import DataTable

from ..model.file_entry import FileEntry, human_size


class FilePane(DataTable):
    """A directory listing pane (remote or local)."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.entries: list[FileEntry] = []

    def on_mount(self) -> None:
        self.cursor_type = "row"
        self.zebra_stripes = True
        self.add_columns("size", "", "name", "mtime")

    def populate(self, entries: list[FileEntry], selected: set[str]) -> None:
        prev = self.cursor_row
        self.entries = entries
        self.clear()
        for e in entries:
            mark = "*" if e.path in selected else ""
            # Text objects bypass DataTable's markup parsing, so names like
            # x[TGx].mkv are shown verbatim
            if e.kind == "dir":
                name = Text(e.name + "/", style="bold")
            else:
                name = Text(e.name)
            size = Text("<DIR>" if e.kind == "dir" else human_size(e.size), justify="right")
            self.add_row(size, mark, name, e.mtime or "", key=e.path)
        if entries:
            self.move_cursor(row=min(prev or 0, len(entries) - 1))

    def entry_at_cursor(self) -> FileEntry | None:
        if not self.entries or self.cursor_row is None or self.cursor_row >= len(self.entries):
            return None
        return self.entries[self.cursor_row]


class QueuePane(DataTable):
    """The transfer queue table."""

    def on_mount(self) -> None:
        self.cursor_type = "row"
        self.zebra_stripes = True
        self.add_columns("status", "file", "info")

    def populate(self, rows: list[tuple[str, str, str]]) -> None:
        prev = self.cursor_row
        self.clear()
        for status, name, info in rows:
            self.add_row(status, Text(name), Text(info))
        if rows:
            self.move_cursor(row=min(prev or 0, len(rows) - 1))
