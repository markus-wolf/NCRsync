# NCRsync

A Norton Commander / Midnight Commander inspired terminal file manager for remote SSH hosts, optimized for reliable large-file downloads using `rsync`.

NCRsync is not just an rsync wrapper. It is a keyboard-first, dual-pane TUI where one pane browses a remote host over SSH, the other browses your local filesystem, and transfers run through a queued rsync engine with resume support, persistent state, and logging.

## Features

- Dual-pane remote and local file browsing
- SSH remote access (no server-side agent required)
- Rsync transfer queue with resumable downloads (files and whole directories)
- Cancel (F7) keeps the partial file; transient network failures retry
  automatically with backoff and resume where they left off
- rsync capability auto-detection: resume/path-safety/progress flags are chosen
  from the effective version of both ends (see *Transfers* below)
- Session, queue, and recent-host persistence across restarts, with a
  Resume/View/Discard prompt after an interrupted queue
- In-app `doctor` command for environment checks
- Command-line (with arrow-key history) and function-key driven UI built with
  [Textual](https://textual.textualize.io/), NC-blue theme included

## Requirements

- **Python** 3.11 or newer
- **rsync** 3.x on the client (Homebrew rsync on macOS is recommended)
- **SSH** access to the remote host
- **Primary target:** macOS client connecting to a Linux remote host

## Install

The project is managed with [uv](https://docs.astral.sh/uv/). Clone and sync:

```bash
git clone https://github.com/markus-wolf/NCRsync.git
cd NCRsync
uv sync
```

`uv sync` creates `.venv`, installs pinned dependencies from `uv.lock` (dev
tools included), and installs the `ncrsync` command.

To try it without cloning:

```bash
uvx --from git+https://github.com/markus-wolf/NCRsync ncrsync myserver
```

or install it as a persistent tool: `uv tool install git+https://github.com/markus-wolf/NCRsync`.

## Run

From the project root:

```bash
uv run ncrsync TARGET
```

`TARGET` is an SSH host alias or connection string, for example:

```bash
uv run ncrsync myserver
uv run ncrsync user@example.com
uv run ncrsync "user@example.com -p 2222"
```

If `default_host` is set in config (see below), you can omit the target. With
the venv activated (`source .venv/bin/activate`), plain `ncrsync TARGET` and
`python -m ncrsync TARGET` also work.

Inside the app, type commands at the `:` prompt or use the function keys shown
in the footer. Run `doctor` after the first connect: it verifies SSH
connectivity, local/remote rsync versions (and the resulting capability tier),
and destination writability.

### Keys

| Key | Action |
|---|---|
| Tab | Switch between remote and local pane |
| Shift+Tab | Cycle focus (panes, queue, command line) |
| Enter | Enter directory / toggle selection on a remote file |
| Space | Toggle selection (remote pane) |
| Backspace | Parent directory (focused pane) |
| Ctrl+R | Refresh focused pane |
| F5 | Start downloading the queue |
| F6 | Queue selected items (files and directories) |
| F7 | Cancel the running transfer (partial file kept) |
| F8 | Remove queued item (focus the queue first; running jobs must be cancelled) |
| F10 | Quit |

### Commands

`cd DIR` (remote), `lcd DIR` (local), `ls`, `ll` (long listing with
permissions), `select PATTERN` (glob; matches files and directories), `queue`,
`download`, `doctor`, `mkdir NAME` (local), `clear`, `quit`. The `:` prompt
keeps arrow-up/down history.

## Transfers

rsync runs with `-av --partial --human-readable --timeout=120` plus SSH
keepalives. Resume, path-safety, and progress flags are auto-selected from the
effective rsync version, `min(local, remote)`:

| Effective rsync | path safety | resume | progress |
|---|---|---|---|
| >= 3.2 | `-s` | `--append` | `--info=progress2` |
| 3.0 – 3.1 | `-s` | `--append-verify` | 3.1: `progress2`, 3.0: `--progress` |
| < 3.0 (degraded) | quoted paths + warning | `--partial` only | `--progress` |

Transient failures (rsync exit 10/12/30/35) retry automatically up to
`max_retries` with backoff; other failures stop the queue unless
`continue_on_error` is set. Remote shell commands are always shell-quoted while
the rsync `host:path` source is passed raw under `-s`, so paths like
`Movie (2019) [1080p] [YTS.MX]/file.mp4` transfer verbatim.

## Configuration

Optional settings live at:

```text
~/.config/ncrsync/config.toml
```

Example:

```toml
default_host = "myserver"
rsync_bin = "/opt/homebrew/bin/rsync"

[ui]
theme = "nc-blue"        # or any built-in Textual theme
show_hidden = true

[transfer]
append_verify = true     # resume via --append/--append-verify
partial = true
protect_args = true      # set false to force legacy path quoting (no -s)
timeout = 120
bwlimit = 0              # KiB/s, 0 = unlimited
continue_on_error = false
max_retries = 3
retry_delay_seconds = 5

[hosts.myserver]
default_remote_dir = "/downloads"
default_local_dir = "~/Downloads"
```

Logs and application state are stored outside the repo under `~/Library/Logs/ncrsync/` and `~/Library/Application Support/ncrsync/` on macOS.

## Tests

```bash
uv run pytest
```

## Specifications

Design documents, architecture notes, and the implementation roadmap are in [`reqs/`](reqs/README.md).
