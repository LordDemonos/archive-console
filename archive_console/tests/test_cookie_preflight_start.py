"""Extension cookie preflight before yt-dlp run start."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.cookie_preflight import CookiePreflightTimeoutError
import app.main as main
from app.main import app


def _write_state(
    tmp_path: Path,
    *,
    preflight_via_extension: bool = True,
    require_cookie_confirm_manual: bool = True,
) -> Path:
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
                    "require_cookie_confirm_manual": require_cookie_confirm_manual,
                    "tray_notify_before_schedule": False,
                },
                "ytdlp_batch_run": {
                    "preflight_via_extension": preflight_via_extension,
                    "preflight_wait_sec": 30,
                    "pause_on_cookie_error": False,
                    "cookie_auth_poll_sec": 15,
                },
                "schedules": [],
                "run_history": [],
            }
        ),
        encoding="utf-8",
    )
    return st_path


@pytest.fixture
def preflight_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import app.settings as sm

    st_path = _write_state(tmp_path)
    monkeypatch.setattr(sm, "DEFAULT_STATE_PATH", st_path)
    main._state = None
    main._manager = None

    class FakeMgr:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        async def start(self, job, **kwargs):  # noqa: ANN001
            self.calls.append({"job": job, **kwargs})
            return SimpleNamespace(
                run_id="pf-run",
                job=job,
                started_unix=1.0,
            )

        async def status(self) -> dict:
            return {"phase": "idle"}

    fake = FakeMgr()
    monkeypatch.setattr(main, "_get_manager", lambda: fake)

    async def _ok_preflight(*_a, **_k):
        return True, "cookies refreshed"

    monkeypatch.setattr(
        "app.run_manager.await_extension_cookie_preflight",
        _ok_preflight,
    )

    with TestClient(app) as client:
        yield client, fake


def test_run_start_skips_428_when_preflight_enabled(preflight_client) -> None:
    client, fake = preflight_client
    r = client.post("/api/run/start", json={"job": "watch_later"})
    assert r.status_code == 200
    assert len(fake.calls) == 1
    assert fake.calls[0]["preflight_via_extension"] is True


def test_run_manager_raises_when_preflight_times_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import asyncio

    from app.run_manager import RunManager

    ar = tmp_path / "archive"
    ar.mkdir()
    (ar / "monthly_videos_archive.bat").write_text("@echo off\n", encoding="utf-8")
    mgr = RunManager(archive_root=ar)

    async def _timeout(*_a, **_k):
        return False, "cookie preflight timed out after 30s"

    monkeypatch.setattr(
        "app.run_manager.await_extension_cookie_preflight",
        _timeout,
    )

    async def _noop_complete(_finished) -> None:
        return None

    with pytest.raises(CookiePreflightTimeoutError, match="preflight"):
        asyncio.run(
            mgr.start(
                "videos",
                dry_run=False,
                skip_ytdlp_update=True,
                skip_pip_update=True,
                on_complete=_noop_complete,
                preflight_via_extension=True,
                preflight_wait_sec=30,
            )
        )


def test_youtube_refresh_reports_preflight_needed(tmp_path: Path, monkeypatch) -> None:
    import app.settings as sm
    from archive_cookies import request_cookie_preflight

    st_path = _write_state(tmp_path, preflight_via_extension=True)
    monkeypatch.setattr(sm, "DEFAULT_STATE_PATH", st_path)
    main._state = None
    main._manager = None

    ar = tmp_path / "archive"
    request_cookie_preflight(str(ar), job="watch_later")

    with TestClient(app) as client:
        r = client.get("/api/cookies/youtube-refresh")
    assert r.status_code == 200
    body = r.json()
    assert body["preflight_needed"] is True
    assert "preflight_before_run" in str(
        (body.get("request") or {}).get("reason", "")
    )
