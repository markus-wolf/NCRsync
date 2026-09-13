# Changelog

## Unreleased

### Added

- **Uploads.** Select files or directories in the local pane and press F6 to
  queue them into the remote pane's current directory. Direction is decided
  when an item is queued, from the pane it was selected in, so one queue can
  hold downloads and uploads together; F5 runs both. The queue marks each job
  `↓` or `↑`.
- **Overwrite confirmation for uploads.** Before sending, every upload
  destination is checked in one SSH round trip. If any would replace a file on
  the server: Overwrite / Skip those / Cancel. Skip holds the default focus and
  Escape cancels, so an unread prompt does no damage. Disable with
  `transfer.confirm_overwrite = false`. Downloads are never prompted.
- **Selection in both panes.** Space, Enter, `select` and `deselect` work in
  the local pane as well, independently of the remote pane.
- `mkdir` creates the directory on whichever side the pane represents;
  `verify` compares against the other side in either direction.
- `doctor` reports remote directory writability and free space on both sides.
- The header names what is actually running: `0.5.0` on a released build,
  `0.5.0+1` one commit past the tag, `*` for uncommitted changes. `doctor`, the
  session log and a new `version` command carry the full build string.

### Fixed

- **Two symlinks to the same target crashed the local pane** with a duplicate
  row key. Entries were keyed on their resolved path; they now keep the path
  as listed. This also fixes a symlink queued for upload: rsync names the
  destination after the source basename, and the resolved target's name
  differed from the link's, so the resume policy would have inspected a
  different file from the one written.
- **A destination that could not be inspected read as empty**, both when no
  remote probe was available and when it failed — permitting append-resume
  onto an unknown remote file. It now counts as unknown and is never appended
  to. The remote probe also confirms GNU `find` is present before trusting an
  empty result.

### Changed

- F5's label is "Transfer"; it runs the whole queue regardless of direction.
- Commands typed at the prompt act on the pane last focused, since typing
  moves focus to the prompt. Keyboard actions still follow true focus.
- `queue.json` is version 2: per-job `direction`, and `local_dest` renamed to
  `local_path`. Version 1 files load unchanged, as downloads.
- The transfer layer formats the `host:path` end wherever it sits, so the path
  rules follow the remote side rather than the source position: raw under
  `-s`, quoted in the `< 3.0` degraded mode.
- Product requirements amended: uploads added as §3.10 of
  `reqs/01_product_requirements.md`. Bidirectional *sync* remains a non-goal.

## 0.5.0 — 2026-09-13

### Fixed

- **Append-resume no longer trusts a file it did not write.** rsync's
  `--append` assumes the bytes at the destination are a correct prefix of the
  source and checks only the length, never the contents. A torrent client that
  preallocates a file to its full size made rsync skip it, transfer nothing,
  exit successfully, and leave a corrupt file — reported as a completed
  download with an absurd speedup figure. A leftover *shorter* than the source
  was worse still: the missing tail was appended onto out-of-order data,
  silently corrupting the file with no size mismatch to notice.
  `--append-verify` did not help; a skipped file is never checksummed.

  Append is now permitted only when the destination is empty or holds a partial
  ncrsync itself wrote, recorded per job in `queue.json`. Everything else falls
  back to content comparison, which reclaims what is genuinely present and
  sends only checksums. The log states which strategy was chosen and why.

- **A run that transferred nothing is reported as `skipped`**, not as a
  completed download. rsync exits 0 either way, which is how this stayed
  invisible.

### Added

- `verify [PATTERN]` command: checksum-compare selected remote files against
  the local copies. Reads both ends in full, transfers nothing, writes nothing.
- `[transfer] checksum_existing` (default `true`): force content comparison
  when a file of unknown origin is already at the destination, instead of
  trusting size and mtime.

### Changed

- `queue.json` gains a `dest_preexisting` field. Older queue files load
  normally; the missing field reads as "origin unknown", which declines to
  append.

## 0.4.1 — 2026-09-13

- Versioning scheme aligned with the other projects here: `ncrsync/__init__.py`
  is the single source of truth and `pyproject.toml` derives the version from
  it, replacing the copy that was duplicated in both files. Documented in
  [RELEASING.md](RELEASING.md) and enforced by `tests/test_version.py`.
