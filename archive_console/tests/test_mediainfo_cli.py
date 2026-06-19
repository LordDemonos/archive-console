"""MediaInfo CLI validation, JSON parse, and API allowlist."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.mediainfo_cli import (
    mediainfo_for_file,
    parse_mediainfo_json,
    resolve_mediainfo_bin,
    validate_mediainfo_exe_setting,
)
import app.main as main


def test_validate_mediainfo_exe_setting() -> None:
    assert validate_mediainfo_exe_setting("") == ""
    assert validate_mediainfo_exe_setting("  ") == ""
    assert validate_mediainfo_exe_setting("C:\\Tools\\MediaInfo.exe") == "C:\\Tools\\MediaInfo.exe"
    with pytest.raises(ValueError):
        validate_mediainfo_exe_setting("mediainfo;rm -rf /")


def test_parse_mediainfo_json_general_and_video() -> None:
    raw = json.dumps(
        {
            "media": {
                "track": [
                    {
                        "@type": "General",
                        "Format": "MPEG-4",
                        "Format_Profile": "Base Media",
                        "OverallBitRate": "5000000",
                        "Duration": "61000",
                    },
                    {
                        "@type": "Video",
                        "Format": "AVC",
                        "Width": "1920",
                        "Height": "1080",
                        "FrameRate": "30.000",
                        "ScanType": "Progressive",
                        "Title": "Main",
                    },
                ]
            }
        }
    )
    dto = parse_mediainfo_json(raw)
    assert dto.container == "MPEG-4"
    assert dto.duration_ms == 61000
    assert dto.overall_bitrate == "5000000"
    assert len(dto.streams) == 1
    assert dto.streams[0].kind == "Video"
    assert dto.streams[0].width == 1920
    assert dto.streams[0].height == 1080
    assert dto.sparse is False


def test_parse_mediainfo_json_sparse() -> None:
    dto = parse_mediainfo_json("{}")
    assert dto.sparse is True


def test_resolve_mediainfo_bin_existing_file(tmp_path: Path) -> None:
    exe = tmp_path / "my_mediainfo.cmd"
    exe.write_text("@echo off\n", encoding="utf-8")
    got = resolve_mediainfo_bin(str(exe))
    assert Path(got).resolve() == exe.resolve()


def test_resolve_mediainfo_bin_empty_uses_which(monkeypatch: pytest.MonkeyPatch) -> None:
    names: list[str] = []

    def fake_which(name: str) -> str | None:
        names.append(name)
        if name == "mediainfo":
            return None
        if name == "MediaInfo":
            return r"C:\Program Files\MediaInfo\MediaInfo.exe"
        return None

    monkeypatch.setattr("app.mediainfo_cli.shutil.which", fake_which)
    assert resolve_mediainfo_bin("") == r"C:\Program Files\MediaInfo\MediaInfo.exe"
    assert names[:2] == ["mediainfo", "MediaInfo"]


def test_mediainfo_for_file_missing_exe_has_help_url(tmp_path: Path) -> None:
    f = tmp_path / "clip.mp4"
    f.write_bytes(b"x")
    out = mediainfo_for_file(str(tmp_path / "no_such_mediainfo.exe"), f)
    assert out["ok"] is False
    assert out.get("error_code") == "executable_not_found"
    assert "help_url" in out
    assert "mediaarea.net" in str(out["help_url"])


@pytest.fixture
def mediainfo_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import app.settings as sm

    ar = tmp_path / "archive"
    ar.mkdir()
    (ar / "videos").mkdir()
    f = ar / "videos" / "a.mp4"
    f.write_bytes(b"x")
    st_path = tmp_path / "state.json"
    st_path.write_text(
        json.dumps(
            {
                "host": "127.0.0.1",
                "port": 8756,
                "archive_root": str(ar),
                "allowlisted_rel_prefixes": ["videos"],
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
        yield client


def test_mediainfo_api_403_outside_allowlist(mediainfo_client: TestClient) -> None:
    r = mediainfo_client.get(
        "/api/files/mediainfo", params={"path": "other/secret.mp4"}
    )
    assert r.status_code == 403


def test_mediainfo_api_ok_monkeypatch(mediainfo_client: TestClient, monkeypatch) -> None:
    def fake_mediainfo(exe: str, file_abs: Path, **kwargs):
        return {
            "ok": True,
            "details": {
                "container": "Test",
                "format_profile": "",
                "duration_ms": 1000,
                "overall_bitrate": "",
                "streams": [],
                "sparse": False,
            },
        }

    monkeypatch.setattr(main, "mediainfo_for_file", fake_mediainfo)
    r = mediainfo_client.get(
        "/api/files/mediainfo", params={"path": "videos/a.mp4"}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["details"]["container"] == "Test"
