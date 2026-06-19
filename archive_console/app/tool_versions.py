"""Bounded subprocess checks for external CLI tools (read-only, no secrets)."""

from __future__ import annotations

import logging
import subprocess
import sys
from typing import Any

from .clip_export import resolve_ffmpeg_bin
from .gallery_cli import gallery_dl_exe_invocable, resolve_gallery_dl_exe
from .czkawka_runner import czkawka_invocable, resolve_czkawka_bin
from .gifski_convert import resolve_gifski_bin
from .settings import ConsoleState
from .supported_sites import resolve_ytdlp_version_argv

logger = logging.getLogger(__name__)

VERSION_TIMEOUT_SEC = 6.0
ERR_TAIL = 400
VERSION_STR_MAX = 200


def _tail(s: str, n: int = ERR_TAIL) -> str:
    t = (s or "").strip().replace("\r\n", "\n")
    if len(t) > n:
        return t[-n:]
    return t


def _first_line(stdout: str) -> str:
    line = (stdout or "").strip().splitlines()[0] if (stdout or "").strip() else ""
    if len(line) > VERSION_STR_MAX:
        line = line[:VERSION_STR_MAX] + "…"
    return line


def _run_version(
    argv: list[str],
    *,
    tool_id: str,
) -> tuple[bool, str | None, str | None]:
    """Return (ok, version_string, error_for_json)."""
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            timeout=VERSION_TIMEOUT_SEC,
            shell=False,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.TimeoutExpired:
        logger.warning(
            "tool_versions: timeout after %ss tool=%s argv0=%s",
            VERSION_TIMEOUT_SEC,
            tool_id,
            argv[0] if argv else "",
        )
        return False, None, "timeout"
    except FileNotFoundError:
        logger.warning(
            "tool_versions: executable not found tool=%s argv0=%s",
            tool_id,
            argv[0] if argv else "",
        )
        return False, None, "not found"
    except OSError as e:
        logger.warning(
            "tool_versions: spawn failed tool=%s err=%s",
            tool_id,
            e,
        )
        return False, None, "spawn error"

    out = proc.stdout or ""
    err = proc.stderr or ""
    if proc.returncode != 0:
        tail = _tail(err) or _tail(out)
        logger.warning(
            "tool_versions: non-zero exit tool=%s code=%s err_tail=%s",
            tool_id,
            proc.returncode,
            _tail(tail, 120),
        )
        detail = f"exit {proc.returncode}"
        if tail:
            detail = f"{detail}: {_tail(tail, 160)}"
        return False, None, detail

    ver = _first_line(out)
    if not ver:
        ver = _first_line(err)
    if not ver:
        return False, None, "empty output"
    return True, ver, None


def _python_version_row() -> dict[str, Any]:
    line = sys.version.split("\n", 1)[0].strip()
    if len(line) > VERSION_STR_MAX:
        line = line[:VERSION_STR_MAX] + "…"
    return {"ok": True, "tool": "python", "version": line, "error": None}


def build_tools_versions_payload(st: ConsoleState) -> dict[str, Any]:
    """One combined JSON payload for GET /api/tools/versions."""
    tools: list[dict[str, Any]] = [_python_version_row()]

    yargv = resolve_ytdlp_version_argv()
    if yargv:
        ok, ver, err = _run_version(yargv, tool_id="yt-dlp")
        tools.append(
            {
                "ok": ok,
                "tool": "yt-dlp",
                "version": ver,
                "error": err,
            }
        )

    gexe = resolve_gallery_dl_exe(None)
    if gallery_dl_exe_invocable(gexe):
        ok, ver, err = _run_version([gexe, "--version"], tool_id="gallery-dl")
        tools.append(
            {
                "ok": ok,
                "tool": "gallery-dl",
                "version": ver,
                "error": err,
            }
        )
    else:
        tools.append(
            {
                "ok": False,
                "tool": "gallery-dl",
                "version": None,
                "error": "not found",
            }
        )

    ff = resolve_ffmpeg_bin(st)
    ok, ver, err = _run_version([ff, "-version"], tool_id="ffmpeg")
    tools.append(
        {
            "ok": ok,
            "tool": "ffmpeg",
            "version": ver,
            "error": err,
        }
    )

    gski = resolve_gifski_bin(st)
    ok, ver, err = _run_version([gski, "--version"], tool_id="gifski")
    tools.append(
        {
            "ok": ok,
            "tool": "gifski",
            "version": ver,
            "error": err,
        }
    )

    czk = resolve_czkawka_bin(st)
    if czkawka_invocable(czk):
        ok, ver, err = _run_version([czk, "--version"], tool_id="czkawka")
        tools.append(
            {
                "ok": ok,
                "tool": "czkawka",
                "version": ver,
                "error": err,
            }
        )
    else:
        tools.append(
            {
                "ok": False,
                "tool": "czkawka",
                "version": None,
                "error": "not found",
            }
        )

    return {"tools": tools}

