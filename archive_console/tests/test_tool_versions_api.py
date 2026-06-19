"""GET /api/tools/versions — bounded CLI checks (mocked subprocess)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import app.main as main
import app.settings as sm


@pytest.fixture()
def tv_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
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
                    "require_cookie_confirm_manual": False,
                    "tray_notify_before_schedule": False,
                },
                "schedules": [],
                "run_history": [],
                "show_getting_started": True,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(sm, "DEFAULT_STATE_PATH", st_path)
    main._state = None  # noqa: SLF001
    main._manager = None  # noqa: SLF001
    with TestClient(main.app) as client:
        yield client


def test_tools_versions_ok(tv_client: TestClient) -> None:
    def fake_run(argv: list[str], **kwargs: object):
        assert kwargs.get("shell") is False
        assert "timeout" in kwargs
        if argv == ["mock-yt-dlp", "--version"]:
            return subprocess.CompletedProcess(argv, 0, "2025.01.01\n", "")
        if argv == ["mock-gallery-dl", "--version"]:
            return subprocess.CompletedProcess(argv, 0, "1.28.0\n", "")
        if argv == ["ffmpeg", "-version"]:
            return subprocess.CompletedProcess(argv, 0, "ffmpeg version 6.0\n", "")
        if argv == ["mock-gifski", "--version"]:
            return subprocess.CompletedProcess(argv, 0, "gifski 1.11.0\n", "")
        return subprocess.CompletedProcess(argv, 99, "", "unexpected argv")

    with (
        patch(
            "app.tool_versions.resolve_ytdlp_version_argv",
            return_value=["mock-yt-dlp", "--version"],
        ),
        patch(
            "app.tool_versions.resolve_gallery_dl_exe",
            return_value="mock-gallery-dl",
        ),
        patch("app.tool_versions.gallery_dl_exe_invocable", return_value=True),
        patch(
            "app.tool_versions.resolve_gifski_bin",
            return_value="mock-gifski",
        ),
        patch("app.tool_versions.subprocess.run", side_effect=fake_run),
    ):
        r = tv_client.get("/api/tools/versions")
    assert r.status_code == 200
    body = r.json()
    tools = {t["tool"]: t for t in body["tools"]}
    assert tools["python"]["ok"] is True
    assert tools["python"]["version"]
    assert tools["yt-dlp"]["ok"] is True
    assert "2025.01.01" in (tools["yt-dlp"]["version"] or "")
    assert tools["ffmpeg"]["ok"] is True
    assert tools["gallery-dl"]["ok"] is True
    assert tools["gifski"]["ok"] is True
    assert "1.11.0" in (tools["gifski"]["version"] or "")


def test_tools_versions_ytdlp_missing(tv_client: TestClient) -> None:
    def fake_run(argv: list[str], **kwargs: object):
        if argv == ["mock-yt-dlp", "--version"]:
            raise FileNotFoundError(2, "nope", argv[0])
        if argv == ["mock-gallery-dl", "--version"]:
            return subprocess.CompletedProcess(argv, 0, "1.0\n", "")
        if argv == ["ffmpeg", "-version"]:
            return subprocess.CompletedProcess(argv, 0, "ffmpeg version 6.0\n", "")
        if argv == ["mock-gifski", "--version"]:
            return subprocess.CompletedProcess(argv, 0, "gifski 1.0\n", "")
        raise AssertionError(argv)

    with (
        patch(
            "app.tool_versions.resolve_ytdlp_version_argv",
            return_value=["mock-yt-dlp", "--version"],
        ),
        patch(
            "app.tool_versions.resolve_gallery_dl_exe",
            return_value="mock-gallery-dl",
        ),
        patch("app.tool_versions.gallery_dl_exe_invocable", return_value=True),
        patch(
            "app.tool_versions.resolve_gifski_bin",
            return_value="mock-gifski",
        ),
        patch("app.tool_versions.subprocess.run", side_effect=fake_run),
    ):
        r = tv_client.get("/api/tools/versions")
    assert r.status_code == 200
    tools = {t["tool"]: t for t in r.json()["tools"]}
    assert tools["yt-dlp"]["ok"] is False
    assert tools["yt-dlp"]["error"] == "not found"


def test_tools_versions_timeout(tv_client: TestClient) -> None:
    def fake_run(argv: list[str], **kwargs: object):
        raise subprocess.TimeoutExpired(argv, float(kwargs.get("timeout") or 1))

    with (
        patch(
            "app.tool_versions.resolve_ytdlp_version_argv",
            return_value=["mock-yt-dlp", "--version"],
        ),
        patch(
            "app.tool_versions.resolve_gallery_dl_exe",
            return_value="mock-gallery-dl",
        ),
        patch("app.tool_versions.gallery_dl_exe_invocable", return_value=True),
        patch(
            "app.tool_versions.resolve_gifski_bin",
            return_value="mock-gifski",
        ),
        patch("app.tool_versions.subprocess.run", side_effect=fake_run),
    ):
        r = tv_client.get("/api/tools/versions")
    assert r.status_code == 200
    tools = {t["tool"]: t for t in r.json()["tools"]}
    assert tools["yt-dlp"]["ok"] is False
    assert tools["yt-dlp"]["error"] == "timeout"


def test_tools_versions_nonzero(tv_client: TestClient) -> None:
    def fake_run(argv: list[str], **kwargs: object):
        if argv == ["ffmpeg", "-version"]:
            return subprocess.CompletedProcess(argv, 7, "", "broken\n")
        if argv == ["mock-yt-dlp", "--version"]:
            return subprocess.CompletedProcess(argv, 0, "1\n", "")
        if argv == ["mock-gallery-dl", "--version"]:
            return subprocess.CompletedProcess(argv, 0, "1.0\n", "")
        if argv == ["mock-gifski", "--version"]:
            return subprocess.CompletedProcess(argv, 0, "gifski 1.0\n", "")
        raise AssertionError(argv)

    with (
        patch(
            "app.tool_versions.resolve_ytdlp_version_argv",
            return_value=["mock-yt-dlp", "--version"],
        ),
        patch(
            "app.tool_versions.resolve_gallery_dl_exe",
            return_value="mock-gallery-dl",
        ),
        patch("app.tool_versions.gallery_dl_exe_invocable", return_value=True),
        patch(
            "app.tool_versions.resolve_gifski_bin",
            return_value="mock-gifski",
        ),
        patch("app.tool_versions.subprocess.run", side_effect=fake_run),
    ):
        r = tv_client.get("/api/tools/versions")
    assert r.status_code == 200
    row = next(t for t in r.json()["tools"] if t["tool"] == "ffmpeg")
    assert row["ok"] is False
    assert row["error"] and "exit 7" in row["error"]


def test_settings_includes_show_getting_started(tv_client: TestClient) -> None:
    r = tv_client.get("/api/settings")
    assert r.status_code == 200
    assert r.json().get("show_getting_started") is True


def test_settings_includes_landing_and_onboarding(tv_client: TestClient) -> None:
    """Legacy state without new keys is migrated to onboarding complete + run default."""
    r = tv_client.get("/api/settings")
    assert r.status_code == 200
    j = r.json()
    assert j.get("getting_started_seen") is True
    assert j.get("default_landing_view") == "run"


def test_settings_patch_show_getting_started(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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
                    "require_cookie_confirm_manual": False,
                    "tray_notify_before_schedule": False,
                },
                "schedules": [],
                "run_history": [],
                "show_getting_started": True,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(sm, "DEFAULT_STATE_PATH", st_path)
    main._state = None  # noqa: SLF001
    main._manager = None  # noqa: SLF001
    with TestClient(main.app) as client:
        r = client.post("/api/settings", json={"show_getting_started": False})
        assert r.status_code == 200
        r2 = client.get("/api/settings")
        assert r2.json().get("show_getting_started") is False


def test_settings_save_general_includes_czkawka_exe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: Save general posts czkawka_exe; missing import caused HTTP 500."""
    ar = tmp_path / "archive"
    ar.mkdir()
    (ar / "logs").mkdir()
    st_path = tmp_path / "state.json"
    st_path.write_text(
        json.dumps(
            {
                "host": "127.0.0.1",
                "port": 8756,
                "archive_root": str(ar),
                "allowlisted_rel_prefixes": ["logs"],
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
                    "require_cookie_confirm_manual": False,
                    "tray_notify_before_schedule": False,
                },
                "schedules": [],
                "run_history": [],
                "czkawka_exe": "windows_czkawka_cli.exe",
                "duplicates_quarantine_rel": "logs/_duplicates_quarantine",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(sm, "DEFAULT_STATE_PATH", st_path)
    main._state = None  # noqa: SLF001
    main._manager = None  # noqa: SLF001
    body = {
        "port": 8756,
        "allowlisted_rel_prefixes": ["logs"],
        "archive_root": str(ar),
        "editor_backup_max": 10,
        "ffmpeg_exe": "",
        "gifski_exe": "",
        "czkawka_exe": "windows_czkawka_cli.exe",
        "mediainfo_exe": "",
        "exiftool_exe": "",
        "exiftool_timeout_sec": 45,
        "duplicates_quarantine_rel": "logs/_duplicates_quarantine",
        "duplicates_prefer_quarantine": True,
        "show_getting_started": False,
        "default_landing_view": "home",
    }
    with TestClient(main.app) as client:
        r = client.post("/api/settings", json=body)
        assert r.status_code == 200, r.text
        assert client.get("/api/settings").json().get("show_getting_started") is False


def test_settings_patch_default_landing_view(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ar = tmp_path / "archive2"
    ar.mkdir()
    st_path = tmp_path / "state2.json"
    st_path.write_text(
        json.dumps(
            {
                "host": "127.0.0.1",
                "port": 8756,
                "archive_root": str(ar),
                "allowlisted_rel_prefixes": ["logs"],
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
                    "require_cookie_confirm_manual": False,
                    "tray_notify_before_schedule": False,
                },
                "schedules": [],
                "run_history": [],
                "show_getting_started": True,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(sm, "DEFAULT_STATE_PATH", st_path)
    main._state = None  # noqa: SLF001
    main._manager = None  # noqa: SLF001
    with TestClient(main.app) as client:
        rh = client.post("/api/settings", json={"default_landing_view": "home"})
        assert rh.status_code == 200
        assert client.get("/api/settings").json().get("default_landing_view") == "home"
        rb = client.post("/api/settings", json={"default_landing_view": "not-a-view"})
        assert rb.status_code == 200
        assert client.get("/api/settings").json().get("default_landing_view") == "run"
