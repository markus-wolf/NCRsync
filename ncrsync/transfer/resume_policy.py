"""Decide whether rsync's append-resume is safe for a given transfer.

``--append`` assumes the bytes already at the destination are a correct prefix
of the source. It verifies that assumption by comparing lengths only, never
contents, and skips outright when the destination is already as long as the
source. Handed a file it did not write - a preallocated torrent leftover, a
half-finished browser download - it either skips a broken file while reporting
success, or appends onto out-of-order data and silently corrupts it.

So append is permitted only when the destination is empty, or holds a partial
that ncrsync itself wrote. Everything else falls back to rsync's content
comparison, which reclaims whatever is genuinely present and costs only
checksums on the wire.

Nothing here is specific to the download direction; an upload can use the same
decision once it can stat its destination.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Below this fraction of allocated-to-logical bytes the file has holes in it,
# which no completed rsync transfer produces.
SPARSE_RATIO = 0.95


@dataclass(frozen=True)
class DestInfo:
    """What the filesystem says about the destination."""

    exists: bool
    size: int = 0
    allocated: int = 0

    @property
    def sparse(self) -> bool:
        return self.exists and self.size > 0 and self.allocated < self.size * SPARSE_RATIO


def inspect(path: Path) -> DestInfo:
    """Stat the destination. A missing or unreadable path reports as absent."""
    try:
        st = os.stat(path)
    except OSError:
        return DestInfo(exists=False)
    return DestInfo(exists=True, size=st.st_size, allocated=st.st_blocks * 512)


@dataclass(frozen=True)
class ResumeDecision:
    use_append: bool
    #: whether to force a content comparison rather than trusting size+mtime
    checksum: bool
    #: human-readable justification, logged so the choice is never a surprise
    reason: str


def decide(
    dest: DestInfo,
    *,
    dest_preexisting: Optional[bool],
    is_directory: bool = False,
    checksum_existing: bool = True,
) -> ResumeDecision:
    """Choose a resume strategy.

    ``dest_preexisting`` records whether something was already at the
    destination when ncrsync first ran this job: ``False`` means the file there
    now is ours, ``True`` means it came from elsewhere, ``None`` means we never
    looked (an older queue.json, say) and must not assume.
    """
    if is_directory:
        # a directory job covers many files; provenance cannot be reasoned
        # about per-file here, so let rsync compare contents
        return ResumeDecision(False, False, "directory transfer - comparing contents")
    if not dest.exists:
        return ResumeDecision(True, False, "no file at destination")
    if dest_preexisting:
        return ResumeDecision(
            False, checksum_existing,
            "file at destination was not written by ncrsync - comparing contents",
        )
    if dest.sparse:
        return ResumeDecision(
            False, checksum_existing,
            "file at destination has holes in it - comparing contents",
        )
    if dest_preexisting is None:
        return ResumeDecision(
            False, checksum_existing,
            "origin of file at destination is unknown - comparing contents",
        )
    return ResumeDecision(True, False, "resuming our own partial file")
