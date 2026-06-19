"""Server-side batch runner for all saved gallery-dl sources (scheduled overnight crawl)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from .download_output import extra_env_for_galleries, validate_galleries_output_dir
from .gallery_sources import gallery_source_label, iter_gallery_sources_for_run
from .paths import PathNotAllowedError
from .run_manager import RunManager, RunState
from .settings import ConsoleState, load_state

logger = logging.getLogger(__name__)

GALLERY_SOURCES_SCHEDULE_JOB = "gallery_sources"
GALLERY_SOURCES_SCHEDULE_ID = "gallery_sources_crawl"


def scheduled_gallery_max_run_sec(st: ConsoleState) -> int:
    """Per-source wall clock for scheduled batches (0 = unlimited)."""
    return int(st.gallery_batch_run.scheduled_max_run_sec)

_batch_queue: list[tuple[str, str | None]] = []
_batch_total: int = 0
_batch_meta: dict[str, Any] = {}
_batch_results: list[dict[str, Any]] = []


def gallery_batch_active() -> bool:
    return _batch_total > 0


def is_gallery_batch_last_source(finished: RunState) -> bool:
    meta = finished.run_meta or {}
    idx = int(meta.get("gallery_batch_index") or 0)
    total = int(meta.get("gallery_batch_total") or 0)
    return total > 0 and idx >= total


def record_gallery_batch_source_result(
    finished: RunState,
    entry: dict[str, Any],
) -> None:
    """Append per-source stats for the batch Gotify summary."""
    global _batch_results
    if not gallery_batch_active() and not _batch_results:
        return
    meta = finished.run_meta or {}
    url = str(meta.get("gallery_url") or "").strip()
    _batch_results.append(
        {
            "index": int(meta.get("gallery_batch_index") or 0),
            "url": url,
            "label": gallery_source_label(url) if url else "?",
            "phase": finished.phase.value,
            "exit_code": finished.exit_code,
            "started_unix": finished.started_unix,
            "ended_unix": finished.ended_unix,
            "run_stats": entry.get("run_stats"),
            "log_folder_rel": entry.get("log_folder_rel") or finished.log_folder_rel,
            "failure_detail": finished.failure_detail or entry.get("failure_detail"),
        }
    )


def flush_gallery_batch_gotify(
    st: ConsoleState,
    *,
    partial_reason: str | None = None,
) -> None:
    """Send one Gotify summary for the saved-sources batch, then clear rows."""
    global _batch_results
    from .gotify_notify import notify_gallery_batch_finished

    if not _batch_results:
        return
    notify_gallery_batch_finished(
        st,
        list(_batch_results),
        dict(_batch_meta),
        partial_reason=partial_reason,
    )
    _batch_results = []


def _reset_batch() -> None:
    global _batch_queue, _batch_total, _batch_meta, _batch_results
    _batch_queue = []
    _batch_total = 0
    _batch_meta = {}
    _batch_results = []


def _gallery_extra_env(st: ConsoleState, root: Path, url: str, url_input: str | None) -> dict[str, str]:
    extra: dict[str, str] = {"ARCHIVE_GALLERY_URL": url}
    if url_input and url_input.rstrip("/") != url.rstrip("/"):
        extra["ARCHIVE_GALLERY_URL_INPUT"] = url_input
    validate_galleries_output_dir(root, st.download_dirs)
    extra.update(extra_env_for_galleries(root, st.download_dirs))
    max_sec = _batch_meta.get("max_run_sec")
    if max_sec:
        extra["ARCHIVE_GALLERY_MAX_RUN_SEC"] = str(int(max_sec))
    return extra


async def _start_gallery_url(
    mgr: RunManager,
    on_complete: Callable[[RunState | None], Awaitable[None]],
    st: ConsoleState,
    root: Path,
    url: str,
    url_input: str | None,
) -> bool:
    try:
        extra = _gallery_extra_env(st, root, url, url_input)
    except PathNotAllowedError as e:
        logger.warning("gallery source batch: invalid galleries output dir: %s", e)
        return False

    index = int(_batch_meta.get("batch_index") or 1)
    total = int(_batch_meta.get("batch_total") or 1)
    run_meta = {
        "trigger": _batch_meta.get("trigger") or "scheduler",
        "schedule_id": _batch_meta.get("schedule_id") or "",
        "schedule_frequency": _batch_meta.get("schedule_frequency") or "",
        "gallery_batch_index": index,
        "gallery_batch_total": total,
        "gallery_url": url,
    }
    if url_input and url_input.rstrip("/") != url.rstrip("/"):
        run_meta["gallery_url_input"] = url_input

    try:
        run = await mgr.start(
            "galleries",
            dry_run=False,
            skip_ytdlp_update=True,
            skip_pip_update=True,
            on_complete=on_complete,
            extra_env=extra,
            run_meta=run_meta,
        )
    except RuntimeError as e:
        logger.info("gallery source batch: did not start: %s", e)
        return False
    except FileNotFoundError as e:
        logger.warning("gallery source batch: %s", e)
        return False
    if index == 1:
        from .gotify_notify import notify_gallery_batch_started

        await asyncio.to_thread(notify_gallery_batch_started, st, run)
    logger.info(
        "gallery source batch: started %s/%s url=%s",
        index,
        total,
        url[:80],
    )
    return True


async def start_gallery_sources_batch(
    mgr: RunManager,
    on_complete: Callable[[RunState | None], Awaitable[None]],
    *,
    st: ConsoleState,
    schedule_id: str = "",
    schedule_frequency: str = "",
    trigger: str = "scheduler",
) -> bool:
    """Run every saved gallery source sequentially. Returns True if the first run started."""
    global _batch_queue, _batch_total, _batch_meta

    if gallery_batch_active():
        logger.debug("gallery source batch: already active")
        return False

    root = Path(st.archive_root).expanduser().resolve()
    deprioritize_twitter = trigger == "scheduler"
    sources = iter_gallery_sources_for_run(
        root,
        deprioritize_twitter=deprioritize_twitter,
    )
    if not sources:
        logger.info("gallery source batch: no saved sources — skip")
        return False

    _batch_total = len(sources)
    _batch_queue = sources[1:]
    _batch_meta = {
        "trigger": trigger,
        "schedule_id": schedule_id,
        "schedule_frequency": schedule_frequency,
        "batch_index": 1,
        "batch_total": _batch_total,
        "max_run_sec": scheduled_gallery_max_run_sec(st) if trigger == "scheduler" else 0,
    }

    url, url_input = sources[0]
    started = await _start_gallery_url(mgr, on_complete, st, root, url, url_input)
    if not started:
        _reset_batch()
    return started


async def stop_gallery_source_batch_after_user_cancel(
    finished: RunState,
) -> None:
    """After manual stop, drop remaining queued sources (do not auto-continue)."""
    global _batch_queue, _batch_meta

    if not gallery_batch_active():
        return
    meta = finished.run_meta or {}
    if not meta.get("gallery_batch_total"):
        return

    idx = int(meta.get("gallery_batch_index") or 0)
    total = int(meta.get("gallery_batch_total") or 0)
    remaining = len(_batch_queue)
    logger.info(
        "gallery source batch: user canceled at %s/%s — dropping %s queued source(s)",
        idx,
        total,
        remaining,
    )
    st = load_state()
    await asyncio.to_thread(
        flush_gallery_batch_gotify,
        st,
        partial_reason=f"stopped by user at source {idx}/{total}",
    )
    _reset_batch()


async def continue_gallery_source_batch_if_any(
    mgr: RunManager,
    on_complete: Callable[[RunState | None], Awaitable[None]],
    *,
    finished: RunState | None = None,
) -> None:
    """After a galleries run completes, start the next saved source if a batch is active."""
    global _batch_queue, _batch_meta

    if not gallery_batch_active():
        return
    if finished is not None and not finished.run_meta.get("gallery_batch_total"):
        return

    status = await mgr.status()
    if status.get("phase") == "running":
        return

    if not _batch_queue:
        logger.info("gallery source batch: finished all %s sources", _batch_total)
        _reset_batch()
        return

    st = load_state()
    root = Path(st.archive_root).expanduser().resolve()
    url, url_input = _batch_queue.pop(0)
    done = _batch_total - len(_batch_queue)
    _batch_meta["batch_index"] = done
    started = await _start_gallery_url(mgr, on_complete, st, root, url, url_input)
    if not started:
        logger.warning(
            "gallery source batch: stopped at %s/%s (could not start next run)",
            done,
            _batch_total,
        )
        await asyncio.to_thread(
            flush_gallery_batch_gotify,
            st,
            partial_reason=f"could not start source {done}/{_batch_total}",
        )
        _reset_batch()
