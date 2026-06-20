# 01 - Product Requirements

## 1. Goals

NCRsync shall provide a terminal UI for browsing local and remote filesystems and downloading files from remote hosts using rsync.

## 2. Non-goals for v1

NCRsync v1 shall not attempt to be a general backup system, bidirectional sync engine, cloud file manager, full Midnight Commander replacement, Windows-first application, or daemon/server application.

## 3. Required v1 Features

### 3.1 Start with SSH Target

```bash
ncrsync myserver
ncrsync user@example.com
ncrsync "user@example.com -p 2222"
```

The target may be an entry in `~/.ssh/config`, a direct `user@host`, or a direct SSH argument string.

### 3.2 Dual-pane UI

The program shall show a remote pane, local pane, queue/status/log area, command input or command palette, and footer with function key hints.

### 3.3 Remote Browsing

The user shall be able to list remote directory, enter directory, go to parent, refresh, view long metadata, and select files/directories.

### 3.4 Local Browsing

The user shall be able to list local directory, change destination directory, view partial/completed files, and create local directories.

### 3.5 Selection

The user shall be able to select files using cursor + Space, pattern selection, Enter on file, and command line: `select PATTERN`.

### 3.6 Transfer Queue

The user shall be able to add selected items to queue, remove from queue, clear queue, view queue, start transfer, stop transfer, and resume later.

### 3.7 Rsync Downloads

Downloads shall use rsync over SSH.

Default mode optimized for large compressed media:

```bash
rsync -av -s --partial --append-verify --info=progress2 --human-readable --timeout=120
```

SSH options:

```bash
-o Compression=no
-o ServerAliveInterval=30
-o ServerAliveCountMax=6
```

### 3.8 Logging

The program shall log session information, remote commands, queue operations, rsync command argv, rsync stdout/stderr, errors, and completion/failure.

### 3.9 Diagnostics

The program shall provide a `doctor` command that checks local rsync version, remote rsync version, SSH connectivity, local destination writability, support for `--append-verify`, and support for `-s` / `--protect-args`.

## 4. Success Criteria

A successful v1 allows a user to download a file with a path such as:

```text
/downloads/tv/show.s03.complete.720p/release[bracket]/show.s03e01.mkv
```

without path quoting bugs, and resume after interruption.
