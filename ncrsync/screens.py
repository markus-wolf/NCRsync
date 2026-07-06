"""Modal screens. RecoveryScreen offers Resume/Discard/View on startup when an
unfinished queue from a previous session is found (doc-06 §9).
"""
from __future__ import annotations

from rich.markup import escape
from textual.app import ComposeResult
from textual.containers import Grid, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static

from .model.transfer_job import TransferJob


class RecoveryScreen(ModalScreen[str]):
    """Returns one of: 'resume', 'discard', 'view'."""

    DEFAULT_CSS = """
    RecoveryScreen { align: center middle; }
    #dialog {
        grid-size: 3 3;
        grid-gutter: 1 2;
        padding: 1 2;
        width: 72;
        height: auto;
        border: thick $accent;
        background: $surface;
    }
    #title { column-span: 3; content-align: center middle; text-style: bold; }
    #joblist { column-span: 3; height: auto; max-height: 10; }
    Button { width: 100%; }
    """

    def __init__(self, jobs: list[TransferJob], remote_cwd: str):
        super().__init__()
        self._jobs = jobs
        self._remote_cwd = remote_cwd

    def compose(self) -> ComposeResult:
        unfinished = [j for j in self._jobs if j.status.is_unfinished()]
        with Grid(id="dialog"):
            yield Label(
                f"Found a previous queue with {len(unfinished)} unfinished item(s).",
                id="title",
            )
            with VerticalScroll(id="joblist"):
                for j in unfinished:
                    # escape: Static parses markup; names may contain brackets
                    yield Static(escape(f"• [{j.status.value}] {j.name}"))
            yield Button("Resume", variant="success", id="resume")
            yield Button("View", variant="primary", id="view")
            yield Button("Discard", variant="error", id="discard")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id or "view")
