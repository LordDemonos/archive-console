#!/usr/bin/env python3
"""TTY-colored line for monthly .bat files (same rules as archive_run_console: NO_COLOR, ARCHIVE_PLAIN_LOG, isatty)."""

from __future__ import annotations

import sys

from archive_run_console import init_console, print_role

_VALID_ROLES = frozenset(
    {"ok", "warn", "error", "skip", "info", "header", "dim"},
)


def main() -> int:
    if len(sys.argv) < 3:
        print(
            "usage: archive_print_role.py <role> <message...>",
            file=sys.stderr,
        )
        return 2
    init_console()
    role = sys.argv[1]
    if role not in _VALID_ROLES:
        role = "info"
    print_role(" ".join(sys.argv[2:]), role)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
