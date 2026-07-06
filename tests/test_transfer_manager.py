"""TransferManager retry / stop-on-error behavior with a fake runner."""
import pytest

from ncrsync.model.connection_profile import SshTarget
from ncrsync.model.transfer_job import JobStatus
from ncrsync.transfer.rsync_caps import compute_caps
from ncrsync.transfer.transfer_manager import TransferManager, TransferSettings

CAPS = compute_caps((3, 4, 4), (3, 4, 4))


class FakeRunner:
    """Returns queued exit codes in order; records argv count."""

    def __init__(self, codes):
        self._codes = list(codes)
        self.cancelled = False
        self.calls = 0

    async def run(self, argv, on_line):
        self.calls += 1
        on_line(f"fake rsync call {self.calls}")
        return self._codes.pop(0)

    async def cancel(self):
        self.cancelled = True


def make_manager(codes, **settings_kw):
    target = SshTarget.parse("myserver")
    settings = TransferSettings(retry_delay_seconds=0, **settings_kw)
    mgr = TransferManager(target, CAPS, settings)
    mgr._runner = FakeRunner(codes)
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
