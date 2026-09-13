"""Unit 1: the upload engine, below the UI.

Covers direction on the job, argv construction in both directions, queue.json
v1 compatibility, the batched remote destination probe, and the resume policy
applied to an upload destination.
"""
import pytest

from ncrsync.model.connection_profile import SshTarget
from ncrsync.model.transfer_job import Direction, JobStatus, TransferJob
from ncrsync.state.queue_store import QueueStore
from ncrsync.transfer.resume_policy import DestInfo
from ncrsync.transfer.rsync_caps import compute_caps
from ncrsync.transfer.rsync_runner import build_rsync_argv
from ncrsync.transfer.transfer_manager import TransferManager, TransferSettings

from .test_transfer_manager import FakeRunner

MODERN = compute_caps((3, 4, 4), (3, 4, 4))
LEGACY = compute_caps((3, 4, 4), (2, 6, 9))
TARGET = SshTarget.parse("myserver")
BRACKET = "/downloads/Movie (2019) [1080p] [YTS.MX]/film.mp4"


# -- job endpoints -----------------------------------------------------------

def test_download_endpoints():
    j = TransferJob("/r/a.mkv", "/local", "a.mkv")
    assert j.remote_is_source
    assert j.source_path == "/r/a.mkv"
    assert j.dest_dir == "/local"
    assert j.dest_path == "/local/a.mkv"


def test_upload_endpoints():
    j = TransferJob("/remote/dir", "/home/me/a.mkv", "a.mkv", direction=Direction.UPLOAD)
    assert not j.remote_is_source
    assert j.source_path == "/home/me/a.mkv"
    assert j.dest_dir == "/remote/dir"
    assert j.dest_path == "/remote/dir/a.mkv"     # POSIX join, not local os.sep


def test_directory_job_flag():
    assert TransferJob("/r", "/l", "Season.03/").is_directory
    assert not TransferJob("/r", "/l", "a.mkv").is_directory


# -- argv in both directions -------------------------------------------------

def test_download_argv_unchanged():
    argv = build_rsync_argv(TARGET, BRACKET, "/dest", MODERN)
    assert argv[-2] == f"myserver:{BRACKET}"      # raw remote source
    assert argv[-1] == "/dest/"


def test_upload_argv_swaps_endpoints():
    argv = build_rsync_argv(
        TARGET, "/downloads/incoming", "/home/me/big.mkv", MODERN,
        direction=Direction.UPLOAD,
    )
    assert argv[-2] == "/home/me/big.mkv"                    # local source
    assert argv[-1] == "myserver:/downloads/incoming/"       # remote dest, trailing /


def test_upload_remote_destination_is_not_shell_quoted_under_protect_args():
    """The no-quoting rule follows the remote end, not the source position."""
    argv = build_rsync_argv(
        TARGET, "/downloads/Movie (2019) [1080p]", "/home/me/f.mp4", MODERN,
        direction=Direction.UPLOAD,
    )
    dest = argv[-1]
    assert dest == "myserver:/downloads/Movie (2019) [1080p]/"
    assert "'" not in dest and "\\" not in dest
    assert "-s" in argv


def test_upload_remote_destination_quoted_in_legacy_mode():
    """Without -s the remote shell splits the path, so quote it - in the
    destination position now, not the source."""
    argv = build_rsync_argv(
        TARGET, "/downloads/has space", "/home/me/f.mp4", LEGACY,
        direction=Direction.UPLOAD,
    )
    assert "-s" not in argv
    assert argv[-1] == "myserver:'/downloads/has space/'"


# -- persistence -------------------------------------------------------------

def test_upload_job_round_trip(tmp_path):
    store = QueueStore(base=tmp_path)
    jobs = [
        TransferJob("/r/a.mkv", "/l", "a.mkv"),
        TransferJob("/r/inbox", "/l/b.mkv", "b.mkv", direction=Direction.UPLOAD),
    ]
    store.save("myserver", "/r", "/l", jobs)
    loaded = store.load()["jobs"]
    assert [j.direction for j in loaded] == [Direction.DOWNLOAD, Direction.UPLOAD]
    assert loaded[1].source_path == "/l/b.mkv"