- Build backend switched from `uv_build` to setuptools, which is what makes the
  dynamic version possible (`uv_build` requires a static one). `uv sync` and
  `uv run` are unaffected.
- Added `license` and `Homepage` metadata.

## 0.4.0 — 2026-07-05

- Waiting indicator: a rotating `/-\|` spinner leads the header directory line
  while admin operations run (remote listing/`cd`/refresh, capability
  detection, `doctor`). Driven by worker state, so overlapping and cancelled
  operations are handled; transfers are excluded (they have the progress bar).

## 0.3.0 — 2026-07-05

- New `deselect PATTERN` command (same glob syntax as `select`): clears
  matching selection marks and removes matching jobs from the queue. Running
  jobs are kept (cancel with F7 first).
- File panes: size is the first column (right-aligned); timestamps show
  minute precision (`YYYY-MM-DD HH:MM`) on both panes.

- Switched packaging and dependency management to
  [uv](https://docs.astral.sh/uv/): `pyproject.toml` (uv_build backend) with a
  committed `uv.lock` replaces `requirements*.txt`; pytest config moved from
  `pytest.ini` into `pyproject.toml`. New `ncrsync` console entry point
  (`uv run ncrsync TARGET`); installable via `uv tool install` / `uvx`.

## 0.2.0 — 2026-07-05

Foundation + reliability release, plus review fixes and a UI consistency pass.

### Fixed (UI/state review)

- **Tests no longer write real user state.** The app takes an injectable state
  directory; the test suite uses temporary directories. Previously every
  `pytest` run left a phantom queued job that triggered a bogus recovery
  dialog on the next launch.
- **Queue recovery is host-scoped.** An unfinished queue saved for host A no
  longer triggers the recovery prompt when launching host B, and exiting no
  longer overwrites that foreign queue with an empty one.
- **Tab actually switches panes.** The binding now has priority over Textual's
  default focus-next, matching the footer label. Shift+Tab still cycles focus
  (remote, local, queue, command line); the log pane is display-only.
- **Keys act on the focused pane.** Space/Backspace/Ctrl+R/F8 derive their
  target from real focus instead of a shadow variable that went stale when
  other widgets had focus.
- **Bracket filenames render verbatim.** RichLog and DataTable parse `[...]`
  as Rich markup; status prefixes like `[done]` and names like `x[TGx].mkv`
  were being swallowed. All untrusted text (filenames, rsync output, paths) is
  now escaped or rendered as plain `Text`.
- **Removing a running job is refused** (the rsync subprocess would keep
  transferring invisibly). Cancel with F7 first; F8 away from the queue now
  explains itself instead of misfiring.

### Added / changed (consistency pass)

- Directories can be queued (F6/`queue`); rsync `-a` transfers them
  recursively. `select PATTERN` matches directories too.
- Enter on a remote file toggles its selection (spec 3.5); Enter on a
  directory still descends.
- `cd`/`lcd`/`mkdir` without an argument print usage instead of
  "unknown command".
- `ll` shows a long listing (permissions, size, mtime) of the focused pane;
  previously it was an alias for `ls`.
- Status bar shows `rsync tier | transfer progress`; stale progress clears
  when nothing is running, and the tier appears only after detection.
- `ui.theme` from config is applied; a built-in `nc-blue` Norton Commander
  palette ships with the app.
- The `:` command line has arrow-up/down history.
- `transfer.protect_args = false` is honored: drops `-s` and quotes the remote
  path portion, as an escape hatch on modern rsync.

### Foundation + reliability (2026-06-20)

Split the single-file prototype into the
`ncrsync/` package (`reqs/03_architecture.md` layout); TOML config with
per-host overrides; session/queue persistence with startup recovery; file
logging with full rsync argv; rsync capability auto-detection
(`effective = min(local, remote)`) selecting resume/path-safety/progress
flags; transfer cancellation (SIGINT, partial kept) and automatic retry with
backoff on transient rsync exit codes (10/12/30/35).

## 0.1.0 — 2026-06-20

Single-file Textual prototype (`ncrsync_textual.py`): dual-pane browsing over
SSH, selection, queue, rsync download with `--partial`, doctor checks, and the
bracket-path correctness rules (shell-quote remote commands; never quote the
rsync `host:path` source).
