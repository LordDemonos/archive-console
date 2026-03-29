"""Settings model migration, schedules, operator backup validation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.operator_backup import run_operator_backup
from app.schedule_util import next_run_iso
from app.settings import ConsoleState, OperatorBackupConfig, ScheduleEntry


def test_console_state_loads_legacy_minimal_json(tmp_path: Path, monkeypatch):
    """Old state without Phase-1 keys gets defaults."""
    ar = tmp_path / "ar"
    ar.mkdir()
    monkeypatch.chdir(tmp_path)
    p = tmp_path / "state.json"
    p.write_text(
        json.dumps(
            {
                "host": "127.0.0.1",
                "port": 8756,
                "archive_root": str(ar),
                "allowlisted_rel_prefixes": ["logs"],
                "features": {"scheduler_enabled": False, "notifications_stub": False},
                "schedules": [],
                "run_history": [],
            }
        ),
        encoding="utf-8",
    )
    from app import settings as mod

    monkeypatch.setattr(mod, "DEFAULT_STATE_PATH", p)
    st = mod.load_state(p)
    assert st.settings_schema_version == 1
    assert st.operator_backup.destination_rel
    assert st.cookie_hygiene.remind_interval_days == 0
    assert st.pre_run_reminder.minutes_before == 0


def test_next_run_iso_disabled():
    s = ScheduleEntry(enabled=False, day_of_month=1, hour=12, minute=0)
    assert next_run_iso(s) is None


def test_next_run_iso_enabled():
    s = ScheduleEntry(
        id="a",
        enabled=True,
        job="watch_later",
        day_of_month=28,
        hour=12,
        minute=0,
    )
    iso = next_run_iso(s)
    assert iso and "T" in iso


def test_operator_backup_rejects_bad_destination(tmp_path: Path, monkeypatch):
    root = tmp_path / "ar"
    root.mkdir()
    (root / "logs").mkdir()
    st = ConsoleState(
        archive_root=str(root),
        allowlisted_rel_prefixes=["logs"],
        operator_backup=OperatorBackupConfig(
            destination_rel="playlists/no",
            include_logs_dir=False,
        ),
    )
    res = run_operator_backup(st)
    assert res.success is False
    assert "forbidden" in res.summary.lower()


def test_operator_backup_writes_zip(tmp_path: Path, monkeypatch):
    root = tmp_path / "ar"
    root.mkdir()
    logs = root / "logs" / "archive_console_backups"
    logs.mkdir(parents=True)
    (root / "logs" / "a.log").write_text("x", encoding="utf-8")
    st_path = tmp_path / "console" / "state.json"
    st_path.parent.mkdir(parents=True)
    st_path.write_text('{"port": 1}', encoding="utf-8")
    from app import operator_backup as ob

    monkeypatch.setattr(ob, "DEFAULT_STATE_PATH", st_path)
    from app.settings import ConsoleState, OperatorBackupConfig

    st = ConsoleState(
        archive_root=str(root),
        allowlisted_rel_prefixes=["logs"],
        operator_backup=OperatorBackupConfig(
            destination_rel="logs/archive_console_backups",
            include_state_json=True,
            include_logs_dir=True,
            retention_max_files=10,
            retention_days=0,
        ),
    )
    res = run_operator_backup(st)
    assert res.success is True
    assert res.summary.endswith(".zip")
    dest = root / res.summary
    assert dest.is_file()
