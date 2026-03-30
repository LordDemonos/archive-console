"""Clip export: path rules and ffmpeg argv construction."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.clip_export import (
    build_ffmpeg_argv,
    resolve_clip_paths,
    validate_clip_times,
    validate_ffmpeg_exe_setting,
)
from app.main import app
import app.main as main


def test_validate_ffmpeg_exe_setting_rejects_shell_chars() -> None:
    with pytest.raises(ValueError):
        validate_ffmpeg_exe_setting("ffmpeg;rm -rf /")


def test_validate_clip_times_max_segment() -> None:
    with pytest.raises(ValueError, match="longer than"):
        validate_clip_times(0.0, duration_sec=601.0)


def test_build_ffmpeg_argv_mp4() -> None:
    argv = build_ffmpeg_argv(
        "ffmpeg",
        Path("/in/video.mp4"),
        Path("/out/x.mp4"),
        1.5,
        10.0,
        "mp4",
    )
    assert argv[0] == "ffmpeg"
    assert "-ss" in argv
    assert "1.500000" in argv or "1.5" in argv
    assert "-t" in argv
    assert "-c:v" in argv
    assert "libx264" in argv
    assert str(Path("/out/x.mp4")) in argv or "/out/x.mp4" in " ".join(argv)


def test_build_ffmpeg_argv_gif_palette() -> None:
    argv = build_ffmpeg_argv(
        "ff",
        Path("a.mp4"),
        Path("b.gif"),
        0.0,
        2.0,
        "gif",
    )
    joined = " ".join(argv)
    assert "palettegen" in joined
    assert "paletteuse" in joined


def test_resolve_clip_paths_playable_only(tmp_path: Path) -> None:
    root = tmp_path / "archive"
    root.mkdir()
    (root / "playlists").mkdir()
    vid = root / "playlists" / "a.mp4"
    vid.write_bytes(b"\x00\x00\x00\x18ftypmp42")
    note = root / "playlists" / "n.txt"
    note.write_text("x", encoding="utf-8")
    prefixes = ["playlists"]
    src, out, rel = resolve_clip_paths(
        root, prefixes, "playlists/a.mp4", "playlists", "", "mp4"
    )
    assert src == vid.resolve()
    assert rel.startswith("playlists/")
    assert rel.endswith(".mp4")
    with pytest.raises(ValueError, match="not a supported"):
        resolve_clip_paths(
            root, prefixes, "playlists/n.txt", "playlists", "x", "mp4"
        )


@pytest.fixture
def clip_client_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import app.settings as sm

    ar = tmp_path / "archive"
    ar.mkdir()
    (ar / "playlists").mkdir()
    (ar / "playlists" / "clip.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42")
    st_path = tmp_path / "state.json"
    st_path.write_text(
        json.dumps(
            {
                "host": "127.0.0.1",
                "port": 8756,
                "archive_root": str(ar),
                "allowlisted_rel_prefixes": ["playlists"],
                "ffmpeg_exe": "",
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
    main._clip_manager = None
    with TestClient(app) as client:
        yield client, ar


def test_api_clip_start_rejects_disallowed_source(clip_client_env) -> None:
    client, _ar = clip_client_env
    r = client.post(
        "/api/clip/start",
        json={
            "source_rel": "videos/nope.mp4",
            "output_dir_rel": "playlists",
            "start_sec": 0,
            "duration_sec": 1,
            "format": "mp4",
            "basename": "",
        },
    )
    assert r.status_code == 403
