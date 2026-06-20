"""Path-safety and listing tests - the core correctness rules from doc-03/08."""
import shlex

import pytest

from ncrsync.model.connection_profile import SshTarget
from ncrsync.model.file_entry import human_size, sort_entries
from ncrsync.remote.path_utils import (
    build_remote_list_cmd,
    parse_find_output,
    remote_resolve,
)
from ncrsync.transfer.rsync_caps import compute_caps
from ncrsync.transfer.rsync_runner import build_rsync_argv

BRACKET_PATH = (
    "/downloads/tv/The.Lincoln.Lawyer.S03.COMPLETE.720p.NF.WEBRip.x264-GalaxyTV[TGx]/"
    "The.Lincoln.Lawyer.S03E01.720p.NF.WEBRip.x264-GalaxyTV.mkv"
)

MODERN = compute_caps((3, 4, 4), (3, 4, 4))
LEGACY = compute_caps((3, 4, 4), (2, 6, 9))


def test_target_parse_alias():
    t = SshTarget.parse("80078")
    assert t.host == "80078" and t.opts == []


def test_target_parse_user_host():
    t = SshTarget.parse("alex@example.com")
    assert t.host == "alex@example.com"


def test_target_parse_with_port():
    t = SshTarget.parse("alex@example.com -p 2222")
    assert t.host == "alex@example.com"
    assert t.opts == ["-p", "2222"]
    assert t.ssh_argv("echo hi") == ["ssh", "-p", "2222", "alex@example.com", "echo hi"]


def test_target_parse_no_host_raises():
    with pytest.raises(ValueError):
        SshTarget.parse("-p 2222")


def test_bracket_source_is_raw_unquoted():
    t = SshTarget.parse("80078")
    argv = build_rsync_argv(t, BRACKET_PATH, "/Users/alex/Downloads", MODERN, rsync_bin="rsync")
    source = argv[-2]
    assert source == f"80078:{BRACKET_PATH}"
    assert "'" not in source and "\\" not in source  # no quoting/escaping
    assert "-s" in argv  # protect-args present on modern rsync


def test_dest_ends_with_slash():
    t = SshTarget.parse("80078")
    argv = build_rsync_argv(t, BRACKET_PATH, "/Users/alex/Downloads", MODERN)
    assert argv[-1].endswith("/")


def test_legacy_degraded_quotes_path_and_drops_protect_args():
    t = SshTarget.parse("80078")
    argv = build_rsync_argv(t, "/p/has space.mkv", "/dest", LEGACY)
    assert "-s" not in argv
    source = argv[-2]
    # legacy: path portion is shell-quoted so the remote shell won't split it
    assert source == "80078:'/p/has space.mkv'"


def test_remote_list_cmd_is_shell_quoted():
    cmd = build_remote_list_cmd("/downloads/tv/has space[bracket]")
    assert "'/downloads/tv/has space[bracket]'" in cmd
    assert "find . -maxdepth 1 -mindepth 1 -printf" in cmd


def test_parse_find_output():
    sample = (
        "d\t4096\t2026-06-20 10:00:00.0\tdrwxr-xr-x\tThe.Show.S03\n"
        "f\t734003200\t2026-06-19 22:15:03.0\t-rw-r--r--\tThe.Show.S03E01.mkv\n"
    )
    entries = sort_entries(parse_find_output(sample, "/downloads/tv"))
    assert [e.kind for e in entries] == ["dir", "file"]
    assert entries[1].path == "/downloads/tv/The.Show.S03E01.mkv"
    assert entries[1].size == 734003200


def test_parse_find_ignores_ls_fallback_lines():
    # ls -la lines don't have 5 tab-separated fields -> skipped
    sample = "total 8\ndrwxr-xr-x  2 user group 4096 Jun 20 10:00 somedir\n"
    assert parse_find_output(sample, "/x") == []


def test_remote_resolve():
    assert remote_resolve("/a/b", "c") == "/a/b/c"
    assert remote_resolve("/a/b", "..") == "/a"
    assert remote_resolve("/a/b", "/x/y") == "/x/y"


def test_human_size():
    assert human_size(0) == "0B"
    assert human_size(1024) == "1.0K"
    assert human_size(734003200).endswith("M")