def test_queue_json_v1_still_loads():
    """Files written before direction existed used local_dest and were all
    downloads."""
    j = TransferJob.from_dict({
        "remote_path": "/r/a.mkv", "local_dest": "/local", "name": "a.mkv",
        "status": "queued", "attempts": 1,
    })
    assert j.direction is Direction.DOWNLOAD
    assert j.local_path == "/local"
    assert j.dest_preexisting is None      # unknown origin -> will not append


def test_unknown_direction_value_falls_back_to_download():
    j = TransferJob.from_dict({
        "remote_path": "/r/a", "local_path": "/l", "name": "a", "direction": "sideways",
    })
    assert j.direction is Direction.DOWNLOAD


# -- queue behaviour ---------------------------------------------------------

def make_manager(codes, xfr=1, remote_stat=None, **kw):
    mgr = TransferManager(TARGET, MODERN, TransferSettings(retry_delay_seconds=0, **kw),
                          remote_stat=remote_stat)
    mgr._runner = FakeRunner(codes, xfr=xfr)
    return mgr


@pytest.mark.asyncio
async def test_dedupe_is_per_direction():
    """Uploading and downloading the same path are different jobs."""
    mgr = make_manager([0, 0])
    assert mgr.add("/r/a.mkv", "a.mkv", "/l") is True
    assert mgr.add("/r/a.mkv", "a.mkv", "/l") is False               # same again
    assert mgr.add("/r/a.mkv", "a.mkv", "/l", Direction.UPLOAD) is True
    assert len(mgr.jobs) == 2


@pytest.mark.asyncio
async def test_upload_destination_probed_in_one_batch():
    calls = []

    async def fake_stat(paths):
        calls.append(paths)
        return {p: DestInfo(exists=False) for p in paths}

    mgr = make_manager([0, 0, 0], remote_stat=fake_stat)
    for n in ("a.mkv", "b.mkv", "c.mkv"):
        mgr.add("/remote/inbox", n, f"/local/{n}", Direction.UPLOAD)
    await mgr.run_queue()
    assert len(calls) == 1                       # one round trip for the queue
    assert calls[0] == ["/remote/inbox/a.mkv", "/remote/inbox/b.mkv",
                        "/remote/inbox/c.mkv"]


@pytest.mark.asyncio
async def test_existing_remote_file_suppresses_append_on_upload():
    async def fake_stat(paths):
        return {p: DestInfo(exists=True, size=1000, allocated=1024) for p in paths}

    mgr = make_manager([0], remote_stat=fake_stat)
    mgr.add("/remote/inbox", "a.mkv", "/local/a.mkv", Direction.UPLOAD)
    await mgr.run_queue()
    argv = mgr._runner.last_argv
    assert "--append" not in argv and "--append-verify" not in argv
    assert "--checksum" in argv
    assert mgr.jobs[0].dest_preexisting is True


@pytest.mark.asyncio
async def test_absent_remote_file_allows_append_on_upload():
    async def fake_stat(paths):
        return {p: DestInfo(exists=False) for p in paths}

    mgr = make_manager([0], remote_stat=fake_stat)
    mgr.add("/remote/inbox", "a.mkv", "/local/a.mkv", Direction.UPLOAD)
    await mgr.run_queue()
    assert "--append" in mgr._runner.last_argv
    assert mgr.jobs[0].dest_preexisting is False


@pytest.mark.asyncio
async def test_upload_without_probe_never_appends():
    """No remote_stat wired, or a probe that failed: the destination is
    unknown, so the fast path must be declined."""
    mgr = make_manager([0], remote_stat=None)
    mgr.add("/remote/inbox", "a.mkv", "/local/a.mkv", Direction.UPLOAD)
    await mgr.run_queue()
    assert "--append" not in mgr._runner.last_argv


