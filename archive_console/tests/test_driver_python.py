"""Driver Python resolution for one-off / archive_* scripts."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from app.driver_python import resolve_driver_python_exe


def test_resolve_prefers_archive_console_venv(tmp_path: Path) -> None:
    root = tmp_path / "scripts"
    if os.name == "nt":
        exe = root / "archive_console" / ".venv" / "Scripts" / "python.exe"
    else:
        exe = root / "archive_console" / ".venv" / "bin" / "python"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"")
    assert resolve_driver_python_exe(root) == exe.resolve()


def test_resolve_falls_back_to_sys_executable(tmp_path: Path) -> None:
    root = tmp_path / "only_media"
    root.mkdir()
    assert resolve_driver_python_exe(root) == Path(sys.executable).resolve()
