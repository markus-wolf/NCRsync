"""CLI entrypoint. Usage: ncrsync TARGET   (alias / user@host / "host -p 2222")."""
from __future__ import annotations

import sys

from .app import NCRsync
from .config.config_loader import load_config
from .model.connection_profile import SshTarget


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if not args:
        cfg = load_config()
        default = cfg.get("default_host")
        if not default:
            print(__doc__)
            print("error: a target is required, e.g.  ncrsync 80078", file=sys.stderr)
            return 2
        target_raw = str(default)
    else:
        target_raw = args[0]

    try:
        SshTarget.parse(target_raw)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    config = load_config(SshTarget.parse(target_raw).host)
    NCRsync(target_raw, config=config).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
