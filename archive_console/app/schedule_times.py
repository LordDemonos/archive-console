"""Monthly schedule times: local clock, day clamped to last valid day of month."""

from __future__ import annotations

import calendar
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from .settings import ScheduleEntry


def effective_day_of_month(year: int, month: int, desired_dom: int) -> int:
    """``min(desired_dom, last day of month)`` — Jan 31 in February → Feb 28/29."""
    last = calendar.monthrange(year, month)[1]
    return min(int(desired_dom), last)


def _local_tz():
    """IANA zone when ``TZ`` is set; else system local offset (execution TZ)."""
    import os

    name = (os.environ.get("TZ") or "").strip()
    if name:
        try:
            return ZoneInfo(name)
        except Exception:
            pass
    z = datetime.now().astimezone().tzinfo
    return z if z is not None else ZoneInfo("UTC")


def occurrence_date_local(d: date, entry: ScheduleEntry) -> date:
    """Calendar day within month ``d`` matching this schedule's clamped day-of-month."""
    ed = effective_day_of_month(d.year, d.month, entry.day_of_month)
    return date(d.year, d.month, ed)


def next_monthly_fire_local(
    entry: ScheduleEntry,
    *,
    now: datetime | None = None,
) -> datetime | None:
    """Next local wall-clock run at entry hour/minute on the effective DOM (on or after now)."""
    if not entry.enabled:
        return None
    if now is None:
        tz = _local_tz()
        now = datetime.now(tz)
    else:
        tz = now.tzinfo or _local_tz()
        if now.tzinfo is None:
            now = now.replace(tzinfo=tz)
    h, m = entry.hour, entry.minute
    for add in range(0, 400):
        d0 = now.date() + timedelta(days=add)
        occ = occurrence_date_local(d0, entry)
        if d0 != occ:
            continue
        cand = datetime.combine(occ, time(h, m), tzinfo=tz)
        if cand >= now:
            return cand
    return None


def next_run_iso_local(entry: ScheduleEntry) -> str | None:
    n = next_monthly_fire_local(entry)
    return n.isoformat() if n else None


def fire_occurrence_key(entry: ScheduleEntry, fire: datetime) -> str:
    """Stable id for ack/snooze for one scheduled wall time."""
    eid = entry.id or entry.job
    return f"{eid}:{fire.date().isoformat()}:{entry.hour}:{entry.minute}"
