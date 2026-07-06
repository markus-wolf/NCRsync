"""App themes. NC_BLUE evokes the classic Norton Commander palette (doc-02 §8)."""
from __future__ import annotations

from textual.theme import Theme

NC_BLUE = Theme(
    name="nc-blue",
    primary="#00aaaa",      # cyan - pane borders / highlights
    secondary="#5555ff",
    accent="#ffff55",       # yellow - focused elements
    foreground="#e0e0e0",
    background="#0000aa",   # the classic NC blue
    surface="#000080",
    panel="#000080",
    success="#55ff55",
    warning="#ffff55",
    error="#ff5555",
    dark=True,
)
