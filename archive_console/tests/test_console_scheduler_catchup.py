"""Scheduler catch-up helpers: history covers occurrence."""

from __future__ import annotations

from datetime import datetime

from zoneinfo import ZoneInfo

from app.console_scheduler import history_covers_occurrence
from app.settings import ConsoleState, ScheduleEntry


def test_history_covers_occurrence_same_day_after_slot() -> None:
    tz = ZoneInfo("UTC")
    now = datetime(2026, 7, 16, 15, 0, tzinfo=tz)
    entry = ScheduleEntry(
        id="sch",
        job="watch_later",
        frequency="daily",
        hour=3,
        minute=0,
        enabled=True,
    )
    # 2026-07-16 13:21 UTC ≈ manual run after 03:00
    started = datetime(2026, 7, 16, 13, 21, tzinfo=tz).timestamp()
    st = ConsoleState(
        run_history=[{"job": "watch_later", "started_unix": started}],
    )
    assert history_covers_occurrence(st, entry, now) is True


def test_history_covers_occurrence_ignores_earlier_day() -> None:
    tz = ZoneInfo("UTC")
    now = datetime(2026, 7, 16, 15, 0, tzinfo=tz)
    entry = ScheduleEntry(
        job="watch_later",
        frequency="daily",
        hour=3,
        minute=0,
        enabled=True,
    )
    started = datetime(2026, 7, 15, 7, 0, tzinfo=tz).timestamp()
    st = ConsoleState(
        run_history=[{"job": "watch_later", "started_unix": started}],
    )
    assert history_covers_occurrence(st, entry, now) is False


def test_history_covers_interval_slot_only() -> None:
    tz = ZoneInfo("UTC")
    # Slot at 15:00 for every 4h from 03:00 → … 11:00, 15:00, 19:00 …
    now = datetime(2026, 7, 16, 16, 0, tzinfo=tz)
    entry = ScheduleEntry(
        job="watch_later",
        frequency="interval",
        interval_hours=4,
        hour=3,
        minute=0,
        enabled=True,
    )
    before_slot = datetime(2026, 7, 16, 14, 0, tzinfo=tz).timestamp()
    in_slot = datetime(2026, 7, 16, 15, 10, tzinfo=tz).timestamp()
    st_miss = ConsoleState(
        run_history=[{"job": "watch_later", "started_unix": before_slot}],
    )
    st_hit = ConsoleState(
        run_history=[{"job": "watch_later", "started_unix": in_slot}],
    )
    assert history_covers_occurrence(st_miss, entry, now) is False
    assert history_covers_occurrence(st_hit, entry, now) is True
