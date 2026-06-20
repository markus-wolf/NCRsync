"""Opportunistic progress parsing (doc-04 §9).

Raw rsync output is authoritative and always logged elsewhere. This extracts a
single status line's worth of info when possible. Handles both
``--info=progress2`` (whole-transfer) and per-file ``--progress`` formats.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

# e.g. "  1,234,567  45%  2.34MB/s    0:01:23"
_PROGRESS_RE = re.compile(
    r"(?P<bytes>[\d,]+)\s+(?P<pct>\d+)%\s+(?P<rate>[\d.]+\s*\wB/s)\s+(?P<eta>[\d:]+)"
)


@dataclass
class Progress:
    bytes: Optional[int] = None
    percent: Optional[int] = None
    rate: Optional[str] = None
    eta: Optional[str] = None

    def as_status(self) -> str:
        parts = []
        if self.percent is not None:
            parts.append(f"{self.percent}%")
        if self.rate:
            parts.append(self.rate.replace(" ", ""))
        if self.eta:
            parts.append(f"ETA {self.eta}")
        return "  ".join(parts)


def parse_progress_line(line: str) -> Optional[Progress]:
    m = _PROGRESS_RE.search(line)
    if not m:
        return None
    try:
        nbytes = int(m.group("bytes").replace(",", ""))
    except ValueError:
        nbytes = None
    return Progress(
        bytes=nbytes,
        percent=int(m.group("pct")),
        rate=m.group("rate").strip(),
        eta=m.group("eta"),
    )
