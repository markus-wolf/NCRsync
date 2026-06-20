# 04 - Transfer Engine

## 1. Backend

v1 transfer backend: rsync over SSH.

## 2. Default Rsync Args

```python
[
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
    destination,
]
```

## 3. Source Format

Correct source format:

```text
80078:/absolute/remote/path/file.mkv
```

No embedded quotes.

## 4. Destination Format

Destination should be a local directory ending in `/`.

## 5. Job State Machine

```text
Queued -> Running -> Completed
Queued -> Running -> Failed
Queued -> Running -> Cancelled
Queued -> Skipped
```

Optional later states: `Paused`, `Verifying`, `Retrying`.

## 6. Failure Behavior

Default behavior: stop queue on first failed job, preserve partial file, show error, allow user to resume.

Optional config:

```toml
continue_on_error = true
```

## 7. Resume Strategy

Preferred:

```bash
--partial --append-verify
```

Fallback:

```bash
--partial --progress
```

## 8. Bandwidth Limit

Optional per-session or per-host:

```bash
--bwlimit=4000
```

Unit: KiB/s as rsync expects.

## 9. Progress Parsing

Parse rsync output opportunistically. Raw output is authoritative and must always be logged.

Fields to extract where possible: bytes transferred, percent, rate, ETA.

## 10. Cancellation

Cancel should send SIGINT or terminate subprocess, wait briefly, force kill if needed, mark job cancelled, and keep partial file.

## 11. Retry

Retries should be explicit in v1. Later config may add `max_retries` and `retry_delay_seconds`.

## 12. Verification

Default verification relies on rsync and size comparison where possible. Optional `verify` can run dry-run checksum mode, but not by default because it is expensive for video files.
