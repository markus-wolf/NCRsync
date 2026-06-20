# 08 - Textual Prototype Plan

## 1. Immediate Goal

Replace the curses prototype with a minimal Textual app that can connect to an SSH alias, display remote listing, display local listing, select a remote file, queue it, run rsync, and show rsync output.

## 2. Dependencies

```bash
brew install rsync
python3 -m venv .venv
source .venv/bin/activate
pip install textual
```

Optional:

```bash
pip install textual-dev
```

## 3. First Prototype File

Start with a single file:

```text
ncrsync_textual.py
```

Only after it works, split into package modules.

## 4. Minimal UI

Textual widgets:

```python
Header()
Footer()
DataTable(id="remote")
DataTable(id="local")
DataTable(id="queue")
RichLog(id="log")
Input(id="command")
```

## 5. Minimal Commands

```text
cd DIR
lcd DIR
select PATTERN
queue
download
doctor
quit
```

## 6. Async Remote Listing

Use Textual worker or asyncio subprocesses.

## 7. Rsync Runner

Initial command builder:

```python
source = f"{host}:{remote_path}"

cmd = [
    rsync_bin,
    "-av",
    "-s",
    "--partial",
    "--append-verify",
    "--info=progress2",
    "--human-readable",
    "--timeout=120",
    "-e",
    "ssh -o Compression=no -o ServerAliveInterval=30 -o ServerAliveCountMax=6",
    source,
    str(local_dest) + "/",
]
```

## 8. First Test Case

Remote path:

```text
/downloads/tv/show.s03.complete.720p/release[bracket]/show.s03e01.mkv
```

This verifies absolute remote paths, brackets in directory name, no embedded quote bug, and rsync `-s` behavior.

## 9. Debug Output

Always show the actual argv in the log pane.

## 10. Avoid Premature Complexity

Do not implement initially: mouse, uploads, remote delete, multiple hosts, plugins, detached transfer daemon. Get the download path correct first.
