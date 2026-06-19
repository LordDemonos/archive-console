"""Gotify push notifications for batch runs (YouTube monthly + gallery-dl)."""

from __future__ import annotations

import json
import logging
import re
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from .gallery_sources import gallery_source_label
from .run_manager import RunPhase, RunState
from .settings import (
    ConsoleState,
    effective_gotify_app_token,
    gotify_is_configured,
    load_state,
    save_state,
)

logger = logging.getLogger(__name__)

NOTIFY_JOBS: frozenset[str] = frozenset(
    {"watch_later", "channels", "videos", "galleries"}
)
GotifyTrigger = Literal["scheduler", "manual"]
GotifyEvent = Literal["start", "complete"]

_LOG_TAIL_BYTES = 8192
_COOKIE_HINT_RE = re.compile(
    r"cookie|cookie-auth|sign[\s-]?in|http error 403|private|members only|\[archive\].*pause",
    re.IGNORECASE,
)
_GALLERY_HINT_RE = re.compile(
    r"AuthenticationError|401:|rate limit|wall-clock limit|"
    r"\[(?:reddit|twitter|instagram|deviantart|pixiv|tumblr)\]\[error\]",
    re.IGNORECASE,
)


def should_notify(
    st: ConsoleState,
    *,
    trigger: GotifyTrigger,
    event: GotifyEvent,
    job: str,
) -> bool:
    if job not in NOTIFY_JOBS:
        return False
    if not gotify_is_configured(st):
        return False
    if event == "start" and not st.gotify_notify_on_start:
        return False
    if event == "complete" and not st.gotify_notify_on_complete:
        return False
    if trigger == "scheduler" and not st.gotify_notify_scheduled:
        return False
    if trigger == "manual" and not st.gotify_notify_manual:
        return False
    return True


def _persist_gotify_failure(st: ConsoleState, msg: str) -> None:
    st2 = st.model_copy(
        update={
            "gotify_last_failure_unix": time.time(),
            "gotify_last_failure_message": msg[:200],
        },
    )
    save_state(st2)


def _clear_gotify_failure(st: ConsoleState) -> None:
    if (
        st.gotify_last_failure_unix <= 0
        and not (st.gotify_last_failure_message or "").strip()
    ):
        return
    save_state(
        st.model_copy(
            update={
                "gotify_last_failure_unix": 0.0,
                "gotify_last_failure_message": "",
            },
        ),
    )


def send_gotify_message(
    st: ConsoleState,
    *,
    title: str,
    message: str,
    priority: int | None = None,
    markdown: bool = True,
) -> bool:
    if not gotify_is_configured(st):
        return False
    base = (st.gotify_base_url or "").strip().rstrip("/")
    token = effective_gotify_app_token(st)
    pri = st.gotify_priority if priority is None else priority
    payload = {
        "title": (title or "Archive Console")[:200],
        "message": (message or "")[:4096],
        "priority": max(0, min(10, int(pri))),
        "markdown": bool(markdown),
    }
    body = json.dumps(payload).encode("utf-8")
    url = f"{base}/message?token={urllib.request.quote(token, safe='')}"
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-Gotify-Key": token,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            ok = 200 <= resp.status < 300
            if not ok:
                _persist_gotify_failure(st, f"HTTP {resp.status}")
            else:
                _clear_gotify_failure(st)
            return ok
    except urllib.error.HTTPError as e:
        if e.code == 401:
            msg = (
                "HTTP 401: invalid application token — use the token from "
                "Gotify → Apps (not a client token and not the server URL)"
            )
        else:
            msg = f"HTTP {e.code}: {e.reason or 'error'}"
        logger.warning("gotify POST failed: %s", msg)
        _persist_gotify_failure(st, msg)
        return False
    except (OSError, urllib.error.URLError, ValueError) as e:
        logger.warning("gotify POST failed: %s", e)
        _persist_gotify_failure(st, str(e)[:200] or type(e).__name__)
        return False


def _format_duration(started: float, ended: float | None) -> str:
    if not ended or ended <= started:
        return "—"
    sec = int(ended - started)
    if sec < 60:
        return f"{sec}s"
    m, s = divmod(sec, 60)
    if m < 60:
        return f"{m}m {s}s"
    h, m = divmod(m, 60)
    return f"{h}h {m}m {s}s"