@pytest.mark.asyncio
async def test_probe_failure_does_not_abort_the_queue():
    async def broken_stat(paths):
        raise RuntimeError("ssh died")

    mgr = make_manager([0], remote_stat=broken_stat)
    mgr.add("/remote/inbox", "a.mkv", "/local/a.mkv", Direction.UPLOAD)
    await mgr.run_queue()
    assert mgr.jobs[0].status == JobStatus.COMPLETED
    assert "--append" not in mgr._runner.last_argv


@pytest.mark.asyncio
async def test_sparse_remote_destination_suppresses_append():
    async def fake_stat(paths):
        return {p: DestInfo(exists=True, size=1_700_000_000, allocated=500_000_000)
                for p in paths}

    mgr = make_manager([0], remote_stat=fake_stat)
    mgr.add("/remote/inbox", "a.mkv", "/local/a.mkv", Direction.UPLOAD)
    await mgr.run_queue()
    assert "--append" not in mgr._runner.last_argv


# -- the remote destination probe --------------------------------------------


class FakeSsh:
    """Stands in for run_ssh: returns a canned (rc, stdout, stderr)."""

    def __init__(self, rc, out):
        self.rc, self.out, self.cmd = rc, out, None

    async def __call__(self, target, command):
        self.cmd = command
        return self.rc, self.out, ""


@pytest.mark.asyncio
async def test_stat_many_parses_find_output(monkeypatch):
    from ncrsync.remote import remote_browser as rb

    out = ("/inbox/a.mkv\t1048576\t2048\n"      # 1MB logical, 1MB allocated
           "/inbox/sparse.mkv\t1048576\t16\n")  # 1MB logical, 8KB allocated
    fake = FakeSsh(0, out)
    monkeypatch.setattr(rb, "run_ssh", fake)
    browser = rb.RemoteBrowser(TARGET, cwd="/inbox")
    got = await browser.stat_many(["/inbox/a.mkv", "/inbox/sparse.mkv", "/inbox/gone.mkv"])

    assert got["/inbox/a.mkv"] == DestInfo(exists=True, size=1048576, allocated=1048576)
    assert got["/inbox/sparse.mkv"].sparse
    # find ran, so a path it did not print really is absent
    assert got["/inbox/gone.mkv"].exists is False
    assert got["/inbox/gone.mkv"].known is True
    assert "-maxdepth 0" in fake.cmd


@pytest.mark.asyncio
async def test_stat_many_quotes_paths(monkeypatch):
    from ncrsync.remote import remote_browser as rb

    fake = FakeSsh(0, "")
    monkeypatch.setattr(rb, "run_ssh", fake)
    await rb.RemoteBrowser(TARGET).stat_many(["/downloads/Movie (2019) [1080p]/f.mp4"])
    assert "'/downloads/Movie (2019) [1080p]/f.mp4'" in fake.cmd


@pytest.mark.asyncio
async def test_stat_many_without_gnu_find_reports_unknown(monkeypatch):
    """rc 127 means the probe could not run; nothing may be assumed absent."""
    from ncrsync.remote import remote_browser as rb

    monkeypatch.setattr(rb, "run_ssh", FakeSsh(127, ""))
    got = await rb.RemoteBrowser(TARGET).stat_many(["/inbox/a.mkv"])
    assert got["/inbox/a.mkv"].known is False


@pytest.mark.asyncio
async def test_stat_many_ssh_failure_reports_unknown(monkeypatch):
    from ncrsync.remote import remote_browser as rb

    async def boom(target, command):
        raise rb.SshError("connection refused")

    monkeypatch.setattr(rb, "run_ssh", boom)
    got = await rb.RemoteBrowser(TARGET).stat_many(["/inbox/a.mkv"])
    assert got["/inbox/a.mkv"].known is False


def test_uninspectable_destination_never_appends():
    """The policy's own guard, independent of who produced the DestInfo."""
    from ncrsync.transfer.resume_policy import decide

    d = decide(DestInfo(exists=False, known=False), dest_preexisting=False)
    assert not d.use_append
    assert "could not inspect" in d.reason
