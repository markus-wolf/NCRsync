"""SshTarget: parse the CLI target into a host token + ssh options.

The host token feeds the rsync ``host:path`` source; the options feed both the
``ssh`` listing command and rsync's ``-e`` transport.
"""
from __future__ import annotations

import shlex
from dataclasses import dataclass, field

# ssh options that consume a following value
_TAKES_VALUE = {"-p", "-i", "-o", "-l", "-F", "-J", "-c", "-m", "-b", "-D", "-L", "-R", "-W"}

# ssh keepalive options injected into the rsync transport (doc-04 §2)
SSH_OPTS_KEEPALIVE = [
    "-o", "Compression=no",
    "-o", "ServerAliveInterval=30",
    "-o", "ServerAliveCountMax=6",
]


@dataclass
class SshTarget:
    host: str
    opts: list[str] = field(default_factory=list)

    @classmethod
    def parse(cls, raw: str) -> "SshTarget":
        parts = shlex.split(raw)
        host = None
        opts: list[str] = []
        i = 0
        while i < len(parts):
            p = parts[i]
            if p.startswith("-"):
                opts.append(p)
                if p in _TAKES_VALUE and i + 1 < len(parts):
                    opts.append(parts[i + 1])
                    i += 1
            elif host is None:
                host = p
            else:
                opts.append(p)  # extra bareword -> pass through as ssh arg
            i += 1
        if host is None:
            raise ValueError(f"could not find a host in target: {raw!r}")
        return cls(host=host, opts=opts)

    def ssh_argv(self, remote_command: str) -> list[str]:
        """argv to run a command on the remote shell."""
        return ["ssh", *self.opts, self.host, remote_command]

    def rsync_e_value(self, keepalive: list[str] | None = None) -> str:
        """Value for rsync's ``-e`` (transport) option."""
        ka = SSH_OPTS_KEEPALIVE if keepalive is None else keepalive
        return shlex.join(["ssh", *self.opts, *ka])
