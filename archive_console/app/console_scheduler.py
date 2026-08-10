"""In-process scheduler when ``features.scheduler_enabled``."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import datetime, time as dt_time
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
from .schedule_times import fire_occurrence_key, schedule_due_now
from .settings import ConsoleState, ScheduleEntry, load_state

logger = logging.getLogger(__name__)

# Occurrence keys successfully started (or intentionally consumed) this process life.
_fired_today: set[str] = set()
# After a failed start (preflight / busy), wait before retrying the same occurrence.
_backoff_until: dict[str, float] = {}
_prune_at = 0.0

_PREFLIGHT_BACKOFF_SEC = 300.0
_BUSY_BACKOFF_SEC = 60.0


def _prune_keys() -> None:
    global _prune_at
    t = time.time()
    if t - _prune_at < 7200:
        return
    _prune_at = t
    if len(_fired_today) > 400:
        _fired_today.clear()
    # Drop expired backoff entries
    expired = [k for k, until in _backoff_until.items() if until <= t]
    for k in expired:
        _backoff_until.pop(k, None)


def _mark_fired(key: str) -> None:
    _fired_today.add(key)
    _backoff_until.pop(key, None)
    _prune_keys()


def _set_backoff(key: str, seconds: float) -> None:
    _backoff_until[key] = time.time() + max(1.0, seconds)
    _prune_keys()


def _history_job_name(schedule_job: str) -> str:
    if schedule_job == GALLERY_SOURCES_SCHEDULE_JOB:
        return "galleries"
    return schedule_job


def history_covers_occurrence(
    st: ConsoleState,
    entry: ScheduleEntry,
    now: datetime,
) -> bool:
    """True if run_history already has a run covering this schedule occurrence."""
    from .schedule_times import interval_slot_start, interval_step

    hist_job = _history_job_name(entry.job)
    tz = now.tzinfo
    freq = getattr(entry, "frequency", None) or "monthly"
    if freq == "interval":
        slot = interval_slot_start(now, entry)
        window_end = slot + interval_step(entry)
    else:
        slot = datetime.combine(
            now.date(),
            dt_time(entry.hour, entry.minute),
            tzinfo=tz,
        )
        window_end = None
    for row in st.run_history:
        if not isinstance(row, dict):
            continue
        if row.get("job") != hist_job:
            continue
        try:
            started = float(row.get("started_unix") or 0.0)
        except (TypeError, ValueError):
            continue
        if started <= 0:
            continue
        started_dt = datetime.fromtimestamp(started, tz=tz)
        if freq == "interval":
            if slot <= started_dt < window_end:
                return True
        elif started_dt >= slot:
            return True
    return False


async def _notify_scheduler_start_failed(job: str, detail: str) -> None:
    """Best-effort Gotify when a scheduled start fails before a run exists."""
    try:
        from .gotify_notify import send_gotify_message
        from .settings import gotify_is_configured

        st = load_state()
        if not gotify_is_configured(st) or not st.gotify_notify_scheduled:
            return
        await asyncio.to_thread(
            send_gotify_message,
            st,
            title=f"Archive schedule: {job} did not start",
            message=detail[:1500],
        )
    except Exception:
        logger.exception("scheduler: gotify notify for start failure failed")


async def _tick(
    get_manager_fn: Callable[[], RunManager],
    on_complete_fn: Callable[[RunState | None], Awaitable[None]],
) -> None:
    st = load_state()
    if not st.features.scheduler_enabled:
        return

    tz = datetime.now().astimezone().tzinfo
    now = datetime.now(tz)  # type: ignore[arg-type]

    mgr = get_manager_fn()
    status = await mgr.status()
    if status.get("phase") == "running":
        logger.debug("scheduler: skip tick — job still running (no overlap)")
        return

    now_mono = time.time()
    for s in st.schedules:
        if not s.enabled:
            continue
        if not schedule_due_now(now, s):
            continue
        key = fire_occurrence_key(s, now.replace(second=0, microsecond=0))
        if key in _fired_today:
            continue
        if history_covers_occurrence(st, s, now):
            logger.info(
                "scheduler: occurrence already covered by run_history (%s) — mark fired",
                s.job,
            )
            _mark_fired(key)
            continue
        if now_mono < _backoff_until.get(key, 0.0):
            continue

        if s.job == GALLERY_SOURCES_SCHEDULE_JOB:
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
                _set_backoff(key, _BUSY_BACKOFF_SEC)
            except FileNotFoundError as e:
                logger.warning("scheduler: gallery batch %s", e)
                _set_backoff(key, _BUSY_BACKOFF_SEC)
                await _notify_scheduler_start_failed("galleries", str(e))
            else:
                _mark_fired(key)
            continue

        if s.job not in BATCH_NAMES:
            continue

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
            _set_backoff(key, _BUSY_BACKOFF_SEC)
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
            _set_backoff(key, _BUSY_BACKOFF_SEC)
        except FileNotFoundError as e:
            logger.warning("scheduler: %s", e)
            _set_backoff(key, _BUSY_BACKOFF_SEC)
            await _notify_scheduler_start_failed(s.job, str(e))
        except CookiePreflightTimeoutError as e:
            logger.warning("scheduler: cookie preflight timed out for %s: %s", s.job, e)
            _set_backoff(key, _PREFLIGHT_BACKOFF_SEC)
            await _notify_scheduler_start_failed(
                s.job,
                f"{e} — will retry in {int(_PREFLIGHT_BACKOFF_SEC // 60)} min "
                "(keep Firefox open with a youtube.com tab / extension auto-poll).",
            )
        else:
            _mark_fired(key)
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
    logger.info(
        "scheduler backend started (30s tick; TZ = local machine; same-day catch-up on)"
    )

    async def shutdown() -> None:
        sched.shutdown(wait=False)
        logger.info("scheduler backend stopped")

    return shutdown
