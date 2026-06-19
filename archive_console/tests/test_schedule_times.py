"""Next-run calendar math: daily, weekly, monthly — local wall times (fixed ``now`` in tests)."""

from __future__ import annotations

from datetime import date, datetime

from zoneinfo import ZoneInfo

from app.schedule_times import (
    effective_day_of_month,
    next_fire_local,
    next_monthly_fire_local,
    occurrence_date_local,
    schedule_matches_moment,
)
from app.settings import ScheduleEntry


def test_effective_day_short_month() -> None:
    assert effective_day_of_month(2025, 2, 31) == 28
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
        frequency="monthly",
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
    s = ScheduleEntry(
        enabled=True,
        frequency="monthly",
        day_of_month=15,
        hour=10,
        minute=0,
    )
    tz = ZoneInfo("UTC")
    now = datetime(2025, 3, 15, 8, 0, tzinfo=tz)
    nxt = next_monthly_fire_local(s, now=now)
    assert nxt is not None
    assert nxt.date() == date(2025, 3, 15)
    assert nxt.hour == 10 and nxt.minute == 0


def test_daily_next_fire_same_day() -> None:
    s = ScheduleEntry(enabled=True, frequency="daily", hour=2, minute=0)
    tz = ZoneInfo("UTC")
    now = datetime(2025, 5, 25, 1, 30, tzinfo=tz)
    nxt = next_fire_local(s, now=now)
    assert nxt is not None
    assert nxt.date() == date(2025, 5, 25)
    assert nxt.hour == 2 and nxt.minute == 0


def test_daily_next_fire_rolls_to_tomorrow() -> None:
    s = ScheduleEntry(enabled=True, frequency="daily", hour=2, minute=0)
    tz = ZoneInfo("UTC")
    now = datetime(2025, 5, 25, 2, 5, tzinfo=tz)
    nxt = next_fire_local(s, now=now)
    assert nxt is not None
    assert nxt.date() == date(2025, 5, 26)
    assert nxt.hour == 2 and nxt.minute == 0


def test_weekly_next_fire_same_week() -> None:
    # 2025-05-25 is a Sunday (weekday 6)
    s = ScheduleEntry(enabled=True, frequency="weekly", day_of_week=6, hour=2, minute=0)
    tz = ZoneInfo("UTC")
    now = datetime(2025, 5, 25, 1, 0, tzinfo=tz)
    nxt = next_fire_local(s, now=now)
    assert nxt is not None
    assert nxt.date() == date(2025, 5, 25)
    assert nxt.weekday() == 6


def test_weekly_next_fire_skips_to_next_week() -> None:
    s = ScheduleEntry(enabled=True, frequency="weekly", day_of_week=0, hour=9, minute=0)
    tz = ZoneInfo("UTC")
    now = datetime(2025, 5, 25, 10, 0, tzinfo=tz)  # Sunday
    nxt = next_fire_local(s, now=now)
    assert nxt is not None
    assert nxt.weekday() == 0
    assert nxt.date() == date(2025, 5, 26)  # Monday


def test_schedule_matches_moment_daily() -> None:
    s = ScheduleEntry(enabled=True, frequency="daily", hour=2, minute=0)
    tz = ZoneInfo("UTC")
    assert schedule_matches_moment(datetime(2025, 5, 25, 2, 0, tzinfo=tz), s)
    assert not schedule_matches_moment(datetime(2025, 5, 25, 2, 1, tzinfo=tz), s)
    assert not schedule_matches_moment(
        datetime(2025, 5, 25, 2, 0, tzinfo=tz),
        s.model_copy(update={"enabled": False}),
    )


def test_schedule_matches_moment_weekly() -> None:
    s = ScheduleEntry(enabled=True, frequency="weekly", day_of_week=6, hour=2, minute=0)
    tz = ZoneInfo("UTC")
    assert schedule_matches_moment(datetime(2025, 5, 25, 2, 0, tzinfo=tz), s)
    assert not schedule_matches_moment(datetime(2025, 5, 26, 2, 0, tzinfo=tz), s)


def test_legacy_schedule_defaults_to_monthly() -> None:
    s = ScheduleEntry(enabled=True, day_of_month=27, hour=1, minute=0)
    assert s.frequency == "monthly"