def _local_time_str(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


def _trigger_label(run_meta: dict[str, Any]) -> str:
    trigger = (run_meta.get("trigger") or "manual").strip()
    if trigger == "scheduler":
        freq = (run_meta.get("schedule_frequency") or "").strip()
        if freq:
            return f"Scheduled **{freq}**"
        return "Scheduled"
    return "Manual"


def format_run_started_message(
    job: str,
    run_meta: dict[str, Any],
    *,
    run_id: str,
    started_unix: float,
    dry_run: bool = False,
) -> tuple[str, str]:
    title = f"Archive Console — {job} started"
    when = _local_time_str(started_unix)
    lines = [
        f"{_trigger_label(run_meta)} run started at **{when}** (local).",
        f"Run id: **{run_id}**",
    ]
    if dry_run:
        lines.append("**Dry run** — no downloads.")
    src = _gallery_source_line(run_meta)
    if src:
        lines.append(src)
    batch_total = int(run_meta.get("gallery_batch_total") or 0)
    if batch_total > 1:
        idx = int(run_meta.get("gallery_batch_index") or 0)
        lines.append(f"Saved-sources batch: **{idx}/{batch_total}**")
    return title, "\n".join(lines)


def _gallery_source_line(run_meta: dict[str, Any] | None) -> str | None:
    url = str((run_meta or {}).get("gallery_url") or "").strip()
    if not url:
        return None
    return f"Source: **{gallery_source_label(url)}**"


def extract_failure_hints(
    archive_root: Path,
    *,
    log_folder_rel: str | None,
    failure_detail: str | None,
    error_message: str | None = None,
    run_stats: dict[str, int] | None = None,
    job: str = "",
) -> str | None:
    parts: list[str] = []
    if failure_detail:
        parts.append(str(failure_detail).strip()[:400])
    if error_message:
        parts.append(str(error_message).strip()[:400])

    cookie_hint = False
    gallery_hint = False
    if log_folder_rel:
        log_path = (archive_root / Path(log_folder_rel) / "run.log").resolve()
        try:
            log_path.relative_to(archive_root.resolve())
            if log_path.is_file():
                size = log_path.stat().st_size
                with log_path.open("rb") as f:
                    if size > _LOG_TAIL_BYTES:
                        f.seek(-_LOG_TAIL_BYTES, 2)
                    tail = f.read().decode("utf-8", errors="replace")
                if _COOKIE_HINT_RE.search(tail):
                    cookie_hint = True
                    if not any("cookie" in p.lower() for p in parts):
                        parts.append("cookie / sign-in or auth issue in run log")
                if job == "galleries" and _GALLERY_HINT_RE.search(tail):
                    gallery_hint = True
                    if not any("gallery" in p.lower() for p in parts):
                        parts.append("gallery-dl auth or rate-limit issue in run log")
        except (OSError, ValueError):
            pass

    fail_n = int((run_stats or {}).get("fail") or 0)
    if job == "galleries" and gallery_hint:
        parts.append(
            "Check **Gallery options** (OAuth/cookies) and extractor rate limits."
        )
    elif cookie_hint:
        parts.append("Refresh **cookies.txt** for youtube.com before the next run.")
    elif fail_n > 0 and not parts:
        parts.append("See run log for per-item errors.")

    if not parts:
        return None
    return " | ".join(dict.fromkeys(parts))  # dedupe preserve order


def format_run_finished_message(
    finished: RunState,
    entry: dict[str, Any],
    *,
    failure_hints: str | None,
) -> tuple[str, str]:
    job = finished.job
    phase = finished.phase
    exit_code = finished.exit_code
    stats = entry.get("run_stats") if isinstance(entry.get("run_stats"), dict) else None
    duration = _format_duration(finished.started_unix, finished.ended_unix)
    log_rel = entry.get("log_folder_rel") or finished.log_folder_rel or "—"
    trigger = _trigger_label(finished.run_meta or {})

    if phase == RunPhase.success and exit_code == 0:
        title = f"Archive Console — {job} finished ✓"
        lines = [f"**Success** in **{duration}**", f"Trigger: {trigger}"]
    elif phase == RunPhase.canceled:
        title = f"Archive Console — {job} canceled"
        lines = [f"**Canceled** after **{duration}**", f"Trigger: {trigger}"]
    else:
        title = f"Archive Console — {job} failed"
        ec = exit_code if exit_code is not None else "?"
        lines = [f"**Failed** — exit code **{ec}** after **{duration}**", f"Trigger: {trigger}"]

    if stats:
        tried = stats.get("tried")
        saved = stats.get("saved")
        ok = stats.get("ok")
        fail = stats.get("fail")
        if all(isinstance(x, int) for x in (tried, saved, ok, fail)):
            lines.append(
                f"**Attempted:** {tried} | **Saved:** {saved} | **OK:** {ok} | **Failed:** {fail}"
            )

    src = _gallery_source_line(finished.run_meta)
    if src:
        lines.append(src)

    if failure_hints:
        lines.append(f"**Likely cause:** {failure_hints}")

    lines.append(f"Logs: `{log_rel}`")
    return title, "\n".join(lines)


def _run_trigger(run_meta: dict[str, Any] | None) -> GotifyTrigger:
    t = (run_meta or {}).get("trigger") or "manual"
    return "scheduler" if t == "scheduler" else "manual"


def format_gallery_batch_started_message(
    run: RunState,
    batch_meta: dict[str, Any],
) -> tuple[str, str]:
    total = int(
        batch_meta.get("batch_total")
        or batch_meta.get("gallery_batch_total")
        or 0
    )
    title = "Archive Console — galleries batch started"
    when = _local_time_str(run.started_unix)
    lines = [
        f"{_trigger_label(run.run_meta or {})} saved-sources crawl at **{when}** (local).",
        f"**{total}** source(s) queued (one Gotify summary when the batch finishes).",
        f"Run id: **{run.run_id}**",
    ]
    return title, "\n".join(lines)


def _source_result_icon(phase: str, exit_code: int | None) -> str:
    if phase == RunPhase.success.value and (exit_code is None or exit_code == 0):
        return "✓"
    if phase == RunPhase.canceled.value:
        return "⊘"
    return "✗"


def _format_source_result_line(row: dict[str, Any]) -> str:
    label = str(row.get("label") or "?")
    phase = str(row.get("phase") or "")
    exit_code = row.get("exit_code")
    dur = _format_duration(
        float(row.get("started_unix") or 0),
        row.get("ended_unix"),
    )
    icon = _source_result_icon(phase, exit_code)
    stats = row.get("run_stats") if isinstance(row.get("run_stats"), dict) else None
    stat_bits: list[str] = []
    if stats:
        saved = stats.get("saved")
        fail = stats.get("fail")
        if isinstance(saved, int):
            stat_bits.append(f"{saved} saved")
        if isinstance(fail, int) and fail > 0:
            stat_bits.append(f"{fail} failed")
    detail = str(row.get("failure_detail") or "").strip()
    if detail and icon != "✓":
        stat_bits.append(detail[:80])
    stat_txt = f" — {', '.join(stat_bits)}" if stat_bits else ""
    return f"- {icon} **{label}** ({dur}){stat_txt}"


def format_gallery_batch_finished_message(
    results: list[dict[str, Any]],
    batch_meta: dict[str, Any],
    *,
    partial_reason: str | None = None,
) -> tuple[str, str]:
    total = int(batch_meta.get("batch_total") or len(results))
    done = len(results)
    trigger = _trigger_label(batch_meta)
    started = min(
        (float(r.get("started_unix") or 0) for r in results if r.get("started_unix")),
        default=0.0,
    )
    ended = max(
        (float(r.get("ended_unix") or 0) for r in results if r.get("ended_unix")),
        default=0.0,
    )
    duration = _format_duration(started, ended if ended > started else None)

    ok_n = sum(
        1
        for r in results
        if r.get("phase") == RunPhase.success.value
        and (r.get("exit_code") in (None, 0))
    )
    bad_n = done - ok_n

    agg_saved = 0
    agg_fail = 0
    for r in results:
        st = r.get("run_stats")
        if isinstance(st, dict):
            if isinstance(st.get("saved"), int):
                agg_saved += int(st["saved"])
            if isinstance(st.get("fail"), int):
                agg_fail += int(st["fail"])

    if partial_reason:
        title = "Archive Console — galleries batch stopped"
    elif bad_n == 0:
        title = "Archive Console — galleries batch finished ✓"
    else:
        title = "Archive Console — galleries batch finished (issues)"

    lines = [
        f"**{done}/{total}** sources in **{duration}**",
        f"Trigger: {trigger}",
        f"**Totals:** {agg_saved} saved | {agg_fail} failed | {ok_n} ok / {bad_n} with issues",
    ]
    if partial_reason:
        lines.append(f"**Stopped early:** {partial_reason}")

    sorted_rows = sorted(results, key=lambda r: int(r.get("index") or 0))
    max_lines = 20
    for row in sorted_rows[:max_lines]:
        lines.append(_format_source_result_line(row))
    if len(sorted_rows) > max_lines:
        lines.append(f"- … and **{len(sorted_rows) - max_lines}** more source(s)")

    return title, "\n".join(lines)


def notify_gallery_batch_started(st: ConsoleState, run: RunState) -> None:
    trigger = _run_trigger(run.run_meta)
    if not should_notify(st, trigger=trigger, event="start", job="galleries"):
        return
    title, message = format_gallery_batch_started_message(run, run.run_meta or {})
    send_gotify_message(st, title=title, message=message)


def notify_gallery_batch_finished(
    st: ConsoleState,
    results: list[dict[str, Any]],
    batch_meta: dict[str, Any],
    *,
    partial_reason: str | None = None,
) -> None:
    if not results:
        return
    trigger = _run_trigger(batch_meta)
    if not should_notify(st, trigger=trigger, event="complete", job="galleries"):
        return
    title, message = format_gallery_batch_finished_message(
        results,
        batch_meta,
        partial_reason=partial_reason,
    )
    send_gotify_message(st, title=title, message=message)


def notify_run_started(st: ConsoleState, run: RunState) -> None:
    meta = run.run_meta or {}
    if run.job == "galleries" and int(meta.get("gallery_batch_total") or 0) > 1:
        if int(meta.get("gallery_batch_index") or 0) == 1:
            notify_gallery_batch_started(st, run)
        return
    trigger = _run_trigger(run.run_meta)
    if not should_notify(st, trigger=trigger, event="start", job=run.job):
        return
    title, message = format_run_started_message(
        run.job,
        run.run_meta or {},
        run_id=run.run_id,
        started_unix=run.started_unix,
        dry_run=run.dry_run,
    )
    send_gotify_message(st, title=title, message=message)


def notify_run_finished(
    st: ConsoleState,
    finished: RunState,
    entry: dict[str, Any],
    *,
    error_message: str | None = None,
) -> None:
    meta = finished.run_meta or {}
    batch_total = int(meta.get("gallery_batch_total") or 0)
    if finished.job == "galleries" and batch_total > 1:
        return
    trigger = _run_trigger(meta)
    if not should_notify(st, trigger=trigger, event="complete", job=finished.job):
        return
    root = Path(st.archive_root).expanduser().resolve()
    stats = entry.get("run_stats") if isinstance(entry.get("run_stats"), dict) else None
    hints = extract_failure_hints(
        root,
        log_folder_rel=entry.get("log_folder_rel") or finished.log_folder_rel,
        failure_detail=finished.failure_detail or entry.get("failure_detail"),
        error_message=error_message,
        run_stats=stats,
        job=finished.job,
    )
    title, message = format_run_finished_message(
        finished, entry, failure_hints=hints
    )
    send_gotify_message(st, title=title, message=message)


def send_test_message(st: ConsoleState) -> tuple[bool, str]:
    if not gotify_is_configured(st):
        return False, "Enable Gotify and set server URL + application token first."
    ok = send_gotify_message(
        st,
        title="Archive Console — Gotify test",
        message="**Test OK** — batch run notifications are configured (YouTube + galleries).",
    )
    if ok:
        return True, "Test message sent."
    st2 = load_state()
    msg = (st2.gotify_last_failure_message or "Gotify request failed").strip()
    return False, msg
