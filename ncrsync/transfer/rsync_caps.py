"""rsync capability detection and flag selection.

The effective version is min(local, remote) because protocol features (notably
``-s``/``--protect-args``) require both ends. Flags are chosen per the matrix in
the plan:

  >= 3.2.0       : -s, --append (--append-verify deprecated), --info=progress2
  3.0.0 - 3.1.x  : -s, --append-verify, (3.1 progress2 / 3.0 --progress)
  < 3.0.0        : NO -s (legacy path quoting), --partial only, --progress
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

Version = tuple[int, int, int]

_VER_RE = re.compile(r"rsync\s+version\s+(\d+)\.(\d+)(?:\.(\d+))?")


def parse_rsync_version(version_output: str) -> Optional[Version]:
    """Extract (major, minor, patch) from `rsync --version` first line."""
    m = _VER_RE.search(version_output)
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)), int(m.group(3) or 0))


@dataclass
class RsyncCaps:
    effective: Version
    protect_args: bool      # -s supported (>= 3.0)
    append_verify: bool     # --append-verify exists & not deprecated (3.0 - 3.1)
    append: bool            # --append exists (>= 3.0)
    progress2: bool         # --info=progress2 (>= 3.1)
    degraded: bool          # effective < 3.0

    @property
    def tier(self) -> str:
        if self.effective >= (3, 2, 0):
            return ">=3.2"
        if self.effective >= (3, 1, 0):
            return "3.1"
        if self.effective >= (3, 0, 0):
            return "3.0"
        return "<3.0 (degraded)"


def compute_caps(local: Optional[Version], remote: Optional[Version]) -> RsyncCaps:
    """Compute capabilities from local and remote versions.

    A missing remote version (could not detect) is treated optimistically as
    equal to local, so detection failure does not needlessly degrade a modern
    setup; doctor surfaces the unknown separately.
    """
    if local is None:
        local = (0, 0, 0)
    eff = local if remote is None else min(local, remote)
    return RsyncCaps(
        effective=eff,
        protect_args=eff >= (3, 0, 0),
        append_verify=(3, 0, 0) <= eff < (3, 2, 0),
        append=eff >= (3, 0, 0),
        progress2=eff >= (3, 1, 0),
        degraded=eff < (3, 0, 0),
    )


def select_flags(caps: RsyncCaps, *, append_verify_pref: bool = True,
                 partial: bool = True, protect_args_pref: bool = True) -> list[str]:
    """Resume/path/progress flags for this capability set (order-stable)."""
    flags: list[str] = []
    if caps.protect_args and protect_args_pref:
        flags.append("-s")
    if partial:
        flags.append("--partial")
    # resume strategy
    if caps.append_verify and append_verify_pref:
        flags.append("--append-verify")
    elif caps.append and append_verify_pref:
        flags.append("--append")   # 3.2+: append-verify deprecated -> append
    # < 3.0 or append_verify disabled: --partial alone handles resume
    # progress
    flags.append("--info=progress2" if caps.progress2 else "--progress")
    return flags
