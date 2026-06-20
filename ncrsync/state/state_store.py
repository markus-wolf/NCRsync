"""StateStore: session.json and recent_hosts.json (doc-06 §6-7).

macOS: ~/Library/Application Support/ncrsync/
Linux: ~/.local/state/ncrsync/
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional


def state_dir() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "ncrsync"
    return Path.home() / ".local" / "state" / "ncrsync"


class StateStore:
    def __init__(self, base: Optional[Path] = None):
        self.base = base or state_dir()
        self.base.mkdir(parents=True, exist_ok=True)

    @property
    def session_path(self) -> Path:
        return self.base / "session.json"

    @property
    def recent_hosts_path(self) -> Path:
        return self.base / "recent_hosts.json"

    def save_session(self, host: str, remote_cwd: str, local_cwd: str) -> None:
        data = {"version": 1, "host": host, "remote_cwd": remote_cwd, "local_cwd": local_cwd}
        self.session_path.write_text(json.dumps(data, indent=2))

    def load_session(self, host: str) -> Optional[dict]:
        if not self.session_path.exists():
            return None
        try:
            data = json.loads(self.session_path.read_text())
        except (json.JSONDecodeError, OSError):
            return None
        return data if data.get("host") == host else None

    def add_recent_host(self, host: str) -> None:
        hosts: list[str] = []
        if self.recent_hosts_path.exists():
            try:
                hosts = json.loads(self.recent_hosts_path.read_text())
            except (json.JSONDecodeError, OSError):
                hosts = []
        hosts = [h for h in hosts if h != host]
        hosts.insert(0, host)
        self.recent_hosts_path.write_text(json.dumps(hosts[:20], indent=2))
