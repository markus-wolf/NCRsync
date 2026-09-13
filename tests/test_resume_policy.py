"""Resume-policy decisions, and an end-to-end reproduction of the bug they fix.

The bug: rsync's --append compares only file lengths. A torrent client that
preallocates a file to its full size makes rsync skip it, report success, and
leave a corrupt file behind.
"""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from ncrsync.model.connection_profile import SshTarget
from ncrsync.transfer.resume_policy import DestInfo, ResumeDecision, decide, inspect
from ncrsync.transfer.rsync_caps import compute_caps
from ncrsync.transfer.rsync_runner import build_rsync_argv, parse_xfr_count

MODERN = compute_caps((3, 4, 4), (3, 4, 4))


# -- the decision table ------------------------------------------------------

def test_absent_destination_may_append():
    d = decide(DestInfo(exists=False), dest_preexisting=False)
    assert d.use_append and not d.checksum


def test_our_own_partial_may_append():
    d = decide(DestInfo(exists=True, size=500, allocated=512), dest_preexisting=False)
    assert d.use_append


def test_foreign_file_never_appends():
    d = decide(DestInfo(exists=True, size=1000, allocated=1024), dest_preexisting=True)
    assert not d.use_append
    assert d.checksum          # don't trust size+mtime on a stranger's file
    assert "not written by ncrsync" in d.reason


def test_unknown_origin_never_appends():
    """Older queue.json has no provenance recorded; must not assume."""
    d = decide(DestInfo(exists=True, size=1000, allocated=1024), dest_preexisting=None)
    assert not d.use_append and d.checksum


def test_sparse_file_never_appends():
    """A file with holes was not produced by a completed rsync transfer."""
    sparse = DestInfo(exists=True, size=1_700_000_000, allocated=500_000_000)
    assert sparse.sparse
    d = decide(sparse, dest_preexisting=False)   # even if we think it is ours
    assert not d.use_append
    assert "holes" in d.reason


def test_directory_job_never_appends():
    d = decide(DestInfo(exists=True, size=0), dest_preexisting=False, is_directory=True)
    assert not d.use_append


def test_checksum_can_be_disabled_by_config():
    d = decide(DestInfo(exists=True, size=10, allocated=4096),
               dest_preexisting=True, checksum_existing=False)
    assert not d.use_append and not d.checksum


def test_inspect_missing_path(tmp_path):
    assert inspect(tmp_path / "nope").exists is False


def test_inspect_real_file(tmp_path):
    f = tmp_path / "f.bin"
    f.write_bytes(b"x" * 4096)
    info = inspect(f)
    assert info.exists and info.size == 4096 and not info.sparse


# -- argv wiring -------------------------------------------------------------

def test_policy_denial_removes_append_from_argv():
    t = SshTarget.parse("myserver")
    argv = build_rsync_argv(t, "/r/v.mkv", "/dest", MODERN, append_verify_pref=False)
    assert "--append" not in argv and "--append-verify" not in argv


def test_extra_args_appended_before_paths():
    t = SshTarget.parse("myserver")
    argv = build_rsync_argv(t, "/r/v.mkv", "/dest", MODERN, extra_args=["--checksum"])
    assert "--checksum" in argv
    assert argv.index("--checksum") < argv.index("myserver:/r/v.mkv")


def test_parse_xfr_count():
    assert parse_xfr_count("   0   0%    0.00kB/s    0:00:00 (xfr#0, to-chk=0/1)") == 0
    assert parse_xfr_count("  20.97M 100%  624MB/s  0:00:00 (xfr#1, to-chk=0/1)") == 1
    assert parse_xfr_count("sending incremental file list") is None


# -- end to end, against real rsync -----------------------------------------

pytestmark_rsync = pytest.mark.skipif(
    shutil.which("rsync") is None, reason="rsync not installed"
)


def _make_case(tmp_path: Path) -> tuple[Path, Path]:
    """Remote file, and a local 'torrent leftover': correct prefix, right size,
    rest empty - exactly the situation that fooled --append."""
    src_dir, dst_dir = tmp_path / "src", tmp_path / "dst"
    src_dir.mkdir(), dst_dir.mkdir()
    src = src_dir / "video.mkv"
    src.write_bytes(os.urandom(4 * 1024 * 1024))
    leftover = dst_dir / "video.mkv"
    data = bytearray(src.read_bytes())
    data[1024 * 1024:] = bytes(len(data) - 1024 * 1024)   # only first 1MB real
    leftover.write_bytes(bytes(data))
    os.utime(src, (0, 0))            # differing mtimes; size is identical
    return src, dst_dir


@pytestmark_rsync
def test_append_skips_and_corrupts_reproducing_the_bug(tmp_path):
    """Baseline: with --append rsync reports success and leaves it broken."""
    src, dst_dir = _make_case(tmp_path)
    r = subprocess.run(
        ["rsync", "-a", "--partial", "--append", "--info=progress2",
         str(src), str(dst_dir) + "/"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0                       # rsync claims success
    assert "xfr#0" in r.stdout                     # having sent nothing
    assert (dst_dir / "video.mkv").read_bytes() != src.read_bytes()   # still corrupt


@pytestmark_rsync
def test_policy_choice_repairs_the_file(tmp_path):
    """The flags our policy selects for a foreign file actually fix it."""
    src, dst_dir = _make_case(tmp_path)
    info = inspect(dst_dir / "video.mkv")
    decision = decide(info, dest_preexisting=True)
    assert not decision.use_append
    argv = ["rsync", "-a", "--partial", "--info=progress2"]
    if decision.checksum:
        argv.append("--checksum")
    argv += [str(src), str(dst_dir) + "/"]
    r = subprocess.run(argv, capture_output=True, text=True)
    assert r.returncode == 0
    assert (dst_dir / "video.mkv").read_bytes() == src.read_bytes()   # repaired
