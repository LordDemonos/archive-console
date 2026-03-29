"""Server-side folder picker on the Archive Console host (not the browser).

Windows: prefers ``powershell.exe -Sta`` + ``System.Windows.Forms.FolderBrowserDialog`` so
the dialog works when the API runs under uvicorn/tray (tkinter often yields no visible
dialog or immediate empty result in those contexts). Falls back to tkinter if PowerShell
fails. Other platforms: tkinter only.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Literal

PickStatus = Literal["picked", "cancelled", "unavailable"]

_browse_lock = threading.Lock()

_PS_FOLDER_SCRIPT = """
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
$d = New-Object System.Windows.Forms.FolderBrowserDialog
$t = $env:AC_FOLDER_DLG_TITLE
if (-not $t) { $t = 'Choose folder' }
$d.Description = [string]$t
$d.ShowNewFolderButton = $true
$dr = $d.ShowDialog()
if ($dr -eq [System.Windows.Forms.DialogResult]::OK -and $d.SelectedPath) {
  [Console]::Out.WriteLine($d.SelectedPath)
}
"""


def _pick_windows_powershell(title: str) -> tuple[PickStatus, str]:
    """Native folder dialog in a separate STA process (recommended on Windows)."""
    env = os.environ.copy()
    env["AC_FOLDER_DLG_TITLE"] = (title or "Choose folder")[:1024]
    cmd = ["powershell.exe", "-NoProfile", "-Sta", "-Command", _PS_FOLDER_SCRIPT]
    popen_kw: dict = {
        "capture_output": True,
        "text": True,
        "env": env,
    }
    if sys.platform == "win32":
        popen_kw["creationflags"] = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
    try:
        r = subprocess.run(cmd, **popen_kw)
    except FileNotFoundError:
        return ("unavailable", "powershell.exe not found")
    except OSError as exc:
        return ("unavailable", type(exc).__name__)

    if r.returncode != 0:
        err = ((r.stderr or r.stdout or "").strip())[:300]
        return ("unavailable", f"powershell exit {r.returncode}: {err}" if err else "powershell failed")

    out = (r.stdout or "").strip()
    if not out:
        return ("cancelled", "")
    try:
        resolved = str(Path(out).expanduser().resolve())
    except OSError:
        return ("cancelled", "")
    return ("picked", resolved)


def _pick_tkinter(title: str) -> tuple[PickStatus, str]:
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception as exc:  # pragma: no cover - env specific
        return ("unavailable", f"tkinter: {type(exc).__name__}")

    root = tk.Tk()
    root.withdraw()
    try:
        try:
            root.attributes("-topmost", True)
        except tk.TclError:
            pass
        try:
            root.lift()
            root.focus_force()
        except tk.TclError:
            pass
        path = filedialog.askdirectory(
            title=title or "Choose folder",
            mustexist=True,
        )
    finally:
        try:
            root.destroy()
        except tk.TclError:
            pass

    if not path or not str(path).strip():
        return ("cancelled", "")
    try:
        resolved = str(Path(path).expanduser().resolve())
    except OSError:
        return ("cancelled", "")
    return ("picked", resolved)


def pick_directory_host(title: str) -> tuple[PickStatus, str]:
    """
    Open a native directory dialog (blocks until closed).
    Returns (``picked``, absolute path), (``cancelled``, ""), or (``unavailable``, short reason).
    """
    with _browse_lock:
        if sys.platform == "win32":
            status, payload = _pick_windows_powershell(title)
            if status != "unavailable":
                return (status, payload)
            return _pick_tkinter(title)
        return _pick_tkinter(title)
