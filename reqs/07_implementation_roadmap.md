# 07 - Implementation Roadmap

## Phase 0 - Textual Skeleton

Goal: create a running Textual app with Header, Footer, remote pane placeholder, local pane placeholder, queue pane, log pane, command input, and key bindings.

Exit criteria: `python -m ncrsync 80078` opens a UI.

## Phase 1 - Real Browsing

Goal: remote and local panes show real files.

Features: local listing, remote listing over SSH, cd into directory, parent directory, refresh, selection.

Exit criteria: user can browse `/downloads/tv` on remote host.

## Phase 2 - Queue

Goal: selectable files can be queued.

Features: Space selection, F6 queue, QueuePane updates, queue stored in memory, remove from queue.

Exit criteria: user can queue multiple remote files.

## Phase 3 - Rsync Transfer

Goal: perform real downloads.

Features: RsyncRunner, TransferManager, live raw rsync log, progress parser, stop on error, partial files preserved.

Exit criteria: user can download selected files to local pane.

## Phase 4 - Persistence

Goal: recover after quit/crash.

Features: config file, queue.json, recent paths, session restoration, latest log.

Exit criteria: interrupted queue can resume after relaunch.

## Phase 5 - Polish

Features: NC blue theme, better status bar, doctor command, dry-run, bandwidth limit, error dialogs, bookmarks.

## Phase 6 - Packaging

Features: `pyproject.toml`, CLI entrypoint `ncrsync`, pipx install, tests, README, screenshots.

## Phase 7 - Advanced

Potential features: SFTP browsing backend, upload support, checksumming, multi-host bookmarks, search, tmux-friendly detached transfer mode, desktop notifications.
