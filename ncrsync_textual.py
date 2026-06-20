#!/usr/bin/env python3
"""NCRsync - single-file Textual prototype.

A Norton Commander style dual-pane terminal file manager for remote SSH hosts,
using rsync for reliable, resumable downloads.

This is the doc-08 prototype: get the download path correct in one file, then
split into the package layout from doc-03. It intentionally avoids mouse,
uploads, remote delete, multi-host, and detached transfers.

Usage:
    python ncrsync_textual.py 80078
    python ncrsync_textual.py alex@example.com
    python ncrsync_textual.py "alex@example.com -p 2222"
"""
from __future__ import annotations

import asyncio
import fnmatch
import os
import posixpath
import shlex
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional

from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Footer, Header, Input, RichLog

# --- Defaults (mirrors docs 04 / 06; real config loader comes later) ---------

RSYNC_BIN = "/opt/homebrew/bin/rsync"
if not os.path.exists(RSYNC_BIN):
    RSYNC_BIN = "rsync"  # fall back to PATH

SSH_OPTS_KEEPALIVE = [
    "-o", "Compression=no",
    "-o", "ServerAliveInterval=30",
    "-o", "ServerAliveCountMax=6",
]


# --- Model -------------------------------------------------------------------


@dataclass
class FileEntry:
    name: str
    path: str  # absolute path in its own namespace (remote or local)
    kind: Literal["file", "dir", "symlink", "other"]
    size: Optional[int] = None
    mtime: Optional[str] = None
    permissions: Optional[str] = None


@dataclass
class TransferJob:
    remote_path: str
    local_dest: str
    name: str
    status: str = "queued"  # queued|running|completed|failed|cancelled
    last_error: Optional[str] = None


# --- SSH target parsing ------------------------------------------------------


@dataclass
class SshTarget:
    """Parsed from the CLI target argument.

    Splits a target like ``alex@host -p 2222`` into the host token (used for the
    rsync ``host:path`` source) and the remaining ssh options.
    """

    host: str
    opts: list[str] = field(default_factory=list)

    @classmethod
    def parse(cls, raw: str) -> "SshTarget":
        parts = shlex.split(raw)
        host = None
        opts: list[str] = []
        takes_value = {"-p", "-i", "-o", "-l", "-F", "-J", "-c", "-m"}
        i = 0
        while i < len(parts):
            p = parts[i]
            if p.startswith("-"):
                opts.append(p)
                if p in takes_value and i + 1 < len(parts):
                    opts.append(parts[i + 1])
                    i += 1
            elif host is None:
                host = p
            else:
                # extra bareword; treat as ssh arg
                opts.append(p)
            i += 1
        if host is None:
            raise ValueError(f"could not find a host in target: {raw!r}")
        return cls(host=host, opts=opts)

    def ssh_argv(self, remote_command: str) -> list[str]:
        """argv to run a command on the remote shell."""
        return ["ssh", *self.opts, self.host, remote_command]

    def rsync_e_value(self) -> str:
        """Value for rsync's ``-e`` (transport) option."""
        return shlex.join(["ssh", *self.opts, *SSH_OPTS_KEEPALIVE])


# --- Helpers -----------------------------------------------------------------


def human_size(n: Optional[int]) -> str:
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
    # dirs first, files second, others last; case-insensitive name.
    rank = {"dir": 0, "file": 1, "symlink": 1, "other": 2}
    return sorted(entries, key=lambda e: (rank.get(e.kind, 2), e.name.lower()))


# Remote find listing. printf escapes (\t \n) are interpreted by find on the
# remote, so they are sent as literal backslash sequences.
_FIND_PRINTF = r"%y\t%s\t%TY-%Tm-%Td %TH:%TM:%TS\t%M\t%f\n"


def build_remote_list_cmd(remote_cwd: str) -> str:
    """Remote shell command string. remote_cwd is shell-quoted (shell context)."""
    return (
        f"cd {shlex.quote(remote_cwd)} && "
        f"find . -maxdepth 1 -mindepth 1 -printf '{_FIND_PRINTF}' "
        f"2>/dev/null || (cd {shlex.quote(remote_cwd)} && ls -la)"
    )


def parse_find_output(text: str, remote_cwd: str) -> list[FileEntry]:
    entries: list[FileEntry] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        cols = line.split("\t")
        if len(cols) != 5:
            continue  # likely an ls -la fallback line; skipped in prototype
        ftype, size, mtime, perms, name = cols
        kind: Literal["file", "dir", "symlink", "other"]
        if ftype == "d":
            kind = "dir"
        elif ftype == "f":
            kind = "file"
        elif ftype == "l":
            kind = "symlink"
        else:
            kind = "other"
        try:
            size_int: Optional[int] = int(size)
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


