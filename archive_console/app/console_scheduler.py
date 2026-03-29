"""In-process monthly scheduler when ``features.scheduler_enabled``."""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .download_output import extra_env_for_job
from .paths import PathNotAllowedError
from .run_manager import RunManager, RunState
from .schedule_times import occurrence_date_local
from .settings import load_state

logger = logging.getLogger(__name__)

_fired_today: set[str] = set()
_prune_at = 0.0


def _prune_keys() -> None:
    global _prune_at
    t = time.time()
    if t - _prune_at < 7200:
        return
    _prune_at = t
    if len(_fired_today) > 400:
        _fired_today.clear()


async def _tick(
    get_manager_fn: Callable[[], RunManager],
    on_complete_fn: Callable[[RunState | None], Awaitable[None]],
) -> None:
    st = load_state()
    if not st.features.scheduler_enabled:
        return

    from datetime import datetime

    tz = datetime.now().astimezone().tzinfo
    now = datetime.now(tz)  # type: ignore[arg-type]
    today = now.date()

    mgr = get_manager_fn()
    status = await mgr.status()
    if status.get("phase") == "running":
        logger.debug("scheduler: skip tick — job still running (no overlap)")
        return

    for s in st.schedules:
        if not s.enabled or s.job not in ("watch_later", "channels", "videos"):
            continue
        if occurrence_date_local(today, s) != today:
            continue
        if now.hour != s.hour or now.minute != s.minute:
            continue
        key = f"{s.id or s.job}:{today.isoformat()}:{s.hour}:{s.minute}"
        if key in _fired_today:
            continue
        _fired_today.add(key)
        _prune_keys()
        logger.info("scheduler: starting job %s (schedule id=%s)", s.job, s.id or "")
        root = Path(st.archive_root).expanduser().resolve()
        try:
            sched_extra = extra_env_for_job(root, st.download_dirs, s.job)
        except PathNotAllowedError:
            logger.warning(
                "scheduler: invalid download_dirs in state; skip scheduled job %s",
                s.job,
            )
            continue
        try:
            await mgr.start(
                s.job,
                dry_run=False,
                skip_ytdlp_update=True,
                skip_pip_update=True,
                on_complete=on_complete_fn,
                extra_env=sched_extra or None,
            )
        except RuntimeError as e:
            logger.info("scheduler: did not start %s: %s", s.job, e)
        except FileNotFoundError as e:
            logger.warning("scheduler: %s", e)


def start_background_scheduler(
    get_manager_fn: Callable[[], RunManager],
    on_complete_fn: Callable[[RunState | None], Awaitable[None]],
) -> Callable[[], Awaitable[None]]:
    sched = AsyncIOScheduler()

    async def job() -> None:
        try:
            await _tick(get_manager_fn, on_complete_fn)
        except Exception:
            logger.exception("scheduler tick failed")

    sched.add_job(
        job,
        "interval",
        seconds=30,
        id="archive_console_monthly",
        coalesce=True,
        max_instances=1,
    )
    sched.start()
    logger.info("scheduler backend started (30s tick; TZ = local machine)")

    async def shutdown() -> None:
        sched.shutdown(wait=False)
        logger.info("scheduler backend stopped")

    return shutdown
