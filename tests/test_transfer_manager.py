"""TransferManager retry / stop-on-error behavior with a fake runner."""
import pytest

from ncrsync.model.connection_profile import SshTarget
from ncrsync.model.transfer_job import JobStatus
from ncrsync.transfer.rsync_caps import compute_caps
from ncrsync.transfer.transfer_manager import TransferManager, TransferSettings

CAPS = compute_caps((3, 4, 4), (3, 4, 4))


class FakeRunner:
    """Returns queued exit codes in order; records argv and calls.

    ``xfr`` is the files-transferred count to report in the progress line, so
    tests can exercise the "rsync skipped it" path (xfr#0).
    """

    def __init__(self, codes, xfr=1):
        self._codes = list(codes)
        self.cancelled = False
        self.calls = 0
        self.argvs = []
        self._xfr = xfr

    async def run(self, argv, on_line):
        self.calls += 1
        self.argvs.append(argv)
        on_line(f"fake rsync call {self.calls}")
        on_line(f"   1.00M 100%  1.0MB/s  0:00:01 (xfr#{self._xfr}, to-chk=0/1)")
        return self._codes.pop(0)

    async def cancel(self):
        self.cancelled = True

    @property
    def last_argv(self):
        return self.argvs[-1]


def make_manager(codes, xfr=1, **settings_kw):
    target = SshTarget.parse("myserver")
    settings = TransferSettings(retry_delay_seconds=0, **settings_kw)
    mgr = TransferManager(target, CAPS, settings)
    mgr._runner = FakeRunner(codes, xfr=xfr)
    return mgr


@pytest.mark.asyncio
async def test_success_first_try():
    mgr = make_manager([0])
    mgr.add("/r/a.mkv", "a.mkv", "/local")
    await mgr.run_queue()
    assert mgr.jobs[0].status == JobStatus.COMPLETED
    assert mgr._runner.calls == 1


@pytest.mark.asyncio
async def test_transient_failure_is_retried_then_succeeds():
    # 30 = timeout (transient) then success
    mgr = make_manager([30, 0], max_retries=3)
    mgr.add("/r/a.mkv", "a.mkv", "/local")
    await mgr.run_queue()
    assert mgr.jobs[0].status == JobStatus.COMPLETED
    assert mgr._runner.calls == 2  # original + 1 retry
    assert mgr.jobs[0].attempts == 2


@pytest.mark.asyncio
async def test_transient_failure_exhausts_retries():
    mgr = make_manager([30, 30, 30, 30], max_retries=2)  # 1 + 2 retries = 3 attempts
    mgr.add("/r/a.mkv", "a.mkv", "/local")
    await mgr.run_queue()
    assert mgr.jobs[0].status == JobStatus.FAILED
    assert mgr._runner.calls == 3


@pytest.mark.asyncio
async def test_non_transient_failure_not_retried_and_stops_queue():
    # rc=23 is not transient; queue should stop, second job untouched
    mgr = make_manager([23], max_retries=3)
    mgr.add("/r/a.mkv", "a.mkv", "/local")
    mgr.add("/r/b.mkv", "b.mkv", "/local")
    await mgr.run_queue()
    assert mgr.jobs[0].status == JobStatus.FAILED
    assert mgr.jobs[1].status == JobStatus.QUEUED  # never started
    assert mgr._runner.calls == 1


@pytest.mark.asyncio
async def test_continue_on_error_proceeds_to_next_job():
    mgr = make_manager([23, 0], continue_on_error=True, max_retries=0)
    mgr.add("/r/a.mkv", "a.mkv", "/local")
    mgr.add("/r/b.mkv", "b.mkv", "/local")
    await mgr.run_queue()
    assert mgr.jobs[0].status == JobStatus.FAILED
    assert mgr.jobs[1].status == JobStatus.COMPLETED


@pytest.mark.asyncio
async def test_remove_running_job_refused():
    mgr = make_manager([0])
    mgr.add("/r/a.mkv", "a.mkv", "/local")
    mgr.jobs[0].status = JobStatus.RUNNING
    assert mgr.remove_at(0) is None
    assert len(mgr.jobs) == 1  # still there; must cancel first


@pytest.mark.asyncio
async def test_remove_matching_keeps_running_and_matches_dir_names():
    mgr = make_manager([0])
    mgr.add("/r/a.mkv", "a.mkv", "/local")
    mgr.add("/r/b.mkv", "b.mkv", "/local")
    mgr.add("/r/Season.03", "Season.03/", "/local")  # dir job, trailing /
    mgr.jobs[0].status = JobStatus.RUNNING
    removed = mgr.remove_matching("*")
    assert sorted(j.name for j in removed) == ["Season.03/", "b.mkv"]
    assert [j.name for j in mgr.jobs] == ["a.mkv"]  # running survives