def list_local(local_cwd: Path) -> list[FileEntry]:
    entries: list[FileEntry] = []
    for child in local_cwd.iterdir():
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
        from datetime import datetime

        entries.append(
            FileEntry(
                name=child.name,
                path=str(child.resolve()),
                kind=kind,
                size=st.st_size if kind == "file" else None,
                mtime=datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            )
        )
    return entries


def build_rsync_argv(target: SshTarget, remote_path: str, local_dest: str) -> list[str]:
    """Build rsync argv. The source ``host:path`` is NOT shell-quoted (doc-03)."""
    source = f"{target.host}:{remote_path}"
    dest = local_dest if local_dest.endswith("/") else local_dest + "/"
    return [
        RSYNC_BIN,
        "-av",
        "-s",
        "--partial",
        "--append-verify",
        "--info=progress2",
        "--human-readable",
        "--timeout=120",
        "-e", target.rsync_e_value(),
        source,
        dest,
    ]


def remote_resolve(remote_cwd: str, arg: str) -> str:
    if arg.startswith("/"):
        new = arg
    else:
        new = posixpath.join(remote_cwd, arg)
    return posixpath.normpath(new)


# --- App ---------------------------------------------------------------------


class NCRsync(App):
    CSS = """
    #panes { height: 1fr; }
    #remote, #local { width: 1fr; border: round $primary; }
    #remote:focus-within, #local:focus-within { border: round $accent; }
    #queue { height: 7; border: round $secondary; }
    #log { height: 1fr; border: round $secondary; }
    #command { dock: bottom; }
    DataTable { height: 1fr; }
    """

    BINDINGS = [
        ("tab", "switch_pane", "Switch Pane"),
        ("f5", "copy", "Download"),
        ("f6", "queue", "Queue"),
        ("f8", "remove", "Remove"),
        ("f10", "quit", "Quit"),
        ("ctrl+r", "refresh", "Refresh"),
        ("space", "toggle_select", "Select"),
        ("backspace", "parent_dir", "Parent"),
    ]

    def __init__(self, target_raw: str, **kwargs):
        super().__init__(**kwargs)
        self.target_raw = target_raw
        self.target = SshTarget.parse(target_raw)
        self.remote_cwd = "/downloads"
        self.local_cwd = Path.home() / "Downloads"
        if not self.local_cwd.exists():
            self.local_cwd = Path.home()
        self.remote_selected: set[str] = set()
        self.remote_entries: list[FileEntry] = []
        self.local_entries: list[FileEntry] = []
        self.queue: list[TransferJob] = []
        self.active_pane = "remote"

    # -- layout --
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="panes"):
            yield DataTable(id="remote")
            yield DataTable(id="local")
        yield DataTable(id="queue")
        yield RichLog(id="log", highlight=True, markup=True, wrap=False)
        yield Input(placeholder=": command (cd, lcd, select, queue, download, doctor, quit)", id="command")
        yield Footer()

    def on_mount(self) -> None:
        self._update_title()
        for tid, cols in (
            ("remote", ("", "name", "size", "mtime")),
            ("local", ("", "name", "size", "mtime")),
            ("queue", ("status", "file")),
        ):
            t = self.query_one(f"#{tid}", DataTable)
            t.cursor_type = "row"
            t.zebra_stripes = True
            t.add_columns(*cols)
        self.log_line(f"[bold]NCRsync[/] prototype - target [b]{self.target.host}[/] (opts: {self.target.opts or 'none'})")
        self.log_line(f"rsync: {RSYNC_BIN}")
        self.query_one("#remote", DataTable).focus()
        self.refresh_local()
        self.refresh_remote()

    def _update_title(self) -> None:
        self.title = "NCRsync"
        self.sub_title = f"{self.target.host} | R:{self.remote_cwd} | L:{self.local_cwd}"

    def log_line(self, msg: str) -> None:
        self.query_one("#log", RichLog).write(msg)

    # -- focus tracking --
    def on_descendant_focus(self, event) -> None:
        w = event.widget
        if getattr(w, "id", None) in ("remote", "local"):
            self.active_pane = w.id

    def _active_table(self) -> DataTable:
        return self.query_one(f"#{self.active_pane}", DataTable)

    # -- rendering --
    def _populate(self, table_id: str, entries: list[FileEntry], selected: set[str]) -> None:
        t = self.query_one(f"#{table_id}", DataTable)
        prev = t.cursor_row
        t.clear()
        for e in entries:
            mark = "*" if e.path in selected else ""
            name = (f"[b]{e.name}/[/]" if e.kind == "dir" else e.name)
            size = "<DIR>" if e.kind == "dir" else human_size(e.size)
            t.add_row(mark, name, size, e.mtime or "", key=e.path)
        if entries:
            t.move_cursor(row=min(prev, len(entries) - 1))

    def _entry_at_cursor(self, pane: str) -> Optional[FileEntry]:
        entries = self.remote_entries if pane == "remote" else self.local_entries
        t = self.query_one(f"#{pane}", DataTable)
        if not entries or t.cursor_row is None or t.cursor_row >= len(entries):
            return None
        return entries[t.cursor_row]

    def _refresh_queue_table(self) -> None:
        t = self.query_one("#queue", DataTable)
        t.clear()
        for j in self.queue:
            t.add_row(j.status, j.name)

    # -- remote / local loading --
    @work(exclusive=True, group="remote")
    async def refresh_remote(self) -> None:
        cmd = build_remote_list_cmd(self.remote_cwd)
        argv = self.target.ssh_argv(cmd)
        self.log_line(f"[dim]$ {shlex.join(argv)}[/]")
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            out, err = await proc.communicate()
        except FileNotFoundError:
            self.log_line("[red]ssh not found[/]")
            return
        if proc.returncode != 0:
            self.log_line(f"[red]remote list failed (rc={proc.returncode})[/] {err.decode(errors='replace').strip()}")
            return
        entries = sort_entries(parse_find_output(out.decode(errors="replace"), self.remote_cwd))
        self.remote_entries = entries
        self._populate("remote", entries, self.remote_selected)
        self.log_line(f"[green]remote[/] {self.remote_cwd}: {len(entries)} entries")

    def refresh_local(self) -> None:
        try:
            entries = sort_entries(list_local(self.local_cwd))
        except OSError as exc:
            self.log_line(f"[red]local list failed:[/] {exc}")
            return
        self.local_entries = entries
        self._populate("local", entries, set())
        self._update_title()

    # -- actions --
    def action_switch_pane(self) -> None:
        nxt = "local" if self.active_pane == "remote" else "remote"
        self.query_one(f"#{nxt}", DataTable).focus()

    def action_refresh(self) -> None:
        if self.active_pane == "remote":
            self.refresh_remote()
        else:
            self.refresh_local()

    def action_toggle_select(self) -> None:
        if self.active_pane != "remote":
            return
        e = self._entry_at_cursor("remote")
        if e is None:
            return
        if e.path in self.remote_selected:
            self.remote_selected.discard(e.path)
        else:
            self.remote_selected.add(e.path)
        self._populate("remote", self.remote_entries, self.remote_selected)

    def action_parent_dir(self) -> None:
        if self.active_pane == "remote":
            self.remote_cwd = posixpath.normpath(posixpath.join(self.remote_cwd, ".."))
            self.remote_selected.clear()
            self._update_title()
            self.refresh_remote()
        else:
            self.local_cwd = self.local_cwd.parent
            self.refresh_local()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        # Enter on a row: descend into directories.
        pane = event.data_table.id
        if pane not in ("remote", "local"):
            return
        e = self._entry_at_cursor(pane)
        if e is None or e.kind != "dir":
            return
        if pane == "remote":
            self.remote_cwd = e.path
            self.remote_selected.clear()
            self._update_title()
            self.refresh_remote()
        else:
            self.local_cwd = Path(e.path)
            self.refresh_local()

    def action_queue(self) -> None:
        # queue current remote selection (or the cursor entry if none selected)
        paths = set(self.remote_selected)
        if not paths:
            e = self._entry_at_cursor("remote")
            if e and e.kind == "file":
                paths = {e.path}
        added = 0
        existing = {j.remote_path for j in self.queue}
        for e in self.remote_entries:
            if e.path in paths and e.kind == "file" and e.path not in existing:
                self.queue.append(
                    TransferJob(remote_path=e.path, local_dest=str(self.local_cwd), name=e.name)
                )
                added += 1
        self.remote_selected.clear()
        self._populate("remote", self.remote_entries, self.remote_selected)
        self._refresh_queue_table()
        self.log_line(f"[green]queued[/] {added} item(s); queue size {len(self.queue)}")

    def action_remove(self) -> None:
        if self.active_pane == "remote":
            return
        # remove the queue row under the queue cursor
        t = self.query_one("#queue", DataTable)
        if self.queue and t.cursor_row is not None and t.cursor_row < len(self.queue):
            removed = self.queue.pop(t.cursor_row)
            self._refresh_queue_table()
            self.log_line(f"[yellow]removed[/] {removed.name}")

    def action_copy(self) -> None:
        self.start_download()

    # -- transfer --
    @work(exclusive=True, group="transfer")
    async def start_download(self) -> None:
        pending = [j for j in self.queue if j.status in ("queued", "failed")]
        if not pending:
            self.log_line("[yellow]queue empty[/] (nothing to download)")
            return
        self.log_line(f"[bold]starting download[/] of {len(pending)} job(s) -> {self.local_cwd}/")
        for job in pending:
            job.status = "running"
            job.last_error = None
            self._refresh_queue_table()
            argv = build_rsync_argv(self.target, job.remote_path, str(self.local_cwd))
            self.log_line(f"[dim]$ {shlex.join(argv)}[/]")
            rc = await self._run_rsync(argv)
            if rc == 0:
                job.status = "completed"
                self.log_line(f"[green]done[/] {job.name}")
            else:
                job.status = "failed"
                job.last_error = f"rsync rc={rc}"
                self.log_line(f"[red]failed[/] {job.name} (rc={rc}) - stopping queue, partial preserved")
                self._refresh_queue_table()
                break  # default: stop on first failure (doc-04)
            self._refresh_queue_table()

    async def _run_rsync(self, argv: list[str]) -> int:
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
        except FileNotFoundError:
            self.log_line("[red]rsync not found[/]")
            return 127
        log = self.query_one("#log", RichLog)
        assert proc.stdout is not None
        buf = ""
        while True:
            chunk = await proc.stdout.read(4096)
            if not chunk:
                break
            buf += chunk.decode(errors="replace").replace("\r", "\n")
            *lines, buf = buf.split("\n")
            for line in lines:
                if line.strip():
                    log.write(line)
        if buf.strip():
            log.write(buf)
        return await proc.wait()

    # -- doctor --
    @work(exclusive=True, group="doctor")
    async def run_doctor(self) -> None:
        self.log_line("[bold]doctor[/] running checks...")

        async def run(argv: list[str]) -> tuple[int, str]:
            try:
                p = await asyncio.create_subprocess_exec(
                    *argv,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                )
                out, _ = await p.communicate()
                return p.returncode, out.decode(errors="replace")
            except FileNotFoundError:
                return 127, "not found"

        rc, out = await run([RSYNC_BIN, "--version"])
        ver = out.splitlines()[0] if out else "?"
        self.log_line(f"  local rsync: {'[green]ok[/]' if rc == 0 else '[red]MISSING[/]'} {ver}")
        if "--append-verify" in out or rc == 0:
            self.log_line("  [yellow]note:[/] --append-verify is deprecated in rsync 3.2+ (maps to --append)")

        rc, out = await run(self.target.ssh_argv("echo ncrsync-ok"))
        self.log_line(f"  ssh connectivity: {'[green]ok[/]' if 'ncrsync-ok' in out else '[red]FAILED[/]'}")

        rc, out = await run(self.target.ssh_argv("rsync --version 2>/dev/null | head -1"))
        self.log_line(f"  remote rsync: {('[green]' + out.strip() + '[/]') if rc == 0 and out.strip() else '[red]unknown[/]'}")

        writable = os.access(self.local_cwd, os.W_OK)
        self.log_line(f"  dest writable ({self.local_cwd}): {'[green]yes[/]' if writable else '[red]NO[/]'}")

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
        if cmd == "cd":
            if arg:
                self.remote_cwd = remote_resolve(self.remote_cwd, arg)
                self.remote_selected.clear()
                self._update_title()
                self.refresh_remote()
        elif cmd == "lcd":
            if arg:
                new = (self.local_cwd / arg).expanduser() if not arg.startswith("/") else Path(arg).expanduser()
                if new.is_dir():
                    self.local_cwd = new.resolve()
                    self.refresh_local()
                else:
                    self.log_line(f"[red]not a directory:[/] {new}")
        elif cmd in ("ls", "ll"):
            self.refresh_remote()
        elif cmd == "select":
            self._cmd_select(arg or "*")
        elif cmd == "queue":
            self.action_queue()
        elif cmd == "download":
            self.start_download()
        elif cmd == "doctor":
            self.run_doctor()
        elif cmd == "clear":
            self.query_one("#log", RichLog).clear()
        elif cmd in ("quit", "exit", "q"):
            self.exit()
        else:
            self.log_line(f"[red]unknown command:[/] {cmd}")

    def _cmd_select(self, pattern: str) -> None:
        n = 0
        for e in self.remote_entries:
            if e.kind == "file" and fnmatch.fnmatch(e.name, pattern):
                self.remote_selected.add(e.path)
                n += 1
        self._populate("remote", self.remote_entries, self.remote_selected)
        self.log_line(f"[green]selected[/] {n} item(s) matching {pattern!r}")


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        print("error: a target is required, e.g.  ncrsync_textual.py 80078", file=sys.stderr)
        sys.exit(2)
    target = sys.argv[1]
    NCRsync(target).run()


if __name__ == "__main__":
    main()
