"""Galleries preview/start API: cookie gate, mutex, URL validation."""

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
def galleries_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ar = tmp_path / "archive"
    ar.mkdir()
    st_path = tmp_path / "state.json"
    st_path.write_text(
        json.dumps(
            {
                "host": "127.0.0.1",
                "port": 8756,
                "archive_root": str(ar),
                "allowlisted_rel_prefixes": [
                    "logs",
                    "playlists",
                    "videos",
                    "channels",
                    "oneoff",
                    "galleries",
                ],
                "download_dirs": {
                    "watch_later": "",
                    "channels": "",
                    "videos": "",
                    "oneoff": "",
                    "galleries": "",
                },
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
                run_id="gal-test",
                job=job,
                started_unix=1.0,
            )

        async def status(self) -> dict:
            return {"phase": "idle"}

    fake = FakeMgr()
    monkeypatch.setattr(main, "_get_manager", lambda: fake)
    with TestClient(app) as client:
        yield client, fake


def test_galleries_start_428_without_cookie_confirm(galleries_env) -> None:
    client, fake = galleries_env
    r = client.post(
        "/api/galleries/start",
        json={"url": "https://www.reddit.com/r/test/"},
    )
    assert r.status_code == 428
    assert r.json().get("error") == "cookie_confirm_required"
    assert not fake.calls


def test_galleries_start_skips_cookie_when_dry_run(galleries_env) -> None:
    client, fake = galleries_env
    st_path = sm.DEFAULT_STATE_PATH
    data = json.loads(st_path.read_text(encoding="utf-8"))
    root = Path(data["archive_root"])
    (root / "archive_gallery_run.py").write_text("# stub\n", encoding="utf-8")

    r = client.post(
        "/api/galleries/start",
        json={
            "url": "https://www.reddit.com/r/test/",
            "dry_run": True,
        },
    )
    assert r.status_code == 200
    assert len(fake.calls) == 1
    assert fake.calls[0]["job"] == "galleries"


def test_galleries_start_400_bad_url(galleries_env) -> None:
    client, fake = galleries_env
    r = client.post("/api/galleries/start", json={"url": ""})
    assert r.status_code == 400
    assert not fake.calls


def test_galleries_preview_accepts_reddit_url(galleries_env, monkeypatch) -> None:
    client, _fake = galleries_env

    def fake_dump(**kwargs):  # noqa: ANN003
        return 0, '{"title": "x", "url": "https://example.com/a.jpg"}\n', ""

    monkeypatch.setattr(main, "run_gallery_dl_json_dump", fake_dump)
    r = client.post(
        "/api/galleries/preview",
        json={"url": "old.reddit.com/r/foo/"},
    )
    assert r.status_code == 200
    j = r.json()
    assert "www.reddit.com" in j["url"]
    assert len(j["rows"]) >= 1


def test_browse_download_dir_body_accepts_galleries_field() -> None:
    from app.main import BrowseDownloadDirBody

    assert BrowseDownloadDirBody(field="galleries").field == "galleries"
