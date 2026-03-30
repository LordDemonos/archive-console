"""Background tick: tray balloon during pre-run window (optional feature flag)."""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from collections.abc import Awaitable, Callable
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .pre_run_notify import pre_run_reminder_banner
from .settings import ConsoleState, effective_tray_notify_port, load_state, save_state

logger = logging.getLogger(__name__)

_tray_fired_keys: set[str] = set()
_prune_at = 0.0


def _prune_keys() -> None:
    global _prune_at
    t = time.time()
    if t - _prune_at < 7200:
        return
    _prune_at = t
    if len(_tray_fired_keys) > 400:
        _tray_fired_keys.clear()


def _post_tray_notify(port: int, title: str, body: str) -> bool:
    payload = json.dumps({"title": title, "body": body}).encode("utf-8")
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/notify",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            return 200 <= resp.status < 300
    except (OSError, urllib.error.URLError, ValueError) as e:
        logger.warning("tray notify POST failed: %s", e)
        return False


def _failure_message(err: BaseException) -> str:
    s = str(err).strip() or type(err).__name__
    return s[:200]


def _persist_tray_failure(st: ConsoleState, msg: str) -> None:
    st2 = st.model_copy(
        update={
            "tray_notify_last_failure_unix": time.time(),
            "tray_notify_last_failure_message": msg[:200],
        },
    )
    save_state(st2)


def _clear_tray_failure(st: ConsoleState) -> None:
    if (
        st.tray_notify_last_failure_unix <= 0
        and not (st.tray_notify_last_failure_message or "").strip()
    ):
        return
    save_state(
        st.model_copy(
            update={
                "tray_notify_last_failure_unix": 0.0,
                "tray_notify_last_failure_message": "",
            },
        ),
    )


async def tray_notify_tick() -> None:
    st = load_state()
    if not st.features.tray_notify_before_schedule:
        return

    banner = pre_run_reminder_banner(st)
    if not banner.get("show"):
        return

    fk = str(banner.get("fire_key") or "")
    if not fk or fk in _tray_fired_keys:
        return

    port = effective_tray_notify_port(st)
    title = "Archive Console — refresh cookies"
    body = (
        "Scheduled run is coming soon. Export fresh cookies for youtube.com into "
        "cookies.txt before it starts. "
        + str(banner.get("message") or "")
    )
    body = body.strip()[:512]

    import asyncio

    ok = await asyncio.to_thread(_post_tray_notify, port, title, body)
    _tray_fired_keys.add(fk)
    _prune_keys()
    if ok:
        _clear_tray_failure(st)
        return
    _persist_tray_failure(st, f"tray unreachable on port {port}")


def start_tray_notify_scheduler() -> Callable[[], Awaitable[None]]:
    sched = AsyncIOScheduler()

    async def job() -> None:
        try:
            await tray_notify_tick()
        except Exception:
            logger.exception("tray notify tick failed")

    sched.add_job(
        job,
        "interval",
        seconds=30,
        id="archive_console_tray_notify",
        coalesce=True,
        max_instances=1,
    )
    sched.start()
    logger.info("tray notify tick started (30s)")

    async def shutdown() -> None:
        sched.shutdown(wait=False)
        logger.info("tray notify tick stopped")

    return shutdown
