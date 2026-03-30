"""Subprocess helpers for gallery-dl (preview and path resolution)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def resolve_gallery_dl_exe(explicit: str | None) -> str:
    r"""
    Resolve the gallery-dl executable.

    ``start_archive_console.bat`` runs ``.venv\Scripts\python.exe -m uvicorn`` without
    activating the venv, so ``PATH`` often does **not** include ``Scripts``. Prefer
    ``shutil.which`` when present, then the console script next to ``sys.executable``
    (same layout as ``pip install -r requirements.txt`` in the Archive Console venv).
    """
    ex = (explicit or "").strip()
    if ex:
        return ex
    w = shutil.which("gallery-dl")
    if w:
        return w
    try:
        bindir = Path(sys.executable).resolve().parent
        for name in ("gallery-dl.exe", "gallery-dl"):
            candidate = bindir / name
            if candidate.is_file():
                return str(candidate)
    except OSError:
        pass
    return "gallery-dl"


def gallery_dl_exe_invocable(exe: str) -> bool:
    """True if ``exe`` is a PATH command or an existing file path."""
    if not exe:
        return False
    if shutil.which(exe):
        return True
    try:
        return Path(exe).is_file()
    except OSError:
        return False


def gallery_dl_executable_ready(explicit: str | None = None) -> bool:
    """True after ``resolve_gallery_dl_exe`` when the binary can be run."""
    return gallery_dl_exe_invocable(resolve_gallery_dl_exe(explicit))


def run_gallery_dl_json_dump(
    *,
    exe: str,
    url: str,
    cwd: Path,
    cookies_file: Path | None,
    conf_file: Path | None,
    timeout_sec: float,
) -> tuple[int, str, str]:
    """
    Run gallery-dl in simulate + JSON dump mode (no media files written).
    Returns (exit_code, combined_stdout, combined_stderr).
    """
    cmd: list[str] = [exe]
    if conf_file and conf_file.is_file():
        cmd.extend(["-c", str(conf_file)])
    if cookies_file and cookies_file.is_file():
        cmd.extend(["--cookies", str(cookies_file)])
    cmd.extend(["-s", "-j", url])
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_sec,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
        out = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
        return proc.returncode, proc.stdout or "", out
    except subprocess.TimeoutExpired as e:
        partial = (e.stdout or "") + ("\n" + (e.stderr or ""))
        return -124, e.stdout or "", partial + "\n[timeout]"
