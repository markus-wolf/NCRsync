"""Headless Textual pilot tests: mount, queue flow, focus/tab model, recovery scoping."""
import pytest

from ncrsync.app import NCRsync
from ncrsync.config.config_loader import load_config
from ncrsync.model.file_entry import FileEntry
from ncrsync.model.transfer_job import JobStatus, TransferJob
from ncrsync.screens import RecoveryScreen
from ncrsync.state.queue_store import QueueStore
from ncrsync.ui.panes import FilePane, QueuePane


def make_app(tmp_path, host="myserver"):
    cfg = load_config(host)
    cfg._host_cfg = {"default_remote_dir": "/downloads", "default_local_dir": str(tmp_path)}
    return NCRsync(host, config=cfg, state_dir=tmp_path / "state")


@pytest.mark.asyncio
async def test_mount_and_queue_flow(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        # all widgets present
        assert app.query_one("#remote", FilePane)
        assert app.query_one("#local", FilePane)
        assert app.query_one("#queue", QueuePane)

        # inject fake remote entries (no SSH needed) and queue via select
        remote = app.query_one("#remote", FilePane)
        remote.populate([FileEntry("a.mkv", "/downloads/a.mkv", "file", 10)], set())
        app._cmd_select("*.mkv")
        await pilot.pause()
        assert app.remote_selected == {"/downloads/a.mkv"}

        app.action_queue()
        await pilot.pause()
        assert len(app.manager.jobs) == 1
        assert app.manager.jobs[0].name == "a.mkv"

    # state landed in the injected dir, not the user's real state dir
    assert (tmp_path / "state" / "queue.json").exists()


@pytest.mark.asyncio
async def test_tab_switches_panes_directly(tmp_path):
    # tab is a priority binding: remote <-> local, never into queue/log/input
    app = make_app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert app.focused.id == "remote"
        await pilot.press("tab")
        assert app.focused.id == "local"
        await pilot.press("tab")
        assert app.focused.id == "remote"


@pytest.mark.asyncio
async def test_bindings_follow_real_focus(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        # log is display-only: not focusable
        assert app.query_one("#log").can_focus is False
        # backspace with queue focused must not navigate any pane
        app.query_one("#queue", QueuePane).focus()
        await pilot.pause()
        remote_before, local_before = app.remote.cwd, app.local.cwd
        await pilot.press("backspace")
        assert app.remote.cwd == remote_before
        assert app.local.cwd == local_before


@pytest.mark.asyncio
async def test_foreign_queue_not_recovered_or_clobbered(tmp_path):
    state = tmp_path / "state"
    QueueStore(base=state).save(
        "otherhost", "/r", "/l", [TransferJob("/r/x.mkv", "/l", "x.mkv")]
    )
    app = make_app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        # no recovery modal for another host's queue
        assert not isinstance(app.screen, RecoveryScreen)
    # and exiting did not overwrite it
    data = QueueStore(base=state).load()
    assert data["host"] == "otherhost"
    assert data["jobs"][0].name == "x.mkv"


@pytest.mark.asyncio
async def test_own_queue_triggers_recovery(tmp_path):
    state = tmp_path / "state"
    QueueStore(base=state).save(
        "myserver", "/r", "/l", [TransferJob("/r/x.mkv", "/l", "x.mkv", JobStatus.QUEUED)]
    )
    app = make_app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, RecoveryScreen)
