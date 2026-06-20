"""Load and merge configuration (doc-06).

Precedence (low -> high): DEFAULTS  <  ~/.config/ncrsync/config.toml  <  [hosts.<host>].
The returned Config is a thin attribute-friendly view with helpers for the
per-host directories.
"""
from __future__ import annotations

import copy
import tomllib
from pathlib import Path
from typing import Any, Optional

from .defaults import DEFAULTS

CONFIG_PATH = Path.home() / ".config" / "ncrsync" / "config.toml"


def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


class Config:
    def __init__(self, data: dict, host: Optional[str] = None):
        self._data = data
        self.host = host
        self._host_cfg: dict = data.get("hosts", {}).get(host, {}) if host else {}

    # section accessors
    @property
    def ui(self) -> dict:
        return self._data["ui"]

    @property
    def ssh(self) -> dict:
        return self._data["ssh"]

    @property
    def transfer(self) -> dict:
        return self._data["transfer"]

    @property
    def rsync_bin(self) -> str:
        return self._data["rsync_bin"]

    def get(self, *keys: str, default: Any = None) -> Any:
        node: Any = self._data
        for k in keys:
            if not isinstance(node, dict) or k not in node:
                return default
            node = node[k]
        return node

    def default_remote_dir(self) -> str:
        return self._host_cfg.get("default_remote_dir", "/downloads")

    def default_local_dir(self) -> str:
        return self._host_cfg.get("default_local_dir", "~/Downloads")

    @property
    def keepalive_opts(self) -> list[str]:
        ssh = self.ssh
        opts: list[str] = []
        if not ssh.get("compression", False):
            opts += ["-o", "Compression=no"]
        opts += ["-o", f"ServerAliveInterval={ssh.get('server_alive_interval', 30)}"]
        opts += ["-o", f"ServerAliveCountMax={ssh.get('server_alive_count_max', 6)}"]
        return opts


def load_config(host: Optional[str] = None, path: Optional[Path] = None) -> Config:
    cfg_path = path or CONFIG_PATH
    merged = copy.deepcopy(DEFAULTS)
    if cfg_path.exists():
        with cfg_path.open("rb") as fh:
            user = tomllib.load(fh)
        merged = _deep_merge(merged, user)
    return Config(merged, host=host)
