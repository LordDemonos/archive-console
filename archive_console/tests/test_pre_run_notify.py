"""Shared pre-run reminder window (banner + tray tick)."""

from __future__ import annotations

from datetime import datetime

from zoneinfo import ZoneInfo

from app.pre_run_notify import pre_run_reminder_banner
from app.settings import (
    ConsoleState,
    Features,
    PreRunReminderSettings,
    ScheduleEntry,
)


def _st(
    *,
    minutes_before: int,
    ack_key: str = "",
    snooze_until: float = 0.0,
) -> ConsoleState:
    return ConsoleState(
        archive_root=".",
        allowlisted_rel_prefixes=["logs"],
        features=Features(),
        schedules=[
            ScheduleEntry(
                id="s1",
                enabled=True,
                job="watch_later",
                day_of_month=29,
                hour=12,
                minute=0,
            ),
        ],
        pre_run_reminder=PreRunReminderSettings(
            minutes_before=minutes_before,
            snooze_until_unix=snooze_until,
            acknowledged_fire_key=ack_key,
        ),
    )


def test_pre_run_off_when_minutes_zero() -> None:
    st = _st(minutes_before=0)
    tz = ZoneInfo("UTC")
    now = datetime(2026, 3, 29, 11, 45, tzinfo=tz)
    out = pre_run_reminder_banner(st, now_local=now)
    assert out["show"] is False


def test_pre_run_in_reminder_window() -> None:
    st = _st(minutes_before=30)
    tz = ZoneInfo("UTC")
    now = datetime(2026, 3, 29, 11, 35, tzinfo=tz)
    out = pre_run_reminder_banner(st, now_local=now)
    assert out["show"] is True
    assert out["fire_key"]
    assert "watch_later" in out["message"]


def test_pre_run_outside_window_early() -> None:
    st = _st(minutes_before=30)
    tz = ZoneInfo("UTC")
    now = datetime(2026, 3, 29, 10, 0, tzinfo=tz)
    out = pre_run_reminder_banner(st, now_local=now)
    assert out["show"] is False


def test_pre_run_suppressed_when_acknowledged() -> None:
    st0 = _st(minutes_before=30)
    tz = ZoneInfo("UTC")
    now = datetime(2026, 3, 29, 11, 35, tzinfo=tz)
    pending = pre_run_reminder_banner(st0, now_local=now)
    fk = pending["fire_key"]
    st1 = st0.model_copy(
        update={
            "pre_run_reminder": st0.pre_run_reminder.model_copy(
                update={"acknowledged_fire_key": fk},
            ),
        },
    )
    out = pre_run_reminder_banner(st1, now_local=now)
    assert out["show"] is False


def test_pre_run_suppressed_when_snoozed() -> None:
    tz = ZoneInfo("UTC")
    now = datetime(2026, 3, 29, 11, 35, tzinfo=tz)
    ts = now.timestamp()
    st = _st(minutes_before=30, snooze_until=ts + 3600)
    out = pre_run_reminder_banner(st, now_local=now)
    assert out["show"] is False
