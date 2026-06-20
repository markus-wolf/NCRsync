"""File logging setup (doc-06 §3-5).

macOS: ~/Library/Logs/ncrsync/   Linux: ~/.local/state/ncrsync/logs/
Writes session-YYYYMMDD-HHMMSS.log and keeps latest.log pointing at it.
"""
from __future__ import annotations

import logging
import platform
import sys
from datetime import datetime
from pathlib import Path

from . import __version__


def log_dir() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Logs" / "ncrsync"
    return Path.home() / ".local" / "state" / "ncrsync" / "logs"


def setup_logging(target_host: str, argv: list[str]) -> Path:
    """Configure the 'ncrsync' logger with a session file. Returns the file path."""
    d = log_dir()
    d.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    session_path = d / f"session-{stamp}.log"

    logger = logging.getLogger("ncrsync")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    handler = logging.FileHandler(session_path, encoding="utf-8")
    handler.setFormatter(fmt)
    logger.addHandler(handler)
    logger.propagate = False

    # refresh latest.log -> copy of newest path (symlink where possible)
    latest = d / "latest.log"
    try:
        if latest.exists() or latest.is_symlink():
            latest.unlink()
        latest.symlink_to(session_path.name)
    except OSError:
        pass  # symlinks may be unavailable; session file is authoritative

    logger.info("NCRsync %s starting", __version__)
    logger.info("argv: %s", " ".join(argv))
    logger.info("platform: %s", platform.platform())
    logger.info("python: %s", sys.version.split()[0])
    logger.info("target: %s", target_host)
    return session_path
