"""rsync capability detection + flag selection across versions."""
from ncrsync.transfer.rsync_caps import (
    compute_caps,
    parse_rsync_version,
    select_flags,
)


def test_parse_version():
    assert parse_rsync_version("rsync  version 3.4.4  protocol version 32") == (3, 4, 4)
    assert parse_rsync_version("rsync version 3.1.3") == (3, 1, 3)
    assert parse_rsync_version("rsync version 2.6.9") == (2, 6, 9)
    assert parse_rsync_version("garbage") is None


def test_effective_is_min_of_both_ends():
    caps = compute_caps((3, 4, 4), (3, 0, 9))
    assert caps.effective == (3, 0, 9)


def test_unknown_remote_falls_back_to_local():
    caps = compute_caps((3, 4, 4), None)
    assert caps.effective == (3, 4, 4)
    assert not caps.degraded


def test_flags_modern_3_2_plus():
    caps = compute_caps((3, 4, 4), (3, 4, 4))
    flags = select_flags(caps)
    assert "-s" in flags
    assert "--append" in flags and "--append-verify" not in flags
    assert "--info=progress2" in flags


def test_flags_3_0_uses_append_verify_and_plain_progress():
    caps = compute_caps((3, 0, 9), (3, 0, 9))
    flags = select_flags(caps)
    assert "-s" in flags
    assert "--append-verify" in flags
    assert "--progress" in flags and "--info=progress2" not in flags


def test_flags_3_1_uses_append_verify_and_progress2():
    caps = compute_caps((3, 1, 3), (3, 1, 3))
    flags = select_flags(caps)
    assert "--append-verify" in flags
    assert "--info=progress2" in flags


def test_flags_legacy_under_3_0_degraded():
    caps = compute_caps((3, 4, 4), (2, 6, 9))
    assert caps.degraded
    flags = select_flags(caps)
    assert "-s" not in flags
    assert "--append" not in flags and "--append-verify" not in flags
    assert "--partial" in flags
    assert "--progress" in flags


def test_tier_strings():
    assert compute_caps((3, 4, 4), (3, 4, 4)).tier == ">=3.2"
    assert compute_caps((3, 1, 3), (3, 1, 3)).tier == "3.1"
    assert compute_caps((3, 0, 0), (3, 0, 0)).tier == "3.0"
    assert "degraded" in compute_caps((2, 6, 9), (2, 6, 9)).tier
