"""Headless Textual pilot smoke test: mount + select -> queue -> tab."""
import pytest

from ncrsync.app import NCRsync
from ncrsync.config.config_loader import load_config
from ncrsync.model.file_entry import FileEntry
from ncrsync.ui.panes import FilePane, QueuePane


@pytest.mark.asyncio
async def test_mount_and_queue_flow(tmp_path):
    # use a config with a local dir that exists and no remote dependency
    cfg = load_config("myserver")
    cfg._host_cfg = {"default_remote_dir": "/downloads", "default_local_dir": str(tmp_path)}

    app = NCRsync("myserver", config=cfg)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        # all widgets present
        assert app.query_one("#remote", FilePane)
        assert app.query_one("#local", FilePane)
        assert app.query_one("#queue", QueuePane)

        # inject fake remote entries (no SSH needed) and queue via select
        remote = app.query_one("#remote", FilePane)
        remote.populate(
            [FileEntry("a.mkv", "/downloads/a.mkv", "file", 10)], set()
        )
        app.remote_entries = remote.entries
        app._cmd_select("*.mkv")
        await pilot.pause()
        assert app.remote_selected == {"/downloads/a.mkv"}

        app.action_queue()
        await pilot.pause()
        assert len(app.manager.jobs) == 1
        assert app.manager.jobs[0].name == "a.mkv"

        # tab switches active pane
        app.action_switch_pane()
        await pilot.pause()
        assert app.active_pane == "local"
