"""NCRsync Textual application: wires panes, browsers, transfer manager, state.

Per doc-03 §1 the UI holds NO SSH/rsync command construction - it delegates to
the remote/ and transfer/ modules and reacts to their callbacks.

Transfers run in either direction. The direction of a queued job is decided
when it is queued, from the pane the items were selected in: the remote pane
queues downloads into the local directory, the local pane queues uploads into
the remote directory. F5 then runs whatever is in the queue.
"""
from __future__ import annotations

import fnmatch
import logging
import sys
from pathlib import Path

from rich.markup import escape
from rich.text import Text
from textual import events, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import Footer, Header, Input, RichLog, Static
from textual.worker import Worker, WorkerState

from .config.config_loader import Config, load_config
from .diagnostics.doctor import run_doctor
from .local.local_browser import LocalBrowser
from .logging_setup import setup_logging
from .model.connection_profile import SshTarget
from .model.file_entry import FileEntry, human_size
from .model.transfer_job import Direction, JobStatus, TransferJob
from .remote.remote_browser import RemoteBrowser
from .remote.ssh_client import SshError
from .screens import OverwriteScreen, RecoveryScreen
from .state.queue_store import QueueStore
from .state.state_store import StateStore
from .transfer.progress_parser import Progress
from .transfer.rsync_caps import RsyncCaps, compute_caps, parse_rsync_version
from .transfer.transfer_manager import TransferManager, TransferSettings
from .ui.command_input import CommandInput
from .ui.panes import FilePane, QueuePane
from .ui.themes import NC_BLUE
from .version import resolve as resolve_version

log = logging.getLogger("ncrsync")

# waiting indicator for admin (SSH round-trip) operations
SPINNER_FRAMES = "/-\\|"
# worker groups that drive the spinner; "transfer" is excluded on purpose -
# transfers have their own progress display in the status bar
BUSY_GROUPS = frozenset({"remote", "caps", "doctor"})

PANES = ("remote", "local")
ARROW = {Direction.DOWNLOAD: "↓", Direction.UPLOAD: "↑"}


