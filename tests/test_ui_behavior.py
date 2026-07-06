"""Pilot tests for the UI-consistency improvements: dir queueing, Enter-on-file,
command usage feedback, command history, theme, busy spinner."""
import asyncio

import pytest

from ncrsync.model.file_entry import FileEntry
from ncrsync.ui.command_input import CommandInput
from ncrsync.ui.panes import FilePane

from .test_app_smoke import make_app


def fake_remote(app, entries):
    pane = app.query_one("#remote", FilePane)
    pane.populate(entries, set())
    return pane


async def settle_startup_workers(app, pilot, timeout_ticks=30):
    """Wait for the on-mount remote/caps workers to finish or fail."""
    for _ in range(timeout_ticks):
        if not app._busy:
            return
        await pilot.pause(0.1)


@pytest.mark.asyncio
async def test_directories_are_queueable(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        fake_remote(app, [
            FileEntry("Season.03", "/downloads/Season.03", "dir"),
            FileEntry("a.mkv", "/downloads/a.mkv", "file", 10),
        ])
        app._cmd_select("*")
        app.action_queue()
        await pilot.pause()
        names = sorted(j.name for j in app.manager.jobs)
        assert names == ["Season.03/", "a.mkv"]  # dir queued with trailing /


@pytest.mark.asyncio
async def test_enter_on_remote_file_toggles_selection(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        fake_remote(app, [FileEntry("a.mkv", "/downloads/a.mkv", "file", 10)])
        app.query_one("#remote", FilePane).focus()
        await pilot.pause()
        await pilot.press("enter")
        assert app.remote_selected == {"/downloads/a.mkv"}
        await pilot.press("enter")
        assert app.remote_selected == set()


@pytest.mark.asyncio
async def test_deselect_clears_marks_and_queued_jobs(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        fake_remote(app, [
            FileEntry("a.mkv", "/downloads/a.mkv", "file", 10),
            FileEntry("b.srt", "/downloads/b.srt", "file", 10),
        ])
        # marks: select all, deselect *.srt -> only a.mkv stays marked
        app._cmd_select("*")
        app._cmd_deselect("*.srt")
        assert app.remote_selected == {"/downloads/a.mkv"}
        # queue both, then deselect *.srt -> only a.mkv stays queued
        app._cmd_select("*")
        app.action_queue()
        await pilot.pause()
        assert len(app.manager.jobs) == 2
        app._cmd_deselect("*.srt")
        await pilot.pause()
        assert [j.name for j in app.manager.jobs] == ["a.mkv"]


@pytest.mark.asyncio
async def test_command_history_up_down(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        inp = app.query_one("#command", CommandInput)
        inp.focus()
        await pilot.pause()
        for cmd in ("ls", "select *.mkv"):
            inp.value = cmd
            await pilot.press("enter")
        assert inp.value == ""
        await pilot.press("up")
        assert inp.value == "select *.mkv"
        await pilot.press("up")
        assert inp.value == "ls"
        await pilot.press("down")
        assert inp.value == "select *.mkv"
        await pilot.press("down")
        assert inp.value == ""  # back to the fresh line


@pytest.mark.asyncio
async def test_spinner_during_remote_listing(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await settle_startup_workers(app, pilot)
        assert not app.sub_title[0] in "/-\\|"  # idle: no spinner

        async def slow_list():
            await asyncio.sleep(0.6)
            return []

        app.remote.list_dir = slow_list
        app.refresh_remote()
        await pilot.pause(0.25)
        # spinner frame leads the directory line while listing
        assert app.sub_title[0] in "/-\\|" and app.sub_title[1] == " "
        await pilot.pause(0.8)
        assert app.sub_title.startswith("myserver |")  # clean again


@pytest.mark.asyncio
async def test_spinner_until_last_busy_worker_finishes(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await settle_startup_workers(app, pilot)
        app.run_worker(asyncio.sleep(0.3), group="caps")
        app.run_worker(asyncio.sleep(0.9), group="doctor")
        await pilot.pause(0.15)
        assert app._busy and app.sub_title[0] in "/-\\|"
        await pilot.pause(0.4)  # caps worker done, doctor still running
        assert app._busy
        await pilot.pause(0.8)  # everything done
        assert not app._busy
        assert app.sub_title.startswith("myserver |")


@pytest.mark.asyncio
async def test_theme_from_config_applied(tmp_path):
    app = make_app(tmp_path)  # default config theme is nc-blue
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert app.theme == "nc-blue"


@pytest.mark.asyncio
async def test_cd_without_arg_gives_usage_not_unknown(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        inp = app.query_one("#command", CommandInput)
        inp.focus()
        await pilot.pause()
        seen: list[str] = []
        app.log_line = lambda m: seen.append(m)  # capture
        inp.value = "cd"
        await pilot.press("enter")
        assert any("usage: cd" in m for m in seen)
        assert not any("unknown command" in m for m in seen)