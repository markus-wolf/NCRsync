"""Modal screens.

RecoveryScreen offers Resume/Discard/View on startup when an unfinished queue
from a previous session is found (doc-06 §9). OverwriteScreen asks before an
upload replaces files already on the server (doc-05 §9).
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


class OverwriteScreen(ModalScreen[str]):
    """Ask before uploads replace existing remote files.

    Returns 'overwrite', 'skip' (leave those files alone, upload the rest), or
    'cancel' (run nothing). Escape cancels: the safe answer to a question the
    user did not read.
    """

    BINDINGS = [("escape", "cancel", "Cancel")]

    DEFAULT_CSS = """
    OverwriteScreen { align: center middle; }
    #dialog {
        grid-size: 3 3;
        grid-gutter: 1 2;
        padding: 1 2;
        width: 76;
        height: auto;
        border: thick $warning;
        background: $surface;
    }
    #title { column-span: 3; content-align: center middle; text-style: bold; }
    #filelist { column-span: 3; height: auto; max-height: 12; }
    Button { width: 100%; }
    """

    def __init__(self, jobs: list[TransferJob]):
        super().__init__()
        self._jobs = jobs

    def compose(self) -> ComposeResult:
        n = len(self._jobs)
        with Grid(id="dialog"):
            yield Label(
                f"{n} upload(s) would replace file(s) already on the server.",
                id="title",
            )
            with VerticalScroll(id="filelist"):
                for j in self._jobs:
                    yield Static(escape(f"• {j.dest_path}"))
            yield Button("Overwrite", variant="error", id="overwrite")
            yield Button("Skip those", variant="primary", id="skip")
            yield Button("Cancel", variant="default", id="cancel")

    def on_mount(self) -> None:
        # focus the non-destructive choice so a stray Enter does no damage
        self.query_one("#skip", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id or "cancel")

    def action_cancel(self) -> None:
        self.dismiss("cancel")
