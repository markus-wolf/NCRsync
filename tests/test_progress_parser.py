"""Progress parsing (opportunistic)."""
from ncrsync.transfer.progress_parser import parse_progress_line


def test_parse_progress2_line():
    line = "      1,234,567  45%    2.34MB/s    0:01:23"
    p = parse_progress_line(line)
    assert p is not None
    assert p.percent == 45
    assert p.bytes == 1234567
    assert "MB/s" in p.rate
    assert p.eta == "0:01:23"
    assert "45%" in p.as_status()


def test_non_progress_line_returns_none():
    assert parse_progress_line("sending incremental file list") is None
    assert parse_progress_line("") is None
