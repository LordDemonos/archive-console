"""
Stage ``cookies.txt`` (source of truth) → ``cookies.run.txt`` before yt-dlp runs.

yt-dlp reads and write-backs ``--cookies`` on exit; isolating the run copy prevents
a degraded session from overwriting the operator export in ``cookies.txt``.
"""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

COOKIES_SOURCE_NAME = "cookies.txt"
COOKIES_RUN_NAME = "cookies.run.txt"
COOKIE_REFRESH_SENTINEL_NAME = ".archive_needs_cookies.txt"
ARCHIVE_COOKIES_NO_STAGE_ENV = "ARCHIVE_COOKIES_NO_STAGE"
ARCHIVE_COOKIES_NO_PER_VIDEO_SYNC_ENV = "ARCHIVE_COOKIES_NO_PER_VIDEO_SYNC"


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def source_cookies_path(script_dir: str) -> str:
    return os.path.join(script_dir, COOKIES_SOURCE_NAME)


def run_cookies_path(script_dir: str) -> str:
    return os.path.join(script_dir, COOKIES_RUN_NAME)


def run_cookies_rel() -> str:
    return COOKIES_RUN_NAME


def is_staged_cookie_path(path: str, script_dir: str) -> bool:
    if not path:
        return False
    norm = os.path.normpath(os.path.expanduser(path.strip()))
    run_abs = os.path.normpath(run_cookies_path(script_dir))
    if os.path.isabs(norm):
        return norm == run_abs
    return os.path.basename(norm) == COOKIES_RUN_NAME


def stage_cookies_for_ytdlp(
    script_dir: str,
    *,
    log: Callable[[str], None] | None = None,
) -> str | None:
    """
    Copy ``cookies.txt`` → ``cookies.run.txt`` when the source file exists.

    Returns the relative ``--cookies`` path (``cookies.run.txt``) or ``None`` when
    staging is skipped or the source file is missing.
    """
    if _env_truthy(ARCHIVE_COOKIES_NO_STAGE_ENV):
        return None
    src = source_cookies_path(script_dir)
    if not os.path.isfile(src):
        return None
    dst = run_cookies_path(script_dir)
    shutil.copy2(src, dst)
    if log:
        log(
            "[archive] Staged cookies for yt-dlp: "
            f"{COOKIES_SOURCE_NAME} → {COOKIES_RUN_NAME} "
            "(source unchanged; yt-dlp may write back to the run copy only)"
        )
    return COOKIES_RUN_NAME


def append_ytdlp_staged_cookies_argv(
    argv: list[str],
    script_dir: str,
    log: Callable[[str], None] | None = None,
) -> list[str]:
    """Return ``argv`` plus ``--cookies cookies.run.txt`` when staging succeeded."""
    rel = stage_cookies_for_ytdlp(script_dir, log=log)
    if not rel:
        return list(argv)
    out = list(argv)
    out.extend(["--cookies", rel])
    return out


def _file_mtime(path: str) -> float | None:
    try:
        return os.path.getmtime(path) if os.path.isfile(path) else None
    except OSError:
        return None


def reload_ytdlp_cookie_jar(
    ydl: Any, script_dir: str, *, browser: Any | None = "__use_params__"
) -> None:
    """Reload cookie jar from staged run file (after ``cookies.txt`` was updated)."""
    from yt_dlp.cookies import load_cookies

    run_abs = run_cookies_path(script_dir)
    if not os.path.isfile(run_abs):
        return
    if browser == "__use_params__":
        browser = ydl.params.get("cookiesfrombrowser")
    ydl.cookiejar = load_cookies(run_abs, browser, ydl)
    ydl.params["cookiefile"] = run_cookies_rel()


def sync_staged_cookies_from_source_if_newer(
    ydl: Any,
    script_dir: str,
    *,
    baseline_source_mtime: float | None,
    log: Callable[[str], None] | None = None,
) -> float | None:
    """
    When ``cookies.txt`` mtime is newer than *baseline*, copy to ``cookies.run.txt`` and
    reload yt-dlp's in-memory jar.

    Returns the source mtime after a successful sync, or ``None`` when unchanged.
    """
    src = source_cookies_path(script_dir)
    src_mtime = _file_mtime(src)
    if src_mtime is None:
        return None
    if baseline_source_mtime is not None and src_mtime <= baseline_source_mtime + 1e-6:
        return None
    if not stage_cookies_for_ytdlp(script_dir):
        return None
    reload_ytdlp_cookie_jar(ydl, script_dir, browser=None)  # file only; ignore cookies-from-browser
    if log:
        log(
            "[archive] Reloaded yt-dlp cookie jar from cookies.txt "
            f"(mid-run update → {COOKIES_RUN_NAME})"
        )
    return src_mtime


def cookie_refresh_sentinel_path(script_dir: str) -> str:
    return os.path.join(script_dir, COOKIE_REFRESH_SENTINEL_NAME)


def request_cookie_refresh(script_dir: str, *, reason: str = "cookie_auth") -> None:
    """Signal external tools (browser extension, Console) that cookies.txt must be replaced."""
    payload = {
        "requested_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "reason": (reason or "cookie_auth")[:200],
    }
    path = cookie_refresh_sentinel_path(script_dir)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f)
            f.write("\n")
    except OSError:
        pass


def clear_cookie_refresh_request(script_dir: str) -> None:
    path = cookie_refresh_sentinel_path(script_dir)
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
    except OSError:
        pass


def cookie_refresh_request_payload(script_dir: str) -> dict[str, Any] | None:
    path = cookie_refresh_sentinel_path(script_dir)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {"raw": data}
    except (OSError, json.JSONDecodeError):
        return {"requested_utc": None, "reason": "unreadable_sentinel"}


def cookie_refresh_requested(script_dir: str) -> bool:
    return os.path.isfile(cookie_refresh_sentinel_path(script_dir))


def request_cookie_preflight(script_dir: str, *, job: str = "") -> None:
    """Ask the browser extension to refresh cookies.txt before a yt-dlp job starts."""
    tag = (job or "ytdlp").strip()[:40]
    request_cookie_refresh(script_dir, reason=f"preflight_before_run:{tag}")


def cookie_request_is_preflight(payload: dict[str, Any] | None) -> bool:
    if not payload:
        return False
    reason = str(payload.get("reason") or "")
    return reason.startswith("preflight_before_run")


def looks_like_netscape_cookies(text: str) -> bool:
    body = (text or "").strip()
    if not body:
        return False
    head = body.splitlines()[0].lower()
    if "netscape" in head and "cookie" in head:
        return True
    for line in body.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        return len(s.split("\t")) >= 6
    return False
