# 06 - Configuration, Logging, and State

## 1. Config Location

```text
~/.config/ncrsync/config.toml
```

## 2. Example Config

```toml
default_host = "myserver"
rsync_bin = "/opt/homebrew/bin/rsync"

[ui]
theme = "nc-blue"
show_hidden = true
confirm_delete = true

[ssh]
compression = false
server_alive_interval = 30
server_alive_count_max = 6

[transfer]
append_verify = true
partial = true
timeout = 120
protect_args = true
bwlimit = 0
continue_on_error = false

[hosts.myserver]
default_remote_dir = "/downloads"
default_local_dir = "~/Downloads"
```

## 3. Log Location

macOS:

```text
~/Library/Logs/ncrsync/
```

Linux:

```text
~/.local/state/ncrsync/logs/
```

## 4. Log Files

```text
latest.log
session-YYYYMMDD-HHMMSS.log
```

## 5. Log Contents

Log version, command-line arguments, platform, local/remote rsync versions, SSH target, remote commands, queue operations, rsync argv, rsync output, and exceptions.

## 6. State Location

macOS:

```text
~/Library/Application Support/ncrsync/
```

Linux:

```text
~/.local/state/ncrsync/
```

## 7. State Files

```text
session.json
queue.json
recent_hosts.json
bookmarks.json
```

## 8. Queue State Example

```json
{
  "version": 1,
  "host": "myserver",
  "remote_cwd": "/downloads/tv",
  "local_cwd": "~/Downloads",
  "items": [
    {
      "remote_path": "/downloads/tv/file.mkv",
      "local_dest": "~/Downloads",
      "status": "queued",
      "last_error": null
    }
  ]
}
```

## 9. Startup Recovery

If queue state exists with unfinished jobs, ask whether to resume, discard, or view.

## 10. Doctor Command

Checks local rsync, remote SSH, remote rsync, destination writability, `--append-verify`, and `-s` support.
