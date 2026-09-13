# 01 - Product Requirements

## 1. Goals

NCRsync shall provide a terminal UI for browsing local and remote filesystems and downloading files from remote hosts using rsync.

*Amended in 0.6.0:* NCRsync also uploads — copies files from the local system to the remote host. Direction is chosen per item by the pane it is selected in. See §3.10.

## 2. Non-goals for v1

NCRsync v1 shall not attempt to be a general backup system, bidirectional sync engine, cloud file manager, full Midnight Commander replacement, Windows-first application, or daemon/server application.

Uploads (§3.10) do not contradict the sync non-goal: each transfer is an explicit one-way copy of items the user selected. NCRsync never reconciles two trees, propagates deletions, or decides on its own which side is newer.

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

*Amended in 0.6.0:* `doctor` also reports remote directory writability and free space on both sides, since uploads write to the remote host.

### 3.10 Uploads (added in 0.6.0)

The user shall be able to copy files and directories from the local system to the remote host.

- Direction is decided when an item is queued, from the pane it was selected in: the remote pane queues a download into the local directory, the local pane queues an upload into the remote directory. One queue may hold both.
- Selection (Space, Enter, `select`, `deselect`) works in both panes, independently.
- The resume and path-safety rules of §3.7 apply unchanged, with the remote end taking the role of destination. Append-resume is used only onto a partial NCRsync itself wrote.
- An upload that would replace a file already on the remote host requires confirmation (Overwrite / Skip / Cancel), unless disabled by `transfer.confirm_overwrite = false`. Downloads are not prompted.
- `mkdir` creates the directory on whichever side the source pane represents.

## 4. Success Criteria

A successful v1 allows a user to download a file with a path such as:

```text
/downloads/tv/show.s03.complete.720p/release[bracket]/show.s03e01.mkv
```

without path quoting bugs, and resume after interruption.
