# 03 - Architecture

## 1. Architectural Principle

Separate UI, remote browsing, transfer engine, state, and configuration. Textual should not directly contain rsync or SSH command construction logic.

## 2. Proposed Package Layout

```text
ncrsync/
  __init__.py
  main.py
  app.py
  screens.py
  ui/
    remote_pane.py
    local_pane.py
    queue_pane.py
    command_input.py
    transfer_log.py
    dialogs.py
  model/
    file_entry.py
    transfer_job.py
    connection_profile.py
  remote/
    ssh_client.py
    remote_browser.py
    path_utils.py
  local/
    local_browser.py
  transfer/
    rsync_runner.py
    transfer_manager.py
    progress_parser.py
  state/
    state_store.py
    queue_store.py
  config/
    config_loader.py
    defaults.py
  diagnostics/
    doctor.py
  logging_setup.py
```

## 3. Main Components

### App

Owns the Textual lifecycle, initializes config/state, creates panes, manages global key bindings, and coordinates high-level actions.

### RemoteBrowser

Runs remote list commands, parses directory entries, manages remote cwd, and handles remote path escaping for shell commands.

### LocalBrowser

Lists local files, manages local cwd, creates local directories, and detects partial downloads.

### TransferManager

Queues jobs, starts/stops transfers, serializes job state, invokes RsyncRunner, and updates UI via events/messages.

### RsyncRunner

Builds safe rsync argv, runs subprocess asynchronously, streams output, parses progress opportunistically, and returns exit status.

### StateStore

Saves current host, current directories, transfer queue, recent paths, and bookmarks.

## 4. Textual Event Flow

Queue file:

```text
RemotePane selected rows -> App.action_queue() -> TransferManager.add_jobs() -> QueuePane.refresh() -> StateStore.save_queue()
```

Start download:

```text
App.action_copy() -> TransferManager.start() -> RsyncRunner.run_async() -> progress events -> QueuePane / ProgressBar / TransferLog update
```

## 5. Async Model

Use Textual workers or asyncio subprocesses. The UI thread must remain responsive.

## 6. Path Safety Rule

There are two distinct quoting contexts.

Remote shell commands use shell quoting:

```python
shlex.quote(remote_path)
```

Rsync argv must not shell quote the remote path inside `host:path`:

```python
source = f"{host}:{remote_absolute_path}"
argv = ["rsync", "-av", "-s", source, local_dest]
```

## 7. Logging

Every subprocess argv should be logged in reproducible shell form, but the actual subprocess should receive argv list form.
