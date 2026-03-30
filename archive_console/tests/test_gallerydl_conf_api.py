"""GET/PUT /api/files/gallery-dl.conf — allowlist and roundtrip."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.main import app
import app.settings as sm


@pytest.fixture
def gallerydl_files_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ar = tmp_path / "archive"
    ar.mkdir()
    st_path = tmp_path / "state.json"
    st_path.write_text(
        json.dumps(
            {
                "host": "127.0.0.1",
                "port": 8756,
                "archive_root": str(ar),
                "allowlisted_rel_prefixes": ["logs", "galleries"],
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
    with TestClient(app) as client:
        yield client, ar


def test_get_gallery_dl_conf_missing_returns_empty(gallerydl_files_client) -> None:
    client, _ar = gallerydl_files_client
    r = client.get("/api/files/gallery-dl.conf")
    assert r.status_code == 200
    body = r.json()
    assert body["rel"] == "gallery-dl.conf"
    assert body["content"] == ""
    assert body["mtime"] is None
    assert body.get("locked") is False


def test_put_gallery_dl_conf_writes_disk(gallerydl_files_client) -> None:
    client, ar = gallerydl_files_client
    text = '{"extractor": {}}\n'
    r = client.put(
        "/api/files/gallery-dl.conf",
        json={
            "content": text,
            "strip_blank_lines": False,
            "conf_smoke": False,
            "unlock_cookies": False,
        },
    )
    assert r.status_code == 200
    assert r.json().get("ok") is True
    p = ar / "gallery-dl.conf"
    assert p.is_file()
    assert p.read_text(encoding="utf-8") == text


def test_put_unknown_editor_file_404(gallerydl_files_client) -> None:
    client, _ar = gallerydl_files_client
    r = client.put(
        "/api/files/not-listed.conf",
        json={"content": "x", "strip_blank_lines": False},
    )
    assert r.status_code == 404
