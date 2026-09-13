"""Unit 2: upload reachable from the UI.

Direction follows the pane the items were selected in; selection is per pane;
uploads that would replace server files are confirmed first; mkdir, verify and
doctor act on the relevant side.
"""
import pytest

from ncrsync.diagnostics.doctor import parse_df_available
from ncrsync.model.file_entry import FileEntry
from ncrsync.model.transfer_job import Direction, JobStatus
from ncrsync.screens import OverwriteScreen
from ncrsync.transfer.resume_policy import DestInfo
from ncrsync.ui.command_input import CommandInput
from ncrsync.ui.panes import FilePane, QueuePane

from .test_app_smoke import make_app
from .test_transfer_manager import FakeRunner


def fake_pane(app, pane_id, entries):
    pane = app.query_one(f"#{pane_id}", FilePane)
    pane.populate(entries, set())
    return pane


async def type_command(app, pilot, text):
    inp = app.query_one("#command", CommandInput)
    inp.focus()
    await pilot.pause()
    inp.value = text
    await pilot.press("enter")
    await pilot.pause()


# -- direction follows the pane ----------------------------------------------

@pytest.mark.asyncio
async def test_f6_in_remote_pane_queues_a_download(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        fake_pane(app, "remote", [FileEntry("a.mkv", "/downloads/a.mkv", "file", 10)])
        app.query_one("#remote", FilePane).focus()
        await pilot.pause()
        await pilot.press("f6")
        job = app.manager.jobs[0]
        assert job.direction is Direction.DOWNLOAD
        assert job.source_path == "/downloads/a.mkv"
        assert job.dest_dir == str(app.local.cwd)


@pytest.mark.asyncio
async def test_f6_in_local_pane_queues_an_upload(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        fake_pane(app, "local", [FileEntry("big.mkv", "/Users/me/big.mkv", "file", 10)])
        app.query_one("#local", FilePane).focus()
        await pilot.pause()
        await pilot.press("f6")
        job = app.manager.jobs[0]
        assert job.direction is Direction.UPLOAD
        assert job.source_path == "/Users/me/big.mkv"
        assert job.dest_dir == app.remote.cwd


@pytest.mark.asyncio
async def test_typed_queue_command_uses_the_last_focused_pane(tmp_path):
    """Typing at the prompt moves focus to the input; the command must still
    act on the pane the user was just working in."""
    app = make_app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        fake_pane(app, "local", [FileEntry("big.mkv", "/Users/me/big.mkv", "file", 10)])
        app.query_one("#local", FilePane).focus()
        await pilot.pause()
        await type_command(app, pilot, "queue")
        assert app.manager.jobs[0].direction is Direction.UPLOAD


@pytest.mark.asyncio
async def test_local_directory_queued_for_upload(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        fake_pane(app, "local", [FileEntry("Season.03", "/Users/me/Season.03", "dir")])
        app.query_one("#local", FilePane).focus()
        await pilot.pause()
        await pilot.press("f6")
        job = app.manager.jobs[0]
        assert job.name == "Season.03/" and job.is_directory
        assert job.direction is Direction.UPLOAD


@pytest.mark.asyncio
async def test_queue_pane_shows_direction_arrows(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.manager.add("/downloads/a.mkv", "a.mkv", str(tmp_path), Direction.DOWNLOAD)
        app.manager.add("/downloads", "b.mkv", "/Users/me/b.mkv", Direction.UPLOAD)
        await pilot.pause()
        q = app.query_one("#queue", QueuePane)
        assert [str(q.get_row_at(i)[0]) for i in range(2)] == ["↓", "↑"]


# -- selection is per pane ---------------------------------------------------

@pytest.mark.asyncio
async def test_space_selects_in_the_local_pane(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        fake_pane(app, "local", [FileEntry("a.mkv", "/Users/me/a.mkv", "file", 10)])
        app.query_one("#local", FilePane).focus()
        await pilot.pause()
        await pilot.press("space")
        assert app.local_selected == {"/Users/me/a.mkv"}
        assert app.remote_selected == set()        # panes do not share marks


@pytest.mark.asyncio
async def test_enter_on_local_file_toggles_selection(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        fake_pane(app, "local", [FileEntry("a.mkv", "/Users/me/a.mkv", "file", 10)])
        app.query_one("#local", FilePane).focus()
        await pilot.pause()
        await pilot.press("enter")
        assert app.local_selected == {"/Users/me/a.mkv"}


@pytest.mark.asyncio
async def test_select_and_deselect_act_on_the_source_pane(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        fake_pane(app, "remote", [FileEntry("r.mkv", "/downloads/r.mkv", "file", 10)])
        fake_pane(app, "local", [FileEntry("l.mkv", "/Users/me/l.mkv", "file", 10),
                                 FileEntry("l.srt", "/Users/me/l.srt", "file", 10)])
        app.query_one("#local", FilePane).focus()
        await pilot.pause()
        await type_command(app, pilot, "select *")
        assert app.local_selected == {"/Users/me/l.mkv", "/Users/me/l.srt"}
        assert app.remote_selected == set()
        await type_command(app, pilot, "deselect *.srt")
        assert app.local_selected == {"/Users/me/l.mkv"}


@pytest.mark.asyncio
async def test_local_navigation_clears_local_marks(tmp_path):
    sub = tmp_path / "sub"
    sub.mkdir()
    app = make_app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.selected["local"].add(str(tmp_path / "x"))
        app.query_one("#local", FilePane).focus()
        await pilot.pause()
        await pilot.press("backspace")
        assert app.local_selected == set()


# -- confirming overwrites ---------------------------------------------------

def wire_fakes(app, *, exists):
    """Fake runner and a remote probe reporting every destination as present
    or absent."""
    app.manager._runner = FakeRunner([0] * 10)

    async def stat(paths):
        return {p: DestInfo(exists=exists, size=10, allocated=4096) for p in paths}

    app.manager._remote_stat = stat


async def run_download(app, pilot):
    app.download()
    for _ in range(20):
        await pilot.pause(0.05)
        if isinstance(app.screen, OverwriteScreen):
            return


@pytest.mark.asyncio
async def test_upload_onto_existing_file_asks_first(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        wire_fakes(app, exists=True)
        app.manager.add("/downloads", "a.mkv", "/Users/me/a.mkv", Direction.UPLOAD)
        await run_download(app, pilot)
        assert isinstance(app.screen, OverwriteScreen)
        assert app.manager._runner.calls == 0      # nothing sent before answering


@pytest.mark.asyncio
async def test_overwrite_answer_runs_the_upload(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        wire_fakes(app, exists=True)
        app.manager.add("/downloads", "a.mkv", "/Users/me/a.mkv", Direction.UPLOAD)
        await run_download(app, pilot)
        await pilot.click("#overwrite")
        await pilot.pause(0.2)
        assert app.manager._runner.calls == 1
        assert app.manager.jobs[0].status is JobStatus.COMPLETED


@pytest.mark.asyncio
async def test_skip_answer_leaves_the_server_file_alone(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        wire_fakes(app, exists=True)
        app.manager.add("/downloads", "a.mkv", "/Users/me/a.mkv", Direction.UPLOAD)
        await run_download(app, pilot)
        await pilot.click("#skip")
        await pilot.pause(0.2)
        assert app.manager._runner.calls == 0
        assert app.manager.jobs[0].status is JobStatus.SKIPPED


@pytest.mark.asyncio
async def test_cancel_answer_sends_nothing(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        wire_fakes(app, exists=True)
        app.manager.add("/downloads", "a.mkv", "/Users/me/a.mkv", Direction.UPLOAD)
        await run_download(app, pilot)
        await pilot.press("escape")                # escape is the safe answer
        await pilot.pause(0.2)
        assert app.manager._runner.calls == 0
        assert app.manager.jobs[0].status is JobStatus.QUEUED


@pytest.mark.asyncio
async def test_default_focus_is_the_non_destructive_choice(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        wire_fakes(app, exists=True)
        app.manager.add("/downloads", "a.mkv", "/Users/me/a.mkv", Direction.UPLOAD)
        await run_download(app, pilot)
        assert app.screen.focused.id == "skip"


@pytest.mark.asyncio
async def test_no_prompt_when_nothing_would_be_overwritten(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        wire_fakes(app, exists=False)
        app.manager.add("/downloads", "a.mkv", "/Users/me/a.mkv", Direction.UPLOAD)
        await run_download(app, pilot)
        await pilot.pause(0.2)
        assert not isinstance(app.screen, OverwriteScreen)
        assert app.manager._runner.calls == 1


@pytest.mark.asyncio
async def test_confirm_overwrite_can_be_disabled(tmp_path):
    app = make_app(tmp_path)
    app.config._data["transfer"]["confirm_overwrite"] = False
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        wire_fakes(app, exists=True)
        app.manager.add("/downloads", "a.mkv", "/Users/me/a.mkv", Direction.UPLOAD)
        await run_download(app, pilot)
        await pilot.pause(0.2)
        assert not isinstance(app.screen, OverwriteScreen)
        assert app.manager._runner.calls == 1


@pytest.mark.asyncio
async def test_downloads_never_trigger_the_overwrite_prompt(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        wire_fakes(app, exists=True)
        app.manager.add("/downloads/a.mkv", "a.mkv", str(tmp_path), Direction.DOWNLOAD)
        await run_download(app, pilot)
        await pilot.pause(0.2)
        assert not isinstance(app.screen, OverwriteScreen)


# -- mkdir on the right side -------------------------------------------------

@pytest.mark.asyncio
async def test_mkdir_in_remote_pane_runs_remotely_and_quotes(tmp_path, monkeypatch):
    from ncrsync.remote import remote_browser as rb

    sent = []

    async def fake_ssh(target, command):
        sent.append(command)
        return 0, "", ""

    monkeypatch.setattr(rb, "run_ssh", fake_ssh)
    app = make_app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.query_one("#remote", FilePane).focus()
        await pilot.pause()
        await type_command(app, pilot, "mkdir New [Folder]")
        await pilot.pause(0.2)
        mk = [c for c in sent if c.startswith("mkdir")]
        assert mk == ["mkdir -p -- '/downloads/New [Folder]'"]
        assert not (tmp_path / "New [Folder]").exists()      # not created locally


@pytest.mark.asyncio
async def test_mkdir_in_local_pane_runs_locally(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.query_one("#local", FilePane).focus()
        await pilot.pause()
        await type_command(app, pilot, "mkdir incoming")
        assert (tmp_path / "incoming").is_dir()


# -- verify follows the pane -------------------------------------------------

@pytest.mark.asyncio
async def test_verify_from_local_pane_compares_against_the_server(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.manager._runner = FakeRunner([0])
        fake_pane(app, "local", [FileEntry("a.mkv", "/Users/me/a.mkv", "file", 10)])
        app.query_one("#local", FilePane).focus()
        await pilot.pause()
        await type_command(app, pilot, "verify")
        await pilot.pause(0.2)
        argv = app.manager._runner.last_argv
        assert "--dry-run" in argv and "--checksum" in argv
        assert argv[-2] == "/Users/me/a.mkv"                   # local source
        assert argv[-1] == "myserver:/downloads/"              # remote destination


# -- doctor free-space parsing -----------------------------------------------

def test_df_parses_real_posix_output():
    out = ("Filesystem     1024-blocks      Used Available Capacity  Mounted on\n"
           "/dev/disk3s3s1   482797652  12337928 108147744    11%    /\n")
    assert parse_df_available(out) == 108147744 * 1024


def test_df_survives_spaces_in_the_mount_point():
    out = "server:/export  1000  400  600  40% /mnt/My Media\n"
    assert parse_df_available(out) == 600 * 1024


def test_df_unparseable_is_unknown():
    assert parse_df_available("") is None
    assert parse_df_available("df: /nope: No such file or directory") is None


# -- local listing identity ----------------------------------------------------

def test_symlinks_to_one_target_keep_distinct_paths(tmp_path):
    """Regression: rows were keyed on the resolved path, so two symlinks to
    the same target collided and crashed the table with DuplicateKey."""
    from ncrsync.local.local_browser import list_local

    (tmp_path / "target").mkdir()
    (tmp_path / "link1").symlink_to("target")
    (tmp_path / "link2").symlink_to("target")
    entries = list_local(tmp_path)
    paths = [e.path for e in entries]
    assert len(paths) == len(set(paths)) == 3


def test_symlink_path_keeps_its_own_name(tmp_path):
    """An upload's destination is named after the source basename. The entry
    path must end in the link's name, or the resume policy would inspect a
    different file from the one rsync writes."""
    from ncrsync.local.local_browser import list_local

    (tmp_path / "real.mkv").write_bytes(b"x")
    (tmp_path / "alias.mkv").symlink_to("real.mkv")
    by_name = {e.name: e.path for e in list_local(tmp_path)}
    assert by_name["alias.mkv"].endswith("/alias.mkv")


@pytest.mark.asyncio
async def test_local_pane_lists_a_directory_with_duplicate_symlinks(tmp_path):
    (tmp_path / "target").mkdir()
    (tmp_path / "link1").symlink_to("target")
    (tmp_path / "link2").symlink_to("target")
    app = make_app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        # the pane also lists the state/ dir make_app creates here, so check
        # the symlink rows by name rather than counting
        by_name = {e.name: e.path for e in app.query_one("#local", FilePane).entries}
        assert {"target", "link1", "link2"} <= set(by_name)
        assert by_name["link1"].endswith("/link1")
        assert by_name["link2"].endswith("/link2")
        assert len({by_name[n] for n in ("target", "link1", "link2")}) == 3
