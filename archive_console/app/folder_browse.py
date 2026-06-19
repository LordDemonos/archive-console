"""Server-side folder and file pickers on the Archive Console host (not the browser).

Windows: prefers ``powershell.exe -Sta`` + ``System.Windows.Forms`` dialogs so
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

_PS_UTF8_PREAMBLE = """
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
"""

_PS_FOLDER_SCRIPT = (
    _PS_UTF8_PREAMBLE
    + """
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()
$dlgTitle = if ($env:AC_FOLDER_DLG_TITLE) { $env:AC_FOLDER_DLG_TITLE } else { 'Choose folder' }
$startPath = $env:AC_FOLDER_START_PATH
$owner = New-Object System.Windows.Forms.Form
$owner.TopMost = $true
$owner.ShowInTaskbar = $false
$owner.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::None
$owner.Size = New-Object System.Drawing.Size(0, 0)
$owner.StartPosition = [System.Windows.Forms.FormStartPosition]::Manual
$owner.Location = New-Object System.Drawing.Point(-20000, -20000)
$owner.Add_Shown({
    $d = New-Object System.Windows.Forms.FolderBrowserDialog
    $d.Description = [string]$dlgTitle
    $d.ShowNewFolderButton = $true
    if ($startPath) {
        try {
            if (Test-Path -LiteralPath $startPath -PathType Container) {
                $d.SelectedPath = $startPath
            } else {
                $parent = Split-Path -LiteralPath $startPath -Parent
                if ($parent -and (Test-Path -LiteralPath $parent -PathType Container)) {
                    $d.SelectedPath = $parent
                }
            }
        } catch { }
    }
    $dr = $d.ShowDialog($owner)
    if ($dr -eq [System.Windows.Forms.DialogResult]::OK -and $d.SelectedPath) {
        [Console]::Out.WriteLine($d.SelectedPath)
    }
    $owner.Close()
})
$null = $owner.ShowDialog()
"""
)


def _run_powershell(script: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Run PowerShell with UTF-8 stdout (required for non-ASCII paths on Windows)."""
    cmd = ["powershell.exe", "-NoProfile", "-Sta", "-Command", script]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )


def _browse_env(title: str, initial_dir: str | None, title_env: str) -> dict[str, str]:
    env = os.environ.copy()
    env[title_env] = (title or "Choose folder")[:1024]
    start = (initial_dir or "").strip()
    if start:
        try:
            p = Path(start).expanduser()
            if p.is_dir():
                env["AC_FOLDER_START_PATH"] = str(p.resolve())
            elif p.parent.is_dir():
                env["AC_FOLDER_START_PATH"] = str(p.parent.resolve())
        except OSError:
            pass
    return env


def _pick_windows_powershell(
    title: str,
    *,
    script: str,
    title_env: str,
    initial_dir: str | None = None,
) -> tuple[PickStatus, str]:
    """Native dialog in a separate STA process (recommended on Windows)."""
    env = _browse_env(title, initial_dir, title_env)
    try:
        r = _run_powershell(script, env)
    except FileNotFoundError:
        return ("unavailable", "powershell.exe not found")
    except OSError as exc:
        return ("unavailable", type(exc).__name__)

    if r.returncode != 0:
        err = ((r.stderr or r.stdout or "").strip())[:300]
        return (
            "unavailable",
            f"powershell exit {r.returncode}: {err}" if err else "powershell failed",
        )

    out = (r.stdout or "").strip()
    if not out:
        return ("cancelled", "")
    try:
        resolved = str(Path(out).expanduser().resolve())
    except OSError:
        return ("cancelled", "")
    return ("picked", resolved)


