"""Resolving what is actually running, and the fallbacks when git cannot say.

The distinction that matters: __version__ names the last release, which
understates a checkout that has moved past its tag.
"""
import pytest

from ncrsync import __version__
from ncrsync.version import VersionInfo, parse_describe, resolve


# -- parsing git describe ----------------------------------------------------

def test_exactly_on_a_tag():
    v = parse_describe("v0.5.0", "0.5.0")
    assert v.distance == 0 and not v.dirty
    assert v.short() == "0.5.0"
    assert v.is_release


def test_past_a_tag_shows_the_distance():
    v = parse_describe("v0.5.0-1-g68773e7", "0.5.0")
    assert v.distance == 1
    assert v.commit == "68773e7"
    assert v.short() == "0.5.0+1"        # honest: this is not the release
    assert not v.is_release
    assert "68773e7" in v.long()


def test_dirty_tree_is_marked():
    v = parse_describe("v0.5.0-2-gabc1234-dirty", "0.5.0")
    assert v.dirty and v.distance == 2
    assert v.short() == "0.5.0+2*"
    assert "modified" in v.long()


def test_bare_hash_when_no_tag_is_reachable():
    """Shallow clone: --always falls back to a hash, distance unknowable."""
    v = parse_describe("abc1234", "0.5.0")
    assert v.commit == "abc1234" and v.distance is None
    assert v.short() == "0.5.0 (abc1234)"
    assert not v.is_release


def test_dirty_bare_hash():
    v = parse_describe("abc1234-dirty", "0.5.0")
    assert v.dirty and v.commit == "abc1234"
    assert v.short().endswith("*")


# -- fallbacks ---------------------------------------------------------------

def test_installed_copy_has_no_repository(tmp_path):
    """uv tool install / uvx: no .git, and a wheel really is the release."""
    v = resolve(tmp_path)
    assert v == VersionInfo(release=__version__)
    assert v.short() == __version__
    assert v.long() == __version__
    assert v.is_release


def test_git_failure_falls_back_to_the_release(tmp_path, monkeypatch):
    from ncrsync import version as ver

    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(ver, "_run_git", lambda args, cwd: None)
    resolve.cache_clear()
    try:
        assert resolve(tmp_path).short() == __version__
    finally:
        resolve.cache_clear()


def test_resolution_is_cached(tmp_path, monkeypatch):
    """The header repaints at 10 Hz; resolving must not fork git each time."""
    from ncrsync import version as ver

    (tmp_path / ".git").mkdir()
    calls = []
    monkeypatch.setattr(ver, "_run_git",
                        lambda args, cwd: calls.append(args) or "v0.5.0-1-gdeadbee")
    resolve.cache_clear()
    try:
        for _ in range(20):
            resolve(tmp_path)
        assert len(calls) == 1
    finally:
        resolve.cache_clear()


# -- the label reaches the UI ------------------------------------------------

@pytest.mark.asyncio
async def test_title_carries_the_version(tmp_path):
    from .test_app_smoke import make_app

    app = make_app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert app.title.startswith("NCRsync ")
        assert app.version.release in app.title


@pytest.mark.asyncio
async def test_title_survives_a_spinner_repaint(tmp_path):
    """_update_title runs on every spinner tick; the version must persist."""
    from .test_app_smoke import make_app

    app = make_app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        before = app.title
        app._busy = True
        app._tick_spinner()
        assert app.title == before        # spinner lives in sub_title, not title
