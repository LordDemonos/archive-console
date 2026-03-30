"""Manual run cookie preflight gate (HTTP 428 until cookie_confirm)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import app
import app.main as main


@pytest.fixture
def gate_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import app.settings as sm

    ar = tmp_path / "archive"
    ar.mkdir()
    st_path = tmp_path / "state.json"
    st_path.write_text(
        json.dumps(
            {
                "host": "127.0.0.1",
                "port": 8756,
                "archive_root": str(ar),
                "allowlisted_rel_prefixes": ["logs"],
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
                run_id="test-run",
                job=job,
                started_unix=1.0,
            )

        async def status(self) -> dict:
            return {"phase": "idle"}

    fake = FakeMgr()
    monkeypatch.setattr(main, "_get_manager", lambda: fake)
    with TestClient(app) as client:
        yield client, fake


def test_run_start_cookie_gate_returns_428_without_confirm(gate_env) -> None:
    client, fake = gate_env
    r = client.post("/api/run/start", json={"job": "watch_later"})
    assert r.status_code == 428
    body = r.json()
    assert body.get("error") == "cookie_confirm_required"
    assert not fake.calls


def test_run_start_cookie_gate_skipped_for_dry_run(gate_env) -> None:
    client, fake = gate_env
    r = client.post(
        "/api/run/start",
        json={"job": "watch_later", "dry_run": True},
    )
    assert r.status_code == 200
    assert len(fake.calls) == 1


def test_run_start_with_cookie_confirm_starts(gate_env) -> None:
    client, fake = gate_env
    r = client.post(
        "/api/run/start",
        json={"job": "watch_later", "cookie_confirm": True},
    )
    assert r.status_code == 200
    assert len(fake.calls) == 1
    assert fake.calls[0]["job"] == "watch_later"


def test_run_start_gate_disabled_in_state(tmp_path: Path, monkeypatch) -> None:
    import app.settings as sm

    ar = tmp_path / "ar"
    ar.mkdir()
    st_path = tmp_path / "state.json"
    st_path.write_text(
        json.dumps(
            {
                "host": "127.0.0.1",
                "port": 8756,
                "archive_root": str(ar),
                "allowlisted_rel_prefixes": ["logs"],
                "features": {
                    "scheduler_enabled": False,
                    "notifications_stub": False,
                    "require_cookie_confirm_manual": False,
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
            self.starts = 0

        async def start(self, job, **_k):
            self.starts += 1
            return SimpleNamespace(
                run_id="x",
                job=job,
                started_unix=0.0,
            )

        async def status(self) -> dict:
            return {"phase": "idle"}

    fake = FakeMgr()
    monkeypatch.setattr(main, "_get_manager", lambda: fake)
    with TestClient(app) as client:
        r = client.post("/api/run/start", json={"job": "videos"})
        assert r.status_code == 200
    assert fake.starts == 1
