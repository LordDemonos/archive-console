"""Cookie hygiene reminder: due rules, copy, anchor; server clock is authoritative for snooze."""

from __future__ import annotations

import json
from pathlib import Path

from app.cookie_reminder import (
    COOKIE_REMINDER_MESSAGE,
    cookie_hygiene_anchor_if_needed,
    cookie_reminder_is_due,
    cookie_reminder_payload,
)
from app.settings import CookieHygieneSettings


def test_cookie_off_never_shows() -> None:
    ch = CookieHygieneSettings(
        remind_interval_days=0,
        last_acknowledged_unix=1.0,
        snooze_until_unix=0.0,
    )
    assert cookie_reminder_payload(ch, now=1e12)["show"] is False


def test_cookie_never_ack_not_due() -> None:
    ch = CookieHygieneSettings(
        remind_interval_days=14,
        last_acknowledged_unix=0.0,
        snooze_until_unix=0.0,
    )
    assert cookie_reminder_is_due(ch, now=1e12) is False
    assert cookie_reminder_payload(ch, now=1e12)["show"] is False


def test_cookie_due_after_interval() -> None:
    t0 = 1_000_000.0
    ch = CookieHygieneSettings(
        remind_interval_days=7,
        last_acknowledged_unix=t0,
        snooze_until_unix=0.0,
    )
    now = t0 + 7 * 86400 + 1
    p = cookie_reminder_payload(ch, now=now)
    assert p["show"] is True
    assert "Firefox" in p["message"]
    assert "cookies.txt" in p["message"]
    assert COOKIE_REMINDER_MESSAGE in p["message"]


def test_cookie_not_due_before_interval() -> None:
    t0 = 1_000_000.0
    ch = CookieHygieneSettings(
        remind_interval_days=7,
        last_acknowledged_unix=t0,
        snooze_until_unix=0.0,
    )
    now = t0 + 7 * 86400 - 60
    assert cookie_reminder_payload(ch, now=now)["show"] is False


def test_snooze_suppresses() -> None:
    ch = CookieHygieneSettings(
        remind_interval_days=1,
        last_acknowledged_unix=0.0,
        snooze_until_unix=999_999_999.0,
    )
    assert cookie_reminder_is_due(ch, now=1000.0) is False


def test_anchor_sets_last_ack() -> None:
    ch = CookieHygieneSettings(
        remind_interval_days=3,
        last_acknowledged_unix=0.0,
        snooze_until_unix=0.0,
    )
    out = cookie_hygiene_anchor_if_needed(ch)
    assert out.last_acknowledged_unix > 0


def test_load_state_migrates_interval_without_ack(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "ar"
    root.mkdir()
    p = tmp_path / "state.json"
    p.write_text(
        json.dumps(
            {
                "host": "127.0.0.1",
                "port": 8756,
                "archive_root": str(root),
                "allowlisted_rel_prefixes": ["logs"],
                "cookie_hygiene": {
                    "remind_interval_days": 7,
                    "last_acknowledged_unix": 0,
                    "snooze_until_unix": 0,
                },
            }
        ),
        encoding="utf-8",
    )
    from app import settings as mod

    monkeypatch.setattr(mod, "DEFAULT_STATE_PATH", p)
    st = mod.load_state(p)
    assert st.cookie_hygiene.last_acknowledged_unix > 0
    round_trip = json.loads(p.read_text(encoding="utf-8"))
    assert round_trip["cookie_hygiene"]["last_acknowledged_unix"] > 0
    st2 = mod.ConsoleState.model_validate(round_trip)
    assert cookie_reminder_is_due(st2.cookie_hygiene, now=st2.cookie_hygiene.last_acknowledged_unix + 1) is False