def _pick_tkinter(title: str, initial_dir: str | None = None) -> tuple[PickStatus, str]:
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
        initial = (initial_dir or "").strip()
        initial_kw: dict = {}
        if initial:
            try:
                p = Path(initial).expanduser()
                if p.is_dir():
                    initial_kw["initialdir"] = str(p.resolve())
                elif p.parent.is_dir():
                    initial_kw["initialdir"] = str(p.parent.resolve())
            except OSError:
                pass
        path = filedialog.askdirectory(
            title=title or "Choose folder",
            mustexist=True,
            **initial_kw,
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


def pick_directory_host(
    title: str,
    initial_dir: str | None = None,
) -> tuple[PickStatus, str]:
    """
    Open a native directory dialog (blocks until closed).
    Returns (``picked``, absolute path), (``cancelled``, ""), or (``unavailable``, short reason).
    """
    with _browse_lock:
        if sys.platform == "win32":
            status, payload = _pick_windows_powershell(
                title,
                script=_PS_FOLDER_SCRIPT,
                title_env="AC_FOLDER_DLG_TITLE",
                initial_dir=initial_dir,
            )
            if status != "unavailable":
                return (status, payload)
            return _pick_tkinter(title, initial_dir)
        return _pick_tkinter(title, initial_dir)


_PS_FILE_SCRIPT = (
    _PS_UTF8_PREAMBLE
    + """
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()
$dlgTitle = if ($env:AC_FILE_DLG_TITLE) { $env:AC_FILE_DLG_TITLE } else { 'Choose file' }
$startPath = $env:AC_FOLDER_START_PATH
$owner = New-Object System.Windows.Forms.Form
$owner.TopMost = $true
$owner.ShowInTaskbar = $false
$owner.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::None
$owner.Size = New-Object System.Drawing.Size(0, 0)
$owner.StartPosition = [System.Windows.Forms.FormStartPosition]::Manual
$owner.Location = New-Object System.Drawing.Point(-20000, -20000)
$owner.Add_Shown({
    $d = New-Object System.Windows.Forms.OpenFileDialog
    $d.Title = [string]$dlgTitle
    $d.Filter = 'Executables (*.exe)|*.exe|All files (*.*)|*.*'
    $d.CheckFileExists = $true
    if ($startPath) {
        try {
            if (Test-Path -LiteralPath $startPath -PathType Leaf) {
                $d.InitialDirectory = (Split-Path -LiteralPath $startPath -Parent)
                $d.FileName = (Split-Path -LiteralPath $startPath -Leaf)
            } elseif (Test-Path -LiteralPath $startPath -PathType Container) {
                $d.InitialDirectory = $startPath
            } else {
                $parent = Split-Path -LiteralPath $startPath -Parent
                if ($parent -and (Test-Path -LiteralPath $parent -PathType Container)) {
                    $d.InitialDirectory = $parent
                }
            }
        } catch { }
    }
    $dr = $d.ShowDialog($owner)
    if ($dr -eq [System.Windows.Forms.DialogResult]::OK -and $d.FileName) {
        [Console]::Out.WriteLine($d.FileName)
    }
    $owner.Close()
})
$null = $owner.ShowDialog()
"""
)


def _pick_file_windows_powershell(
    title: str,
    initial_dir: str | None = None,
) -> tuple[PickStatus, str]:
    return _pick_windows_powershell(
        title,
        script=_PS_FILE_SCRIPT,
        title_env="AC_FILE_DLG_TITLE",
        initial_dir=initial_dir,
    )


def _pick_file_tkinter(title: str, initial_dir: str | None = None) -> tuple[PickStatus, str]:
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
        initial = (initial_dir or "").strip()
        initial_kw: dict = {}
        if initial:
            try:
                p = Path(initial).expanduser()
                if p.is_file():
                    initial_kw["initialdir"] = str(p.parent.resolve())
                    initial_kw["initialfile"] = p.name
                elif p.is_dir():
                    initial_kw["initialdir"] = str(p.resolve())
                elif p.parent.is_dir():
                    initial_kw["initialdir"] = str(p.parent.resolve())
            except OSError:
                pass
        path = filedialog.askopenfilename(
            title=title or "Choose file",
            filetypes=[
                ("Executables", "*.exe"),
                ("All files", "*.*"),
            ],
            **initial_kw,
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


def pick_file_host(
    title: str,
    initial_dir: str | None = None,
) -> tuple[PickStatus, str]:
    """
    Open a native file dialog (blocks until closed).
    Returns (``picked``, absolute path), (``cancelled``, ""), or (``unavailable``, short reason).
    """
    with _browse_lock:
        if sys.platform == "win32":
            status, payload = _pick_file_windows_powershell(title, initial_dir)
            if status != "unavailable":
                return (status, payload)
            return _pick_file_tkinter(title, initial_dir)
        return _pick_file_tkinter(title, initial_dir)


_PS_FILES_SCRIPT = (
    _PS_UTF8_PREAMBLE
    + """
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()
$dlgTitle = if ($env:AC_FILE_DLG_TITLE) { $env:AC_FILE_DLG_TITLE } else { 'Choose files' }
$startPath = $env:AC_FOLDER_START_PATH
$owner = New-Object System.Windows.Forms.Form
$owner.TopMost = $true
$owner.ShowInTaskbar = $false
$owner.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::None
$owner.Size = New-Object System.Drawing.Size(0, 0)
$owner.StartPosition = [System.Windows.Forms.FormStartPosition]::Manual
$owner.Location = New-Object System.Drawing.Point(-20000, -20000)
$owner.Add_Shown({
    $d = New-Object System.Windows.Forms.OpenFileDialog
    $d.Title = [string]$dlgTitle
    $d.Filter = 'All files (*.*)|*.*'
    $d.CheckFileExists = $true
    $d.Multiselect = $true
    if ($startPath) {
        try {
            if (Test-Path -LiteralPath $startPath -PathType Leaf) {
                $d.InitialDirectory = (Split-Path -LiteralPath $startPath -Parent)
                $d.FileName = (Split-Path -LiteralPath $startPath -Leaf)
            } elseif (Test-Path -LiteralPath $startPath -PathType Container) {
                $d.InitialDirectory = $startPath
            } else {
                $parent = Split-Path -LiteralPath $startPath -Parent
                if ($parent -and (Test-Path -LiteralPath $parent -PathType Container)) {
                    $d.InitialDirectory = $parent
                }
            }
        } catch { }
    }
    $dr = $d.ShowDialog($owner)
    if ($dr -eq [System.Windows.Forms.DialogResult]::OK -and $d.FileNames.Count -gt 0) {
        foreach ($fn in $d.FileNames) {
            [Console]::Out.WriteLine($fn)
        }
    }
    $owner.Close()
})
$null = $owner.ShowDialog()
"""
)


def _resolve_picked_paths(raw_stdout: str) -> list[str]:
    paths: list[str] = []
    for line in (raw_stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            paths.append(str(Path(line).expanduser().resolve()))
        except OSError:
            continue
    return paths


def _pick_files_windows_powershell(
    title: str,
    initial_dir: str | None = None,
) -> tuple[PickStatus, list[str]]:
    env = _browse_env(title, initial_dir, "AC_FILE_DLG_TITLE")
    try:
        r = _run_powershell(_PS_FILES_SCRIPT, env)
    except FileNotFoundError:
        return ("unavailable", [])
    except OSError:
        return ("unavailable", [])

    if r.returncode != 0:
        return ("unavailable", [])

    paths = _resolve_picked_paths(r.stdout or "")
    if not paths:
        return ("cancelled", [])
    return ("picked", paths)


def _pick_files_tkinter(
    title: str,
    initial_dir: str | None = None,
) -> tuple[PickStatus, list[str]]:
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception:  # pragma: no cover - env specific
        return ("unavailable", [])

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
        initial = (initial_dir or "").strip()
        initial_kw: dict = {}
        if initial:
            try:
                p = Path(initial).expanduser()
                if p.is_file():
                    initial_kw["initialdir"] = str(p.parent.resolve())
                    initial_kw["initialfile"] = p.name
                elif p.is_dir():
                    initial_kw["initialdir"] = str(p.resolve())
                elif p.parent.is_dir():
                    initial_kw["initialdir"] = str(p.parent.resolve())
            except OSError:
                pass
        picked = filedialog.askopenfilenames(
            title=title or "Choose files",
            filetypes=[("All files", "*.*")],
            **initial_kw,
        )
    finally:
        try:
            root.destroy()
        except tk.TclError:
            pass

    paths: list[str] = []
    for raw in picked or ():
        try:
            resolved = str(Path(raw).expanduser().resolve())
        except OSError:
            continue
        if resolved:
            paths.append(resolved)
    if not paths:
        return ("cancelled", [])
    return ("picked", paths)


def pick_files_host(
    title: str,
    initial_dir: str | None = None,
) -> tuple[PickStatus, list[str]]:
    """
    Open a native multi-select file dialog (blocks until closed).
    Returns (``picked``, absolute paths), (``cancelled``, []), or (``unavailable``, []).
    """
    with _browse_lock:
        if sys.platform == "win32":
            status, payload = _pick_files_windows_powershell(title, initial_dir)
            if status != "unavailable":
                return (status, payload)
            return _pick_files_tkinter(title, initial_dir)
        return _pick_files_tkinter(title, initial_dir)
