"""Shared argv for starting the Archive Console ASGI app (CLI, tray, installers)."""

from __future__ import annotations


def uvicorn_argv(*, host: str, port: int, log_level: str = "info") -> list[str]:
    """Command-line tokens: ``python -m uvicorn ...`` (cwd must be ``archive_console``)."""
    return [
        "uvicorn",
        "app.main:app",
        "--host",
        host,
        "--port",
        str(int(port)),
        "--log-level",
        log_level,
    ]
