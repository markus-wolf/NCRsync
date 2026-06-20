"""Persistence + config tests."""
import textwrap
from pathlib import Path

from ncrsync.config.config_loader import load_config
from ncrsync.model.transfer_job import JobStatus, TransferJob
from ncrsync.state.queue_store import QueueStore
from ncrsync.state.state_store import StateStore


def test_queue_round_trip(tmp_path: Path):
    store = QueueStore(base=tmp_path)
    jobs = [
        TransferJob("/r/a.mkv", "/local", "a.mkv", JobStatus.COMPLETED),
        TransferJob("/r/b.mkv", "/local", "b.mkv", JobStatus.QUEUED),
    ]
    store.save("80078", "/r", "/local", jobs)
    data = store.load()
    assert data["host"] == "80078"
    assert [j.name for j in data["jobs"]] == ["a.mkv", "b.mkv"]
    assert [j.status for j in data["jobs"]] == [JobStatus.COMPLETED, JobStatus.QUEUED]


def test_recovery_detection(tmp_path: Path):
    store = QueueStore(base=tmp_path)
    # all completed -> nothing to recover
    store.save("h", "/r", "/l", [TransferJob("/r/a", "/l", "a", JobStatus.COMPLETED)])
    assert not QueueStore.has_unfinished(store.load())
    # a queued item -> recover
    store.save("h", "/r", "/l", [TransferJob("/r/b", "/l", "b", JobStatus.QUEUED)])
    assert QueueStore.has_unfinished(store.load())


def test_running_job_treated_as_interrupted(tmp_path: Path):
    store = QueueStore(base=tmp_path)
    store.save("h", "/r", "/l", [TransferJob("/r/c", "/l", "c", JobStatus.RUNNING)])
    data = store.load()
    # reloaded as queued so it resumes
    assert data["jobs"][0].status == JobStatus.QUEUED
    assert QueueStore.has_unfinished(data)


def test_session_round_trip(tmp_path: Path):
    store = StateStore(base=tmp_path)
    store.save_session("80078", "/downloads/tv", "/Users/alex/Downloads")
    assert store.load_session("80078")["remote_cwd"] == "/downloads/tv"
    assert store.load_session("other-host") is None  # host mismatch


def test_recent_hosts(tmp_path: Path):
    store = StateStore(base=tmp_path)
    store.add_recent_host("a")
    store.add_recent_host("b")
    store.add_recent_host("a")  # moves to front, deduped
    import json

    hosts = json.loads(store.recent_hosts_path.read_text())
    assert hosts[0] == "a" and hosts.count("a") == 1


def test_config_precedence(tmp_path: Path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(textwrap.dedent("""
        rsync_bin = "/custom/rsync"
        [ui]
        theme = "dark"
        [transfer]
        bwlimit = 4000
        [hosts.80078]
        default_remote_dir = "/media"
        default_local_dir = "~/Movies"
    """))
    cfg = load_config("80078", path=cfg_file)
    assert cfg.rsync_bin == "/custom/rsync"          # override
    assert cfg.ui["theme"] == "dark"                  # override
    assert cfg.ui["show_hidden"] is True              # default preserved
    assert cfg.transfer["bwlimit"] == 4000            # override
    assert cfg.default_remote_dir() == "/media"       # per-host
    assert cfg.default_local_dir() == "~/Movies"      # per-host


def test_config_defaults_when_missing(tmp_path: Path):
    cfg = load_config("nohost", path=tmp_path / "does-not-exist.toml")
    assert cfg.default_remote_dir() == "/downloads"
    assert cfg.transfer["max_retries"] == 3