@pytest.mark.asyncio
async def test_remove_matching_pattern():
    mgr = make_manager([0])
    mgr.add("/r/a.mkv", "a.mkv", "/local")
    mgr.add("/r/b.srt", "b.srt", "/local")
    removed = mgr.remove_matching("*.srt")
    assert [j.name for j in removed] == ["b.srt"]
    assert [j.name for j in mgr.jobs] == ["a.mkv"]


@pytest.mark.asyncio
async def test_add_dedupes():
    mgr = make_manager([0])
    assert mgr.add("/r/a.mkv", "a.mkv", "/local") is True
    assert mgr.add("/r/a.mkv", "a.mkv", "/local") is False
    assert len(mgr.jobs) == 1


# -- resume policy applied per job -------------------------------------------


@pytest.mark.asyncio
async def test_foreign_destination_file_suppresses_append(tmp_path):
    """A file we did not write must not be appended onto."""
    (tmp_path / "a.mkv").write_bytes(b"torrent leftover")
    mgr = make_manager([0])
    mgr.add("/r/a.mkv", "a.mkv", str(tmp_path))
    await mgr.run_queue()
    argv = mgr._runner.last_argv
    assert "--append" not in argv and "--append-verify" not in argv
    assert "--checksum" in argv
    assert mgr.jobs[0].dest_preexisting is True


@pytest.mark.asyncio
async def test_absent_destination_allows_append(tmp_path):
    mgr = make_manager([0])
    mgr.add("/r/a.mkv", "a.mkv", str(tmp_path))
    await mgr.run_queue()
    argv = mgr._runner.last_argv
    assert "--append" in argv
    assert "--checksum" not in argv
    assert mgr.jobs[0].dest_preexisting is False


@pytest.mark.asyncio
async def test_our_own_partial_still_appends_on_retry(tmp_path):
    """Once we own the destination, a retry may resume it - the fast path
    this feature exists for must survive the fix."""
    mgr = make_manager([30, 0])          # transient failure, then success
    mgr.add("/r/a.mkv", "a.mkv", str(tmp_path))
    # rsync writes a partial between attempts
    job = mgr.jobs[0]
    orig = mgr._resume_decision

    def decide_then_create(j):
        d = orig(j)
        (tmp_path / "a.mkv").write_bytes(b"partial data")
        return d

    mgr._resume_decision = decide_then_create
    await mgr.run_queue()
    assert job.dest_preexisting is False
    assert "--append" in mgr._runner.argvs[-1]     # resumed, not restarted
    assert job.status == JobStatus.COMPLETED


@pytest.mark.asyncio
async def test_unknown_provenance_from_old_queue_file(tmp_path):
    """queue.json written before the field existed leaves it None."""
    (tmp_path / "a.mkv").write_bytes(b"something")
    mgr = make_manager([0])
    mgr.add("/r/a.mkv", "a.mkv", str(tmp_path))
    mgr.jobs[0].attempts = 1            # already run once, provenance unrecorded
    await mgr.run_queue()
    assert mgr.jobs[0].dest_preexisting is None
    assert "--append" not in mgr._runner.last_argv


# -- honest reporting of a skipped file ---------------------------------------


@pytest.mark.asyncio
async def test_zero_transfer_reports_skipped_not_completed(tmp_path):
    """rsync exits 0 whether it sent the file or skipped it; saying 'done'
    for a skip is how the append bug stayed invisible."""
    lines = []
    mgr = make_manager([0], xfr=0)
    mgr._on_line = lines.append
    mgr.add("/r/a.mkv", "a.mkv", str(tmp_path))
    await mgr.run_queue()
    assert mgr.jobs[0].status == JobStatus.SKIPPED
    assert any("already present" in m for m in lines)


@pytest.mark.asyncio
async def test_real_transfer_reports_completed(tmp_path):
    mgr = make_manager([0], xfr=1)
    mgr.add("/r/a.mkv", "a.mkv", str(tmp_path))
    await mgr.run_queue()
    assert mgr.jobs[0].status == JobStatus.COMPLETED


@pytest.mark.asyncio
async def test_skipped_job_is_finished_not_pending(tmp_path):
    mgr = make_manager([0], xfr=0)
    mgr.add("/r/a.mkv", "a.mkv", str(tmp_path))
    await mgr.run_queue()
    assert mgr.pending == []
    assert not mgr.jobs[0].status.is_unfinished()
