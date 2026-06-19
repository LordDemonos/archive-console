"""Wait for Firefox extension to refresh cookies.txt before yt-dlp batch jobs start."""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

# archive_cookies.py lives in the scripts root (two levels up from app/). Ensure it is
# importable regardless of the launcher's working directory (e.g. the tray spawns uvicorn
# with cwd=archive_console, so the scripts root is otherwise not on sys.path).
_SCRIPTS_ROOT = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from archive_cookies import (  # noqa: E402
    COOKIES_SOURCE_NAME,
    clear_cookie_refresh_request,
    cookie_refresh_request_payload,
    cookie_refresh_requested,
    cookie_request_is_preflight,
    request_cookie_preflight,
)

if TYPE_CHECKING:
    from .run_manager import RunBroadcaster

YTDLP_COOKIE_JOBS = frozenset({"watch_later", "channels", "videos", "oneoff"})


class CookiePreflightTimeoutError(RuntimeError):
    """Extension did not refresh cookies.txt before the wait deadline."""


def ytdlp_job_needs_cookies(job: str) -> bool:
    return job in YTDLP_COOKIE_JOBS


def _cookies_mtime(path: Path) -> float | None:
    try:
        return path.stat().st_mtime if path.is_file() else None
    except OSError:
        return None


async def await_extension_cookie_preflight(
    archive_root: Path,
    *,
    job: str,
    timeout_sec: float,
    poll_sec: float = 2.0,
    broadcaster: RunBroadcaster | None = None,
) -> tuple[bool, str]:
    """
    Signal preflight, then wait until the extension PUT clears the sentinel or bumps mtime.

    Returns (ok, detail_message).
    """
    root = archive_root.resolve()
    ck = root / COOKIES_SOURCE_NAME
    script_dir = str(root)
    baseline = _cookies_mtime(ck)
    request_cookie_preflight(script_dir, job=job)

    async def _publish(text: str) -> None:
        if broadcaster is not None:
            await broadcaster.publish({"type": "line", "text": text})

    await _publish(
        f"[console] Preflight: waiting for Firefox extension to refresh {COOKIES_SOURCE_NAME} "
        f"(job={job}, up to {int(timeout_sec)}s). Keep Firefox open with a youtube.com tab."
    )

    deadline = time.monotonic() + max(10.0, float(timeout_sec))
    step = max(0.5, min(float(poll_sec), 15.0))

    while time.monotonic() < deadline:
        payload = cookie_refresh_request_payload(script_dir)
        if not cookie_refresh_requested(script_dir):
            await _publish(
                f"[console] Preflight: {COOKIES_SOURCE_NAME} updated by extension — starting yt-dlp."
            )
            return True, "cookies refreshed"

        cur = _cookies_mtime(ck)
        if cur is not None and (
            baseline is None or cur > baseline + 1e-6
        ):
            if payload and cookie_request_is_preflight(payload):
                clear_cookie_refresh_request(script_dir)
            await _publish(
                f"[console] Preflight: {COOKIES_SOURCE_NAME} mtime increased — starting yt-dlp."
            )
            return True, "cookies.txt mtime increased"

        await asyncio.sleep(step)

    await _publish(
        f"[console] Preflight: timed out after {int(timeout_sec)}s — "
        "enable extension auto-poll and keep a YouTube tab open, or export cookies manually."
    )
    clear_cookie_refresh_request(script_dir)
    return False, f"cookie preflight timed out after {int(timeout_sec)}s"
