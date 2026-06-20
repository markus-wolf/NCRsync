"""NCRsync Textual application: wires panes, browsers, transfer manager, state.

Per doc-03 §1 the UI holds NO SSH/rsync command construction - it delegates to
the remote/ and transfer/ modules and reacts to their callbacks.
"""
from __future__ import annotations

import fnmatch
import logging
import sys
from pathlib import Path

from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.widgets import Footer, Header, Input, RichLog, Static

from .config.config_loader import Config, load_config
from .diagnostics.doctor import run_doctor
from .local.local_browser import LocalBrowser
from .logging_setup import setup_logging
from .model.connection_profile import SshTarget
from .model.transfer_job import JobStatus, TransferJob
from .remote.remote_browser import RemoteBrowser
from .remote.ssh_client import SshError
from .screens import RecoveryScreen
from .state.queue_store import QueueStore
from .state.state_store import StateStore
from .transfer.progress_parser import Progress
from .transfer.rsync_caps import RsyncCaps, compute_caps, parse_rsync_version
from .transfer.transfer_manager import TransferManager, TransferSettings
from .ui.panes import FilePane, QueuePane

log = logging.getLogger("ncrsync")


class NCRsync(App):
    CSS = """
    #panes { height: 1fr; }
    #remote, #local { width: 1fr; border: round $primary; }
    #remote:focus, #local:focus { border: round $accent; }
    #queue { height: 7; border: round $secondary; }
    #status { height: 1; padding: 0 1; color: $text-muted; }
    #log { height: 1fr; border: round $secondary; }
    #command { dock: bottom; }
    """

    BINDINGS = [
        ("tab", "switch_pane", "Switch"),
        ("f5", "download", "Download"),
        ("f6", "queue", "Queue"),
        ("f7", "cancel", "Cancel"),
        ("f8", "remove", "Remove"),
        ("f10", "quit", "Quit"),
        ("ctrl+r", "refresh", "Refresh"),
        ("space", "toggle_select", "Select"),
        ("backspace", "parent_dir", "Parent"),
    ]

    def __init__(self, target_raw: str, config: Config | None = None, **kwargs):
        super().__init__(**kwargs)
        self.target_raw = target_raw
        self.target = SshTarget.parse(target_raw)
        self.config = config or load_config(self.target.host)

        self.remote = RemoteBrowser(self.target, cwd=self.config.default_remote_dir())
        local_dir = Path(self.config.default_local_dir()).expanduser()
        if not local_dir.exists():
            local_dir = Path.home()
        self.local = LocalBrowser(local_dir, show_hidden=self.config.ui.get("show_hidden", True))

        self.state = StateStore()
        self.queue_store = QueueStore()
        self.remote_selected: set[str] = set()
        self.active_pane = "remote"

        # provisional caps from local rsync only; refined by _detect_caps()
        self.caps: RsyncCaps = compute_caps((0, 0, 0), None)
        self.manager = self._build_manager(self.caps)

    def _build_manager(self, caps: RsyncCaps) -> TransferManager:
        t = self.config.transfer
        settings = TransferSettings(
            rsync_bin=self.config.rsync_bin,
            keepalive_opts=self.config.keepalive_opts,
            timeout=t.get("timeout", 120),
            bwlimit=t.get("bwlimit", 0),
            append_verify_pref=t.get("append_verify", True),
            continue_on_error=t.get("continue_on_error", False),
            max_retries=t.get("max_retries", 3),
            retry_delay_seconds=t.get("retry_delay_seconds", 5),
        )
        return TransferManager(
            self.target, caps, settings,
            on_line=self.log_line,
            on_status=self._sync_queue,
            on_progress=self._on_progress,
        )

    # -- layout --
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="panes"):
            yield FilePane(id="remote")
            yield FilePane(id="local")
        yield QueuePane(id="queue")
        yield Static("", id="status")
        yield RichLog(id="log", highlight=True, markup=True, wrap=False)
        yield Input(
            placeholder=": command (cd, lcd, select, queue, download, doctor, mkdir, clear, quit)",
            id="command",
        )
        yield Footer()

    def on_mount(self) -> None:
        setup_logging(self.target.host, sys.argv)
        self.state.add_recent_host(self.target.host)
        self._restore_session()
        self._update_title()
        self.log_line(f"[bold]NCRsync[/] - target [b]{self.target.host}[/]  rsync: {self.config.rsync_bin}")
        self.query_one("#remote", FilePane).focus()
        self.refresh_local()
        self.refresh_remote()
        self.detect_caps()
        self._maybe_recover()

    def _restore_session(self) -> None:
        sess = self.state.load_session(self.target.host)
        if not sess:
            return
        self.remote.set_cwd(sess.get("remote_cwd", self.remote.cwd))
        local = Path(sess.get("local_cwd", str(self.local.cwd)))
        if local.is_dir():
            self.local.cwd = local

    def _update_title(self) -> None:
        self.title = "NCRsync"
        self.sub_title = f"{self.target.host} | R:{self.remote.cwd} | L:{self.local.cwd}"

    def log_line(self, msg: str) -> None:
        self.query_one("#log", RichLog).write(msg)
        log.info(_strip_markup(msg))

    # -- caps detection --
    @work(exclusive=True, group="caps")
    async def detect_caps(self) -> None:
        import asyncio

        async def ver(argv):
            try:
                p = await asyncio.create_subprocess_exec(
                    *argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
                )
                out, _ = await p.communicate()
                return parse_rsync_version(out.decode(errors="replace"))
            except FileNotFoundError:
                return None

        local_ver = await ver([self.config.rsync_bin, "--version"])
        remote_ver = await ver(self.target.ssh_argv("rsync --version 2>/dev/null | head -1"))
        self.caps = compute_caps(local_ver, remote_ver)
        self.manager.caps = self.caps
        self.query_one("#status", Static).update(f"rsync tier: {self.caps.tier}")
        self.log_line(f"[dim]rsync capability tier: {self.caps.tier}[/]")
        if self.caps.degraded:
            self.log_line("[yellow]WARNING:[/] remote rsync < 3.0 - paths with special chars may fail (run doctor)")

    # -- recovery --
    def _maybe_recover(self) -> None:
        data = self.queue_store.load()
        if not self.queue_store.has_unfinished(data):
            return
        jobs = data["jobs"]

        def handle(choice: str | None) -> None:
            if choice == "discard":
                self.queue_store.clear()
                self.log_line("[yellow]previous queue discarded[/]")
                return
            # resume or view: restore paths + load jobs
            self.remote.set_cwd(data.get("remote_cwd", self.remote.cwd))
            self.manager.load_jobs(jobs)
            self._update_title()
            self.refresh_remote()
            if choice == "resume":
                self.log_line("[green]resuming previous queue[/]")
                self.download()
            else:
                self.log_line("[cyan]previous queue loaded (press F5 to download)[/]")

        self.push_screen(RecoveryScreen(jobs, data.get("remote_cwd", "")), handle)

    # -- rendering --
    def _active(self) -> FilePane:
        return self.query_one(f"#{self.active_pane}", FilePane)

    def _sync_queue(self) -> None:
        rows = []
        for j in self.manager.jobs:
            info = j.last_error or ""
            rows.append((j.status.value, j.name, info))
        self.query_one("#queue", QueuePane).populate(rows)
        self._persist_queue()

    def _persist_queue(self) -> None:
        self.queue_store.save(
            self.target.host, self.remote.cwd, str(self.local.cwd), self.manager.jobs
        )

    def _on_progress(self, job: TransferJob, prog: Progress) -> None:
        self.query_one("#status", Static).update(f"{job.name}  {prog.as_status()}")

    # -- remote / local listing --
    @work(exclusive=True, group="remote")
    async def refresh_remote(self) -> None:
        try:
            entries = await self.remote.list_dir()
        except SshError as exc:
            self.log_line(f"[red]{exc}[/]")
            return
        self.query_one("#remote", FilePane).populate(entries, self.remote_selected)
        self.log_line(f"[green]remote[/] {self.remote.cwd}: {len(entries)} entries")

    def refresh_local(self) -> None:
        try:
            entries = self.local.list_dir()
        except OSError as exc:
            self.log_line(f"[red]local list failed:[/] {exc}")
            return
        self.query_one("#local", FilePane).populate(entries, set())
        self._update_title()

    # -- actions --
    def action_switch_pane(self) -> None:
        nxt = "local" if self.active_pane == "remote" else "remote"
        self.query_one(f"#{nxt}", FilePane).focus()

    def on_descendant_focus(self, event) -> None:
        wid = getattr(event.widget, "id", None)
        if wid in ("remote", "local"):
            self.active_pane = wid

    def action_refresh(self) -> None:
        self.refresh_remote() if self.active_pane == "remote" else self.refresh_local()

    def action_toggle_select(self) -> None:
        if self.active_pane != "remote":
            return
        pane = self.query_one("#remote", FilePane)
        e = pane.entry_at_cursor()
        if e is None:
            return
        self.remote_selected.discard(e.path) if e.path in self.remote_selected else self.remote_selected.add(e.path)
        pane.populate(pane.entries, self.remote_selected)

    def action_parent_dir(self) -> None:
        if self.active_pane == "remote":
            self.remote.parent()
            self.remote_selected.clear()
            self._update_title()
            self.refresh_remote()
        else:
            self.local.parent()
            self.refresh_local()

    def on_data_table_row_selected(self, event) -> None:
        pane_id = event.data_table.id
        if pane_id not in ("remote", "local"):
            return
        pane = self.query_one(f"#{pane_id}", FilePane)
        e = pane.entry_at_cursor()
        if e is None or e.kind != "dir":
            return
        if pane_id == "remote":
            self.remote.set_cwd(e.path)
            self.remote_selected.clear()
            self._update_title()
            self.refresh_remote()
        else:
            self.local.cwd = Path(e.path)
            self.refresh_local()

    def action_queue(self) -> None:
        paths = set(self.remote_selected)
        if not paths:
            e = self.query_one("#remote", FilePane).entry_at_cursor()
            if e and e.kind == "file":
                paths = {e.path}
        added = 0
        for e in self.query_one("#remote", FilePane).entries:
            if e.path in paths and e.kind == "file":
                if self.manager.add(e.path, e.name, str(self.local.cwd)):
                    added += 1
        self.remote_selected.clear()
        self.query_one("#remote", FilePane).populate(
            self.query_one("#remote", FilePane).entries, self.remote_selected
        )
        self.log_line(f"[green]queued[/] {added} item(s); queue size {len(self.manager.jobs)}")

    def action_remove(self) -> None:
        if self.active_pane == "remote":
            return
        t = self.query_one("#queue", QueuePane)
        if t.cursor_row is not None:
            removed = self.manager.remove_at(t.cursor_row)
            if removed:
                self.log_line(f"[yellow]removed[/] {removed.name}")

    def action_download(self) -> None:
        self.download()

    @work(exclusive=True, group="transfer")
    async def download(self) -> None:
        await self.manager.run_queue()

    def action_cancel(self) -> None:
        self.cancel_transfer()

    @work(group="cancel")
    async def cancel_transfer(self) -> None:
        await self.manager.stop()
        self.log_line("[yellow]cancel requested[/]")

    @work(exclusive=True, group="doctor")
    async def run_doctor_worker(self) -> None:
        await run_doctor(self.target, self.config.rsync_bin, self.local.cwd, self.log_line)

    # -- command input --
    def on_input_submitted(self, event: Input.Submitted) -> None:
        raw = event.value.strip()
        event.input.value = ""
        if not raw:
            return
        self.log_line(f"[cyan]:[/] {raw}")
        parts = raw.split(None, 1)
        cmd = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""
        if cmd == "cd" and arg:
            self.remote.set_cwd(self.remote.resolve(arg))
            self.remote_selected.clear()
            self._update_title()
            self.refresh_remote()
        elif cmd == "lcd" and arg:
            if self.local.change_dir(arg):
                self.refresh_local()
            else:
                self.log_line(f"[red]not a directory:[/] {arg}")
        elif cmd in ("ls", "ll"):
            self.refresh_remote()
        elif cmd == "select":
            self._cmd_select(arg or "*")
        elif cmd == "mkdir" and arg:
            try:
                p = self.local.mkdir(arg)
                self.refresh_local()
                self.log_line(f"[green]created[/] {p}")
            except OSError as exc:
                self.log_line(f"[red]mkdir failed:[/] {exc}")
        elif cmd == "queue":
            self.action_queue()
        elif cmd == "download":
            self.download()
        elif cmd == "doctor":
            self.run_doctor_worker()
        elif cmd == "clear":
            self.query_one("#log", RichLog).clear()
        elif cmd in ("quit", "exit", "q"):
            self.exit()
        else:
            self.log_line(f"[red]unknown command:[/] {cmd}")

    def _cmd_select(self, pattern: str) -> None:
        pane = self.query_one("#remote", FilePane)
        n = 0
        for e in pane.entries:
            if e.kind == "file" and fnmatch.fnmatch(e.name, pattern):
                self.remote_selected.add(e.path)
                n += 1
        pane.populate(pane.entries, self.remote_selected)
        self.log_line(f"[green]selected[/] {n} item(s) matching {pattern!r}")

    def on_unmount(self) -> None:
        # persist final session + queue state on exit
        try:
            self.state.save_session(self.target.host, self.remote.cwd, str(self.local.cwd))
            self._persist_queue()
        except Exception:  # pragma: no cover - best effort on shutdown
            pass


def _strip_markup(s: str) -> str:
    import re

    return re.sub(r"\[/?[^\]]*\]", "", s)
