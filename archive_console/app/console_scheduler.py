"""In-process scheduler when ``features.scheduler_enabled``."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .download_output import extra_env_for_job, extra_env_for_ytdlp_batch
from .gallery_source_batch import (
    GALLERY_SOURCES_SCHEDULE_JOB,
    start_gallery_sources_batch,
)
from .paths import PathNotAllowedError
from .cookie_preflight import CookiePreflightTimeoutError
from .run_manager import BATCH_NAMES, RunManager, RunState
from .schedule_times import fire_occurrence_key, schedule_matches_moment
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

    mgr = get_manager_fn()
    status = await mgr.status()
    if status.get("phase") == "running":
        logger.debug("scheduler: skip tick — job still running (no overlap)")
        return

    for s in st.schedules:
        if not s.enabled:
            continue
        if not schedule_matches_moment(now, s):
            continue
        key = fire_occurrence_key(s, now.replace(second=0, microsecond=0))
        if key in _fired_today:
            continue

        if s.job == GALLERY_SOURCES_SCHEDULE_JOB:
            _fired_today.add(key)
            _prune_keys()
            logger.info(
                "scheduler: starting gallery saved-sources batch (schedule id=%s)",
                s.id or "",
            )
            try:
                await start_gallery_sources_batch(
                    mgr,
                    on_complete_fn,
                    st=st,
                    schedule_id=s.id or "",
                    schedule_frequency=s.frequency,
                    trigger="scheduler",
                )
            except RuntimeError as e:
                logger.info("scheduler: gallery batch did not start: %s", e)
            except FileNotFoundError as e:
                logger.warning("scheduler: gallery batch %s", e)
            continue

        if s.job not in BATCH_NAMES:
            continue

        _fired_today.add(key)
        _prune_keys()
        logger.info("scheduler: starting job %s (schedule id=%s)", s.job, s.id or "")
        root = Path(st.archive_root).expanduser().resolve()
        try:
            sched_extra = extra_env_for_job(root, st.download_dirs, s.job)
            sched_extra.update(extra_env_for_ytdlp_batch(st.ytdlp_batch_run))
        except PathNotAllowedError:
            logger.warning(
                "scheduler: invalid download_dirs in state; skip scheduled job %s",
                s.job,
            )
            continue
        try:
            ybr = st.ytdlp_batch_run
            run_state = await mgr.start(
                s.job,
                dry_run=False,
                skip_ytdlp_update=True,
                skip_pip_update=True,
                on_complete=on_complete_fn,
                extra_env=sched_extra or None,
                run_meta={
                    "trigger": "scheduler",
                    "schedule_id": s.id,
                    "schedule_frequency": s.frequency,
                },
                preflight_via_extension=ybr.preflight_via_extension,
                preflight_wait_sec=ybr.preflight_wait_sec,
            )
        except RuntimeError as e:
            logger.info("scheduler: did not start %s: %s", s.job, e)
        except FileNotFoundError as e:
            logger.warning("scheduler: %s", e)
        except CookiePreflightTimeoutError as e:
            logger.warning("scheduler: cookie preflight timed out for %s: %s", s.job, e)
        else:
            from .gotify_notify import notify_run_started

            st_g = load_state()
            await asyncio.to_thread(notify_run_started, st_g, run_state)


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
