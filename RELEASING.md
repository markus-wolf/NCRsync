# Versioning and releases

## Scheme

Semantic versioning, `MAJOR.MINOR.PATCH`, tagged `vMAJOR.MINOR.PATCH`.

While the project is pre-1.0 the major stays at `0` and the minor carries
feature work:

| Bump | When |
|---|---|
| PATCH — `0.4.0` → `0.4.1` | bug fix, doc fix, test-only change; no new behaviour |
| MINOR — `0.4.0` → `0.5.0` | new feature, new command or key binding, changed default, changed config key |
| MAJOR — `0.x` → `1.0.0` | first release considered complete against `reqs/`; after that, any breaking change to config, state files, or CLI |

State-file format changes (`queue.json`, `session.json`) need at least a MINOR
bump and a back-compatible reader, since an older queue may be on disk.

## Single source of truth

The version exists in exactly one place:

```python
# ncrsync/__init__.py
__version__ = "0.4.0"
```

`pyproject.toml` declares `dynamic = ["version"]` and reads that attribute via
setuptools. Do not add a `version =` field back to `[project]` — the build
fails or silently disagrees, and `tests/test_version.py` will catch it.

Note: the `uv_build` backend cannot do this (it requires a static version), so
this project uses the setuptools backend. `uv sync` / `uv run` are unaffected.

## Release checklist

1. Bump `__version__` in `ncrsync/__init__.py`.
2. Move the CHANGELOG's `## Unreleased` heading to `## X.Y.Z — YYYY-MM-DD`.
3. `uv sync` — reinstalls the project so its installed metadata matches.
   `uv.lock` does not record the project's own version once it is dynamic, so
   a bump alone leaves the lock unchanged. That is one fewer place to drift.
4. `uv run pytest` — `tests/test_version.py` verifies the above agree.

   If that test reports a version you know you just changed, delete the stale
   bytecode: `find . -name __pycache__ -not -path './.venv/*' -exec rm -rf {} +`.
   Python's `.pyc` cache keys on source mtime at one-second resolution plus file
   size, and two version strings of equal length edited within the same second
   look unchanged to it.
5. Commit the bump together with the change it releases.
6. Tag, annotated, with a short summary of what the release contains:

   ```bash
   git tag -a v0.5.0 -m "NCRsync v0.5.0

   - short bullet per notable change"
   ```

7. Push both: `git push origin main v0.5.0`

## Verifying a release landed

The tag must point at the tip of `main` on GitHub. Check without cloning:

```bash
git ls-remote --heads --tags origin
```

`refs/heads/main` and the `refs/tags/vX.Y.Z^{}` line (the dereferenced
annotated tag) must show the same commit hash.
