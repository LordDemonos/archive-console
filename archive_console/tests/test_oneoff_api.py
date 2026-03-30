"""One-off start API: cookie gate and URL validation."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.main import app
import app.settings as sm


@pytest.fixture
def oneoff_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ar = tmp_path / "archive"
    ar.mkdir()
    st_path = tmp_path / "state.json"
    st_path.write_text(
        json.dumps(
            {
                "host": "127.0.0.1",
                "port": 8756,
                "archive_root": str(ar),
                "allowlisted_rel_prefixes": ["logs", "playlists", "videos", "channels", "oneoff"],
                "download_dirs": {
                    "watch_later": "",
                    "channels": "",
                    "videos": "",
                    "oneoff": "",
                },
                "oneoff_report_retention_days": 90,
                "oneoff_cookie_reminder_last_unix": 0,
                "features": {
                    "scheduler_enabled": False,
                    "notifications_stub": False,
                    "require_cookie_confirm_manual": True,
                    "tray_notify_before_schedule": False,
                },
                "schedules": [],
                "run_history": [],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(sm, "DEFAULT_STATE_PATH", st_path)
    main._state = None
    main._manager = None

    class FakeMgr:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        async def start(self, job, **kwargs):  # noqa: ANN001
            self.calls.append({"job": job, **kwargs})
            return SimpleNamespace(
                run_id="oneoff-test",
                job=job,
                started_unix=1.0,
            )

        async def status(self) -> dict:
            return {"phase": "idle"}

    fake = FakeMgr()
    monkeypatch.setattr(main, "_get_manager", lambda: fake)
    with TestClient(app) as client:
        yield client, fake


def test_oneoff_start_428_without_cookie_confirm(oneoff_env) -> None:
    client, fake = oneoff_env
    r = client.post(
        "/api/oneoff/start",
        json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
    )
    assert r.status_code == 428
    assert r.json().get("error") == "cookie_confirm_required"
    assert not fake.calls


def test_oneoff_start_skips_cookie_when_dry_run(oneoff_env) -> None:
    client, fake = oneoff_env
    r = client.post(
        "/api/oneoff/start",
        json={
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "dry_run": True,
        },
    )
    assert r.status_code == 200
    assert len(fake.calls) == 1
    assert fake.calls[0]["job"] == "oneoff"


def test_oneoff_start_400_bad_url(oneoff_env) -> None:
    client, fake = oneoff_env
    r = client.post("/api/oneoff/start", json={"url": "not-a-url"})
    assert r.status_code == 400
    assert not fake.calls


def test_oneoff_cookie_banner_ack_via_settings(oneoff_env) -> None:
    """One-off Acknowledge persists the same field as POST /api/settings patch."""
    client, _fake = oneoff_env
    t = 1_700_000_000.0
    r = client.post("/api/settings", json={"oneoff_cookie_reminder_last_unix": t})
    assert r.status_code == 200
    r2 = client.get("/api/settings")
    assert r2.status_code == 200
    assert r2.json().get("oneoff_cookie_reminder_last_unix") == pytest.approx(t)


def test_oneoff_cookie_reminder_ack_alias_route(oneoff_env) -> None:
    """Dedicated POST remains registered (curl/scripts); UI uses /api/settings."""
    client, _fake = oneoff_env
    r = client.post("/api/oneoff/cookie-reminder-ack")
    assert r.status_code == 200
    assert r.json().get("ok") == "true"
