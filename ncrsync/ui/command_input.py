"""CommandInput: the ':' command line with arrow-up/down history (doc-02 §6)."""
from __future__ import annotations

from textual.binding import Binding
from textual.widgets import Input


class CommandInput(Input):
    BINDINGS = [
        Binding("up", "history_prev", show=False),
        Binding("down", "history_next", show=False),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.history: list[str] = []
        self._index: int | None = None  # None = editing a fresh line
        self._draft = ""

    def remember(self, command: str) -> None:
        if command and (not self.history or self.history[-1] != command):
            self.history.append(command)
        self._index = None
        self._draft = ""

    def action_history_prev(self) -> None:
        if not self.history:
            return
        if self._index is None:
            self._draft = self.value
            self._index = len(self.history) - 1
        elif self._index > 0:
            self._index -= 1
        self.value = self.history[self._index]
        self.cursor_position = len(self.value)

    def action_history_next(self) -> None:
        if self._index is None:
            return
        if self._index < len(self.history) - 1:
            self._index += 1
            self.value = self.history[self._index]
        else:
            self._index = None
            self.value = self._draft
        self.cursor_position = len(self.value)
