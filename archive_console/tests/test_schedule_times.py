"""Next-run calendar math: clamped day-of-month, local wall times (fixed ``now`` in tests)."""

from __future__ import annotations

from datetime import date, datetime

from zoneinfo import ZoneInfo

from app.schedule_times import (
    effective_day_of_month,
    next_monthly_fire_local,
    occurrence_date_local,
)
from app.settings import ScheduleEntry


def test_effective_day_short_month() -> None:
    assert effective_day_of_month(2025, 2, 31) == 28
    assert effective_day_of_month(2024, 2, 31) == 29
    assert effective_day_of_month(2025, 4, 31) == 30


def test_occurrence_date_clamp_february() -> None:
    s = ScheduleEntry(enabled=True, day_of_month=31, hour=3, minute=0)
    assert occurrence_date_local(date(2025, 2, 1), s) == date(2025, 2, 28)
    assert occurrence_date_local(date(2025, 2, 28), s) == date(2025, 2, 28)


def test_next_monthly_jan31_to_february_clamp() -> None:
    s = ScheduleEntry(
        id="t",
        enabled=True,
        job="watch_later",
        day_of_month=31,
        hour=9,
        minute=0,
    )
    tz = ZoneInfo("UTC")
    now = datetime(2025, 1, 31, 15, 0, tzinfo=tz)
    nxt = next_monthly_fire_local(s, now=now)
    assert nxt is not None
    assert nxt.date() == date(2025, 2, 28)
    assert nxt.hour == 9 and nxt.minute == 0


def test_next_monthly_same_calendar_day_later_slot() -> None:
    s = ScheduleEntry(enabled=True, day_of_month=15, hour=10, minute=0)
    tz = ZoneInfo("UTC")
    now = datetime(2025, 3, 15, 8, 0, tzinfo=tz)
    nxt = next_monthly_fire_local(s, now=now)
    assert nxt is not None
    assert nxt.date() == date(2025, 3, 15)
    assert nxt.hour == 10 and nxt.minute == 0
