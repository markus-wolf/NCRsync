"""Default configuration (doc-06 §2). Overlaid by the user's config.toml."""
from __future__ import annotations

import shutil

# Resolve a sensible rsync binary default: Homebrew path, else PATH, else "rsync".
_BREW_RSYNC = "/opt/homebrew/bin/rsync"


def _default_rsync_bin() -> str:
    import os

    if os.path.exists(_BREW_RSYNC):
        return _BREW_RSYNC
    return shutil.which("rsync") or "rsync"


DEFAULTS: dict = {
    "default_host": None,
    "rsync_bin": _default_rsync_bin(),
    "ui": {
        "theme": "nc-blue",
        "show_hidden": True,
        "confirm_delete": True,
    },
    "ssh": {
        "compression": False,
        "server_alive_interval": 30,
        "server_alive_count_max": 6,
    },
    "transfer": {
        "append_verify": True,   # honored only where rsync supports it (see rsync_caps)
        "partial": True,
        "timeout": 120,
        "protect_args": True,
        "bwlimit": 0,            # 0 = unlimited; KiB/s otherwise
        "continue_on_error": False,
        "max_retries": 3,
        "retry_delay_seconds": 5,
    },
    # per-host overrides live under [hosts.<name>], e.g.
    # "hosts": {"myserver": {"default_remote_dir": "/downloads",
    #                      "default_local_dir": "~/Downloads"}}
    "hosts": {},
}
