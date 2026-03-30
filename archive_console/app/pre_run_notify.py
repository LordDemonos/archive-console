"""Pre-run reminder window shared by web banner and tray notify tick."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from .schedule_times import fire_occurrence_key, next_monthly_fire_local
from .settings import ConsoleState, ScheduleEntry


def pre_run_reminder_banner(
    st: ConsoleState,
    *,
    now_unix: float | None = None,
    now_local: datetime | None = None,
) -> dict[str, Any]:
    """
    Same visibility rules as the Run tab pre-run banner: in
    [fire_unix − minutes_before×60, fire_unix), earliest enabled schedule,
    not snoozed, not acknowledged for this fire_key.
    """
    pr = st.pre_run_reminder
    if pr.minutes_before <= 0:
        return {"show": False, "message": "", "fire_key": ""}

    if now_local is None:
        if now_unix is None:
            now_unix = time.time()
        tz = datetime.now().astimezone().tzinfo
        now_local = datetime.fromtimestamp(now_unix, tz=tz)  # type: ignore[arg-type]
    elif now_unix is None:
        now_unix = now_local.timestamp()

    if pr.snooze_until_unix and now_unix < pr.snooze_until_unix:
        return {"show": False, "message": "", "fire_key": ""}

    best: tuple[ScheduleEntry, datetime] | None = None
    for s in st.schedules:
        if not s.enabled:
            continue
        nf = next_monthly_fire_local(s, now=now_local)
        if nf is None:
            continue
        if best is None or nf < best[1]:
            best = (s, nf)

    if best is None:
        return {"show": False, "message": "", "fire_key": ""}

    entry, fire_dt = best
    fire_unix = fire_dt.timestamp()
    start_win = fire_unix - pr.minutes_before * 60
    if now_unix < start_win or now_unix >= fire_unix:
        return {"show": False, "message": "", "fire_key": ""}

    fk = fire_occurrence_key(entry, fire_dt)
    if pr.acknowledged_fire_key == fk:
        return {"show": False, "message": "", "fire_key": ""}

    msg = (
        f"Scheduled run “{entry.job}” at {fire_dt.strftime('%Y-%m-%d %H:%M')} "
        f"(local machine time). {pr.minutes_before} min reminder."
    ).strip()
    if not msg:
        return {"show": False, "message": "", "fire_key": ""}
    return {"show": True, "message": msg, "fire_key": fk}
