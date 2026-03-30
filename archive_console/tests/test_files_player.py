"""Files page: playable media enumeration (allowlist, cap)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.file_serve import (
    collect_playable_rels_under_dir,
    is_files_player_queue_media_path,
    is_playable_media_path,
)
from app.main import app
import app.main as main


@pytest.fixture
def player_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import app.settings as sm

    ar = tmp_path / "archive"
    ar.mkdir()
    (ar / "playlists" / "sub").mkdir(parents=True)
    (ar / "playlists" / "a.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42")
    (ar / "playlists" / "b.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42")
    (ar / "playlists" / "note.txt").write_text("x", encoding="utf-8")
    (ar / "playlists" / "shot.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (ar / "playlists" / "sub" / "c.webm").write_bytes(b"RIFF....WEBM")
    st_path = tmp_path / "state.json"
    st_path.write_text(
        json.dumps(
            {
                "host": "127.0.0.1",
                "port": 8756,
                "archive_root": str(ar),
                "allowlisted_rel_prefixes": ["playlists"],
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
    with TestClient(app) as client:
        yield client, ar


def test_is_playable_media_path():
    assert is_playable_media_path(Path("x.mp4")) is True
    assert is_playable_media_path(Path("y.txt")) is False
    assert is_playable_media_path(Path("z.png")) is False


def test_is_files_player_queue_media_path():
    assert is_files_player_queue_media_path(Path("a.mp4")) is True
    assert is_files_player_queue_media_path(Path("b.PNG")) is True
    assert is_files_player_queue_media_path(Path("c.webp")) is True
    assert is_files_player_queue_media_path(Path("d.txt")) is False
    assert is_files_player_queue_media_path(Path("e.bmp")) is False


def test_playable_enumerate_non_recursive(player_env) -> None:
    client, ar = player_env
    r = client.get(
        "/api/files/playable-enumerate",
        params={"path": "playlists", "recursive": 0},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 3
    rels = sorted(body["rels"])
    assert rels == ["playlists/a.mp4", "playlists/b.mp4", "playlists/shot.png"]


def test_playable_enumerate_recursive_param_ignored(player_env) -> None:
    """Subfolder media is not included; recursive=1 matches flat listing."""
    client, ar = player_env
    r = client.get(
        "/api/files/playable-enumerate",
        params={"path": "playlists", "recursive": 1},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 3
    assert "playlists/sub/c.webm" not in body["rels"]


def test_playable_enumerate_cap(player_env) -> None:
    client, ar = player_env
    (ar / "playlists" / "third.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42")
    r = client.get(
        "/api/files/playable-enumerate",
        params={"path": "playlists", "recursive": 0, "max_files": 2},
    )
    assert r.status_code == 400
    assert "2" in (r.json().get("detail") or "")


def test_playable_enumerate_forbidden_outside_allowlist(player_env) -> None:
    client, ar = player_env
    (ar / "secret").mkdir()
    (ar / "secret" / "x.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42")
    r = client.get(
        "/api/files/playable-enumerate",
        params={"path": "secret", "recursive": 0},
    )
    assert r.status_code == 403


def test_reports_file_accepts_ranges(player_env) -> None:
    client, ar = player_env
    r = client.get(
        "/reports/file",
        params={"rel": "playlists/a.mp4"},
        headers={"Range": "bytes=0-3"},
    )
    assert r.status_code == 206
    assert r.headers.get("accept-ranges") == "bytes"
    assert int(r.headers.get("content-length", "0")) <= 4


def test_collect_raises_on_not_dir(tmp_path: Path) -> None:
    root = tmp_path
    (root / "media").mkdir()
    (root / "media" / "f.mp4").write_bytes(b"x")
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as ei:
        collect_playable_rels_under_dir(
            root,
            "media/f.mp4",
            ["media"],
            recursive=False,
            max_files=10,
        )
    assert ei.value.status_code == 404