class NCRsync(App):
    CSS = """
    #panes { height: 1fr; }
    #remote, #local { width: 1fr; border: round $primary; }
    #remote:focus, #local:focus { border: round $accent; }
    #queue { height: 7; border: round $secondary; }
    #queue:focus { border: round $accent; }
    #status { height: 1; padding: 0 1; color: $text-muted; }
    #log { height: 1fr; border: round $secondary; }
    #command { dock: bottom; }
    """

    BINDINGS = [
        # priority=True: otherwise Textual's built-in focus_next swallows Tab
        # and the footer's "Switch" label would lie. Shift+Tab still cycles focus.
        Binding("tab", "switch_pane", "Switch", priority=True),
        ("f5", "download", "Transfer"),
        ("f6", "queue", "Queue"),
        ("f7", "cancel", "Cancel"),
        ("f8", "remove", "Remove"),
        ("f10", "quit", "Quit"),
        ("ctrl+r", "refresh", "Refresh"),
        ("space", "toggle_select", "Select"),
        ("backspace", "parent_dir", "Parent"),
    ]

    def __init__(self, target_raw: str, config: Config | None = None,
                 state_dir: Path | None = None, **kwargs):
        super().__init__(**kwargs)
        self.target_raw = target_raw
        self.target = SshTarget.parse(target_raw)
        self.config = config or load_config(self.target.host)

        self.remote = RemoteBrowser(self.target, cwd=self.config.default_remote_dir())
        local_dir = Path(self.config.default_local_dir()).expanduser()
        if not local_dir.exists():
            local_dir = Path.home()
        self.local = LocalBrowser(local_dir, show_hidden=self.config.ui.get("show_hidden", True))

        self.state = StateStore(base=state_dir)
        self.queue_store = QueueStore(base=state_dir)
        #: marked entries per pane, by absolute path (doc-05 §7)
        self.selected: dict[str, set[str]] = {p: set() for p in PANES}
        #: the file pane most recently focused. Commands typed at the prompt
        #: move focus to the input, so they act on this pane instead.
        self._last_pane = "remote"
        # queue.json on disk belongs to a different host and must not be clobbered
        self._foreign_queue = False
        # suppress the misleading provisional tier until detect_caps() finishes
        self._caps_ready = False
        # what is actually running: resolved once at startup, then read from here
        self.version = resolve_version()
        # spinner state; the timer is created on mount and stays paused when idle
        self._busy = False
        self._spin_i = 0
        self._spin_timer = None

        # provisional caps from local rsync only; refined by _detect_caps()
        self.caps: RsyncCaps = compute_caps((0, 0, 0), None)
        self.manager = self._build_manager(self.caps)

    @property
    def remote_selected(self) -> set[str]:
        return self.selected["remote"]

    @property
    def local_selected(self) -> set[str]:
        return self.selected["local"]

    def _build_manager(self, caps: RsyncCaps) -> TransferManager:
        t = self.config.transfer
        settings = TransferSettings(
            rsync_bin=self.config.rsync_bin,
            keepalive_opts=self.config.keepalive_opts,
            timeout=t.get("timeout", 120),
            bwlimit=t.get("bwlimit", 0),
            append_verify_pref=t.get("append_verify", True),
            protect_args_pref=t.get("protect_args", True),
            checksum_existing=t.get("checksum_existing", True),
            continue_on_error=t.get("continue_on_error", False),
            max_retries=t.get("max_retries", 3),
            retry_delay_seconds=t.get("retry_delay_seconds", 5),
        )
        return TransferManager(
            self.target, caps, settings,
            on_line=self.log_raw,
            on_status=self._sync_queue,
            on_progress=self._on_progress,
            remote_stat=self.remote.stat_many,
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
        yield CommandInput(
            placeholder=": command (cd, lcd, ls, ll, select, deselect, queue, download, "
                        "verify, mkdir, doctor, version, clear, quit)",
            id="command",
        )
        yield Footer()

    def on_mount(self) -> None:
        setup_logging(self.target.host, sys.argv, self.version.long())
        self.register_theme(NC_BLUE)
        wanted = self.config.ui.get("theme")
        if wanted:
            try:
                self.theme = wanted
            except Exception:
                self.log_line(f"[yellow]unknown theme[/] {escape(str(wanted))} - keeping default")
        # the log is display-only; keeping it out of the focus chain prevents
        # app-level bindings (backspace/space) firing while it is focused
        self.query_one("#log", RichLog).can_focus = False
        self._spin_timer = self.set_interval(0.1, self._tick_spinner, pause=True)
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
        self.title = f"NCRsync {self.version.short()}"
        # spinner leads the line: sub_title truncates from the tail on narrow
        # terminals, so a trailing spinner could vanish behind long paths
        spin = f"{SPINNER_FRAMES[self._spin_i]} " if self._busy else ""
        self.sub_title = f"{spin}{self.target.host} | R:{self.remote.cwd} | L:{self.local.cwd}"

    def _tick_spinner(self) -> None:
        self._spin_i = (self._spin_i + 1) % len(SPINNER_FRAMES)
        self._update_title()

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        if event.worker.group not in BUSY_GROUPS:
            return
        busy = any(
            w.group in BUSY_GROUPS and w.state is WorkerState.RUNNING
            for w in self.workers
        )
        if busy == self._busy:
            return
        self._busy = busy
        if self._spin_timer is not None:
            (self._spin_timer.resume if busy else self._spin_timer.pause)()
        if not busy:
            self._spin_i = 0
        self._update_title()

    def log_line(self, msg: str) -> None:
        """Write a message that intentionally contains Rich markup."""
        self.query_one("#log", RichLog).write(msg)
        log.info(_strip_markup(msg))

    def log_raw(self, line: str) -> None:
        """Write untrusted text (rsync output, filenames) with brackets escaped
        so names like x[TGx].mkv are not eaten as markup."""
        self.query_one("#log", RichLog).write(escape(line))
        log.info(line)

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
        self._caps_ready = True
        self._set_status()
        self.log_line(f"[dim]rsync capability tier: {self.caps.tier}[/]")
        if self.caps.degraded:
            self.log_line("[yellow]WARNING:[/] remote rsync < 3.0 - paths with special chars may fail (run doctor)")

    # -- recovery --
    def _maybe_recover(self) -> None:
        data = self.queue_store.load()
        if not self.queue_store.has_unfinished(data):
            return
        if data.get("host") != self.target.host:
            self._foreign_queue = True
            self.log_line(
                f"[dim]found an unfinished queue for host "
                f"{escape(str(data.get('host')))} - leaving it untouched[/]"
            )
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
                self.log_line("[cyan]previous queue loaded (press F5 to transfer)[/]")

        self.push_screen(RecoveryScreen(jobs, data.get("remote_cwd", "")), handle)

    # -- panes and selection --
    def _focused_id(self) -> str | None:
        return self.focused.id if self.focused is not None else None

    def on_descendant_focus(self, event: events.DescendantFocus) -> None:
        wid = getattr(event.widget, "id", None)
        if wid in PANES:
            self._last_pane = wid

    def _source_pane(self) -> str:
        """The pane an action applies to: the focused one, or, when focus is
        on the command prompt or the queue, the pane last focused."""
        fid = self._focused_id()
        return fid if fid in PANES else self._last_pane

    def _pane(self, pane_id: str) -> FilePane:
        return self.query_one(f"#{pane_id}", FilePane)

    def _repaint(self, pane_id: str) -> None:
        pane = self._pane(pane_id)
        pane.populate(pane.entries, self.selected[pane_id])

    def _toggle_selection(self, pane_id: str, e: FileEntry) -> None:
        sel = self.selected[pane_id]
        sel.discard(e.path) if e.path in sel else sel.add(e.path)
        self._repaint(pane_id)

    def _set_status(self, progress: str = "") -> None:
        """Status bar: 'rsync tier: X | <progress>'. Text() sidesteps markup."""
        parts = []
        if self._caps_ready:
            parts.append(f"rsync tier: {self.caps.tier}")
        if progress:
            parts.append(progress)
        self.query_one("#status", Static).update(Text("  |  ".join(parts)))

    def _sync_queue(self) -> None:
        rows = [
            (ARROW[j.direction], j.status.value, j.name, j.last_error or "")
            for j in self.manager.jobs
        ]
        self.query_one("#queue", QueuePane).populate(rows)
        self._persist_queue()
        # clear stale progress once nothing is running
        if not any(j.status is JobStatus.RUNNING for j in self.manager.jobs):
            self._set_status()

    def _persist_queue(self) -> None:
        # never overwrite another host's saved queue with our empty one; once
        # this session queues something, it takes ownership of the file
        if self._foreign_queue and not self.manager.jobs:
            return
        self._foreign_queue = False
        self.queue_store.save(
            self.target.host, self.remote.cwd, str(self.local.cwd), self.manager.jobs
        )

    def _on_progress(self, job: TransferJob, prog: Progress) -> None:
        self._set_status(f"{ARROW[job.direction]} {job.name}  {prog.as_status()}")

    # -- remote / local listing --
    @work(exclusive=True, group="remote")
    async def refresh_remote(self) -> None:
        try:
            entries = await self.remote.list_dir()
        except SshError as exc:
            self.log_line(f"[red]{escape(str(exc))}[/]")
            return
        self._pane("remote").populate(entries, self.selected["remote"])
        self.log_line(f"[green]remote[/] {escape(self.remote.cwd)}: {len(entries)} entries")

    def refresh_local(self) -> None:
        try:
            entries = self.local.list_dir()
        except OSError as exc:
            self.log_line(f"[red]local list failed:[/] {exc}")
            return
        self._pane("local").populate(entries, self.selected["local"])
        self._update_title()

    def _enter_remote(self, path: str) -> None:
        self.remote.set_cwd(path)
        self.selected["remote"].clear()   # marks are per directory listing
        self._update_title()
        self.refresh_remote()

    def _enter_local(self, path: Path) -> None:
        self.local.cwd = path
        self.selected["local"].clear()
        self.refresh_local()

    # -- actions --
    # every pane-sensitive action derives the target from the actually focused
    # widget; a shadow "active pane" variable goes stale for other widgets
    def action_switch_pane(self) -> None:
        nxt = "local" if self._focused_id() == "remote" else "remote"
        self._pane(nxt).focus()

    def action_refresh(self) -> None:
        fid = self._focused_id()
        if fid != "local":
            self.refresh_remote()
        if fid != "remote":
            self.refresh_local()

    def action_toggle_select(self) -> None:
        fid = self._focused_id()
        if fid not in PANES:
            return
        e = self._pane(fid).entry_at_cursor()
        if e is not None:
            self._toggle_selection(fid, e)

    def action_parent_dir(self) -> None:
        fid = self._focused_id()
        if fid == "remote":
            self.remote.parent()
            self._enter_remote(self.remote.cwd)
        elif fid == "local":
            self._enter_local(self.local.cwd.parent)

    def on_data_table_row_selected(self, event) -> None:
        pane_id = event.data_table.id
        if pane_id not in PANES:
            return
        e = self._pane(pane_id).entry_at_cursor()
        if e is None:
            return
        if e.kind == "dir":
            if pane_id == "remote":
                self._enter_remote(e.path)
            else:
                self._enter_local(Path(e.path))
        elif e.kind == "file":
            # Enter on a file toggles its selection (doc-01 §3.5)
            self._toggle_selection(pane_id, e)

    def action_queue(self) -> None:
        """Queue the selection (or cursor entry) toward the other pane.

        From the remote pane that is a download into the local directory; from
        the local pane, an upload into the remote directory.
        """
        src = self._source_pane()
        pane = self._pane(src)
        direction = Direction.DOWNLOAD if src == "remote" else Direction.UPLOAD
        sel = self.selected[src]
        paths = set(sel)
        if not paths:
            e = pane.entry_at_cursor()
            if e and e.kind in ("file", "dir"):
                paths = {e.path}
        added = 0
        for e in pane.entries:
            if e.path not in paths or e.kind not in ("file", "dir"):
                continue
            # directories transfer recursively via rsync -a
            name = e.name + "/" if e.kind == "dir" else e.name
            if direction is Direction.DOWNLOAD:
                ok = self.manager.add(e.path, name, str(self.local.cwd), direction)
            else:
                ok = self.manager.add(self.remote.cwd, name, e.path, direction)
            added += ok
        sel.clear()
        self._repaint(src)
        verb = "download" if direction is Direction.DOWNLOAD else "upload"
        dest = self.local.cwd if direction is Direction.DOWNLOAD else self.remote.cwd
        self.log_line(
            f"[green]queued[/] {added} item(s) for {verb} to {escape(str(dest))}; "
            f"queue size {len(self.manager.jobs)}"
        )

    def action_remove(self) -> None:
        if self._focused_id() != "queue":
            self.log_line("[dim]focus the queue (shift+tab or click) to remove items[/]")
            return
        t = self.query_one("#queue", QueuePane)
        row = t.cursor_row
        if row is None or row >= len(self.manager.jobs):
            return
        if self.manager.jobs[row].status is JobStatus.RUNNING:
            self.log_line("[yellow]job is running[/] - press F7 to cancel it first")
            return
        removed = self.manager.remove_at(row)
        if removed:
            self.log_line(f"[yellow]removed[/] {escape(removed.name)}")

    def action_download(self) -> None:
        self.download()

    @work(exclusive=True, group="transfer")
    async def download(self) -> None:
        """Run the queue, asking first if uploads would replace remote files."""
        pending = self.manager.pending
        uploads = [j for j in pending if j.direction is Direction.UPLOAD]
        if uploads and self.config.transfer.get("confirm_overwrite", True):
            # one probe serves both this question and the resume decisions
            clashes = await self.manager.probe_uploads(pending)
            if clashes:
                choice = await self.push_screen_wait(OverwriteScreen(clashes))
                if choice == "cancel":
                    self.log_line("[yellow]transfer cancelled[/] - nothing was sent")
                    return
                if choice == "skip":
                    self.manager.skip_jobs(clashes, "skipped: already on the server")
                    self.log_line(f"[yellow]skipped[/] {len(clashes)} upload(s) that would overwrite")
            await self.manager.run_queue(probe=False)
            return
        await self.manager.run_queue()

    def action_cancel(self) -> None:
        self.cancel_transfer()

    @work(group="cancel")
    async def cancel_transfer(self) -> None:
        await self.manager.stop()
        self.log_line("[yellow]cancel requested[/]")

    @work(exclusive=True, group="transfer")
    async def verify_worker(self, pattern: str) -> None:
        """Checksum-compare the two copies of the selected files.

        Acts on the source pane's selection, or the pattern if given, or the
        cursor entry. From the remote pane the other copy is local; from the
        local pane it is on the server. Reads both, transfers nothing.
        """
        src = self._source_pane()
        pane = self._pane(src)
        if pattern:
            targets = [e for e in pane.entries
                       if e.kind == "file" and fnmatch.fnmatch(e.name, pattern)]
        elif self.selected[src]:
            targets = [e for e in pane.entries if e.path in self.selected[src]]
        else:
            cur = pane.entry_at_cursor()
            targets = [cur] if cur and cur.kind == "file" else []
        targets = [e for e in targets if e.kind == "file"]
        if not targets:
            self.log_line("[dim]verify: select a file, or give a pattern[/]")
            return
        self.log_line(f"[bold]verifying[/] {len(targets)} file(s) by checksum - reads both copies")
        for e in targets:
            if src == "remote":
                await self.manager.verify(e.path, e.name, str(self.local.cwd),
                                          Direction.DOWNLOAD)
            else:
                await self.manager.verify(self.remote.cwd, e.name, e.path,
                                          Direction.UPLOAD)

    @work(exclusive=True, group="doctor")
    async def run_doctor_worker(self) -> None:
        await run_doctor(self.target, self.config.rsync_bin, self.local.cwd,
                         self.log_raw, remote_dir=self.remote.cwd)

    @work(exclusive=True, group="remote")
    async def remote_mkdir_worker(self, name: str) -> None:
        try:
            path = await self.remote.mkdir(name)
        except SshError as exc:
            self.log_line(f"[red]{escape(str(exc))}[/]")
            return
        self.log_line(f"[green]created[/] {escape(path)} on {escape(self.target.host)}")
        # list again from the same worker; a second exclusive worker in this
        # group would cancel this one
        try:
            entries = await self.remote.list_dir()
        except SshError as exc:
            self.log_line(f"[red]{escape(str(exc))}[/]")
            return
        self._pane("remote").populate(entries, self.selected["remote"])

    # -- command input --
    def on_input_submitted(self, event: Input.Submitted) -> None:
        raw = event.value.strip()
        event.input.value = ""
        if not raw:
            return
        if isinstance(event.input, CommandInput):
            event.input.remember(raw)
        self.log_line(f"[cyan]:[/] {escape(raw)}")
        parts = raw.split(None, 1)
        cmd = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""
        if cmd == "cd":
            if not arg:
                self.log_line("[dim]usage: cd REMOTE_DIR[/]")
                return
            self._enter_remote(self.remote.resolve(arg))
        elif cmd == "lcd":
            if not arg:
                self.log_line("[dim]usage: lcd LOCAL_DIR[/]")
            elif self.local.change_dir(arg):
                self.selected["local"].clear()
                self.refresh_local()
            else:
                self.log_line(f"[red]not a directory:[/] {escape(arg)}")
        elif cmd == "ls":
            self.refresh_remote()
        elif cmd == "ll":
            self._cmd_long_listing()
        elif cmd == "select":
            self._cmd_select(arg or "*")
        elif cmd == "deselect":
            self._cmd_deselect(arg or "*")
        elif cmd == "mkdir":
            self._cmd_mkdir(arg)
        elif cmd == "queue":
            self.action_queue()
        elif cmd == "download":
            self.download()
        elif cmd == "doctor":
            self.run_doctor_worker()
        elif cmd == "verify":
            self.verify_worker(arg or "")
        elif cmd == "version":
            self.log_raw(f"NCRsync {self.version.long()}")
        elif cmd == "clear":
            self.query_one("#log", RichLog).clear()
        elif cmd in ("quit", "exit", "q"):
            self.exit()
        else:
            self.log_line(f"[red]unknown command:[/] {cmd}")

    def _cmd_mkdir(self, name: str) -> None:
        """mkdir: create a directory in whichever pane is the source pane."""
        src = self._source_pane()
        if not name:
            self.log_line(f"[dim]usage: mkdir NAME  (creates it in the {src} pane)[/]")
            return
        if src == "remote":
            self.remote_mkdir_worker(name)
            return
        try:
            p = self.local.mkdir(name)
            self.refresh_local()
            self.log_line(f"[green]created[/] {escape(str(p))}")
        except OSError as exc:
            self.log_line(f"[red]mkdir failed:[/] {escape(str(exc))}")

    def _cmd_long_listing(self) -> None:
        """ll: long listing of the source pane (permissions, size, mtime)."""
        pane_id = self._source_pane()
        pane = self._pane(pane_id)
        cwd = str(self.local.cwd) if pane_id == "local" else self.remote.cwd
        self.log_line(f"[bold]{pane_id}[/] {escape(cwd)}:")
        for e in pane.entries:
            size = "<DIR>" if e.kind == "dir" else human_size(e.size)
            self.log_raw(f"  {e.permissions or '-':<11} {size:>8}  {e.mtime or '':<19}  {e.name}")

    def _cmd_select(self, pattern: str) -> None:
        src = self._source_pane()
        pane = self._pane(src)
        n = 0
        for e in pane.entries:
            if e.kind in ("file", "dir") and fnmatch.fnmatch(e.name, pattern):
                self.selected[src].add(e.path)
                n += 1
        self._repaint(src)
        self.log_line(f"[green]selected[/] {n} item(s) in the {src} pane matching {escape(repr(pattern))}")

    def _cmd_deselect(self, pattern: str) -> None:
        """Inverse of select: clear matching marks in the source pane and drop
        matching queued jobs, in either direction."""
        src = self._source_pane()
        pane = self._pane(src)
        unmarked = 0
        for e in pane.entries:
            if e.path in self.selected[src] and fnmatch.fnmatch(e.name, pattern):
                self.selected[src].discard(e.path)
                unmarked += 1
        self._repaint(src)
        removed = self.manager.remove_matching(pattern)
        self.log_line(
            f"[yellow]deselected[/] {unmarked} mark(s), removed {len(removed)} "
            f"queued job(s) matching {escape(repr(pattern))}"
        )
        if any(
            j.status is JobStatus.RUNNING and fnmatch.fnmatch(j.name.rstrip("/"), pattern)
            for j in self.manager.jobs
        ):
            self.log_line("[dim]running job kept - press F7 to cancel it[/]")

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
