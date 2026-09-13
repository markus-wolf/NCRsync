"""Resolve what is actually running, which is not always what was released.

``__version__`` names the last release. Run from a git checkout that has moved
past its tag - the usual state during development - it understates things: the
code in front of you is not 0.5.0, it is 0.5.0 plus whatever landed since.

So the label combines both: the release, plus a suffix describing the distance
from it when there is one. An installed copy (``uv tool install``, ``uvx``) has
no repository to ask and needs no suffix, because a wheel really is the release.

Resolution costs one ``git describe`` (about 12 ms) and must happen once at
startup, never per render - the header is repainted ten times a second while
the busy spinner runs.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

from . import __version__

#: Give up rather than let a wedged git delay startup.
GIT_TIMEOUT_SECONDS = 2.0

# v0.5.0-1-g68773e7[-dirty]
_DESCRIBE_RE = re.compile(
    r"^v?(?P<tag>.+?)-(?P<distance>\d+)-g(?P<commit>[0-9a-f]+)(?P<dirty>-dirty)?$"
)
# a bare hash, from --always when no tag is reachable
_BARE_RE = re.compile(r"^(?P<commit>[0-9a-f]{7,40})(?P<dirty>-dirty)?$")


@dataclass(frozen=True)
class VersionInfo:
    """What is running. ``release`` always set; the rest only from a checkout."""

    release: str
    commit: Optional[str] = None
    distance: Optional[int] = None
    dirty: bool = False
    describe: Optional[str] = None

    @property
    def is_release(self) -> bool:
        """True when what runs is exactly the released code: an installed
        wheel, or a clean checkout sitting on the tag."""
        return not self.dirty and not self.distance and self.commit is None

    def short(self) -> str:
        """Compact label for the header: '0.5.0', '0.5.0+1', '0.5.0+1*'."""
        label = self.release
        if self.distance:
            label += f"+{self.distance}"
        elif self.commit and self.distance is None:
            label += f" ({self.commit})"      # no tag reachable; name the commit
        if self.dirty:
            label += "*"
        return label

    def long(self) -> str:
        """Full detail for doctor and the session log."""
        if self.describe:
            extra = f"{self.describe}{' (modified)' if self.dirty else ''}"
            return f"{self.release} [{extra}]"
        return self.release


def _run_git(args: list[str], cwd: Path) -> Optional[str]:
    try:
        p = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return None       # no git, or it misbehaved: fall back to the release
    if p.returncode != 0:
        return None
    out = p.stdout.strip()
    return out or None


def parse_describe(text: str, release: str) -> VersionInfo:
    """Turn `git describe` output into a VersionInfo."""
    m = _DESCRIBE_RE.match(text)
    if m:
        return VersionInfo(
            release=release,
            commit=m.group("commit"),
            distance=int(m.group("distance")),
            dirty=bool(m.group("dirty")),
            describe=text,
        )
    m = _BARE_RE.match(text)
    if m:
        # shallow clone or no tags: distance is unknowable, name the commit
        return VersionInfo(
            release=release,
            commit=m.group("commit"),
            dirty=bool(m.group("dirty")),
            describe=text,
        )
    # exactly on a tag: describe prints just the tag
    clean = text[1:] if text.startswith("v") else text
    return VersionInfo(release=release, distance=0, describe=text,
                       dirty=clean.endswith("-dirty"))


@lru_cache(maxsize=None)
def resolve(root: Optional[Path] = None) -> VersionInfo:
    """Resolve once, at startup. Never call this per render.

    Cached: the answer cannot change while the process runs, and the header is
    repainted ten times a second by the busy spinner.
    """
    base = VersionInfo(release=__version__)
    cwd = root or Path(__file__).resolve().parent.parent
    if not (cwd / ".git").exists():
        return base                      # installed copy: the wheel is the release
    text = _run_git(["describe", "--tags", "--dirty", "--always"], cwd)
    if not text:
        return base
    return parse_describe(text, __version__)
