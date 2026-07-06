# Changelog

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
