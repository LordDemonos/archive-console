"""Resolve the Python executable for archive_* drivers (yt-dlp stack).

Monthly BAT files run under cmd with ``python`` on PATH (often the user's global
interpreter). Archive Console one-off runs ``archive_oneoff_run.py`` directly and
must use the same layout as ``start_archive_console.bat``: the venv under
``<archive_root>/archive_console/.venv`` when present, so ``import yt_dlp`` matches
``pip install -r archive_console/requirements.txt``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def resolve_driver_python_exe(archive_root: Path) -> Path:
    """Return python.exe (Windows) or python (Unix) for driver scripts.

    Prefers ``<archive_root>/archive_console/.venv`` (standard repo layout),
    then ``<archive_root>/.venv`` (optional root-level venv), else the current
    interpreter (uvicorn).
    """
    root = archive_root.expanduser().resolve()
    if os.name == "nt":
        candidates = (
            root / "archive_console" / ".venv" / "Scripts" / "python.exe",
            root / ".venv" / "Scripts" / "python.exe",
        )
    else:
        candidates = (
            root / "archive_console" / ".venv" / "bin" / "python",
            root / ".venv" / "bin" / "python",
        )
    for c in candidates:
        if c.is_file():
            return c
    return Path(sys.executable).resolve()
