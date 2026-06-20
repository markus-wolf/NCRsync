# NCRsync

A Norton Commander / Midnight Commander inspired terminal file manager for remote SSH hosts, optimized for reliable large-file downloads using `rsync`.

NCRsync is not just an rsync wrapper. It is a keyboard-first, dual-pane TUI where one pane browses a remote host over SSH, the other browses your local filesystem, and transfers run through a queued rsync engine with resume support, persistent state, and logging.

## Features

- Dual-pane remote and local file browsing
- SSH remote access (no server-side agent required)
- Rsync transfer queue with resumable downloads
- Session, queue, and recent-host persistence across restarts
- In-app `doctor` command for environment checks
- Command-line and function-key driven UI built with [Textual](https://textual.textualize.io/)

## Requirements

- **Python** 3.11 or newer
- **rsync** 3.x on the client (Homebrew rsync on macOS is recommended)
- **SSH** access to the remote host
- **Primary target:** macOS client connecting to a Linux remote host

## Install

Clone the repository and create a virtual environment:

```bash
git clone <repo-url> NCRsync
cd NCRsync
python3 -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

For development (tests):

```bash
pip install -r requirements-dev.txt
```

## Run

From the project root with the virtual environment activated:

```bash
python -m ncrsync TARGET
```

`TARGET` is an SSH host alias or connection string, for example:

```bash
python -m ncrsync 80078
python -m ncrsync alex@example.com
python -m ncrsync "alex@example.com -p 2222"
```

If `default_host` is set in config (see below), you can omit the target:

```bash
python -m ncrsync
```

Inside the app, type commands at the `:` prompt (`cd`, `lcd`, `select`, `queue`, `download`, `doctor`, `quit`, etc.) or use the function keys shown in the footer.

## Configuration

Optional settings live at:

```text
~/.config/ncrsync/config.toml
```

Example:

```toml
default_host = "80078"
rsync_bin = "/opt/homebrew/bin/rsync"

[ui]
theme = "nc-blue"
show_hidden = true

[transfer]
append_verify = true
partial = true

[hosts.80078]
default_remote_dir = "/downloads"
default_local_dir = "~/Downloads"
```

Logs and application state are stored outside the repo under `~/Library/Logs/ncrsync/` and `~/Library/Application Support/ncrsync/` on macOS.

## Tests

```bash
pytest
```

## Specifications

Design documents, architecture notes, and the implementation roadmap are in [`reqs/`](reqs/README.md).
