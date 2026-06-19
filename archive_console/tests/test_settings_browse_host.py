"""Settings host browse API."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def browse_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    root = tmp_path / "ar"
    root.mkdir()
    (root / "logs").mkdir()
    state_path = tmp_path / "state.json"
    monkeypatch.setenv("ARCHIVE_CONSOLE_STATE_PATH", str(state_path))
    from app import main as main_mod

    main_mod._state = None
    st = main_mod.load_state()
    st.archive_root = str(root)
    st.allowlisted_rel_prefixes = ["logs", "galleries"]
    main_mod.save_state(st, state_path)
    main_mod._state = st
    return TestClient(main_mod.app)


def test_settings_browse_host_rejects_unknown_kind(browse_client: TestClient) -> None:
    r = browse_client.post(
        "/api/settings/browse-host",
        json={"kind": "not_a_kind", "title": "x"},
    )
    assert r.status_code == 422


def test_settings_browse_host_file_picked(
    browse_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app import main as main_mod

    def fake_pick(_title: str, _initial: str | None = None) -> tuple[str, str]:
        return ("picked", r"C:\tools\ffmpeg.exe")

    monkeypatch.setattr(main_mod, "pick_file_host", fake_pick)
    r = browse_client.post(
        "/api/settings/browse-host",
        json={"kind": "file", "title": "Choose FFmpeg"},
    )
    assert r.status_code == 200
    j = r.json()
    assert j["kind"] == "file"
    assert j["path"].endswith("ffmpeg.exe")


def test_settings_browse_host_directory_picked(
    browse_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app import main as main_mod

    def fake_pick(_title: str, _initial: str | None = None) -> tuple[str, str]:
        return ("picked", r"<ARCHIVE_ROOT>")

    monkeypatch.setattr(main_mod, "pick_directory_host", fake_pick)
    r = browse_client.post(
        "/api/settings/browse-host",
        json={"kind": "directory", "title": "Archive root"},
    )
    assert r.status_code == 200
    j = r.json()
    assert j["kind"] == "directory"
    assert "scripts" in j["path"].replace("\\", "/")


def test_settings_browse_host_archive_relative_picked(
    browse_client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from app import main as main_mod

    quarantine = tmp_path / "ar" / "logs" / "_duplicates_quarantine"
    quarantine.mkdir(parents=True)

    def fake_pick(_title: str, _initial: str | None = None) -> tuple[str, str]:
        return ("picked", str(quarantine))

    monkeypatch.setattr(main_mod, "pick_directory_host", fake_pick)
    r = browse_client.post(
        "/api/settings/browse-host",
        json={"kind": "archive_relative", "title": "Quarantine"},
    )
    assert r.status_code == 200
    j = r.json()
    assert j["kind"] == "archive_relative"
    assert j["rel"] == "logs/_duplicates_quarantine"


def test_health_includes_settings_browse_kinds(browse_client: TestClient) -> None:
    r = browse_client.get("/api/health")
    assert r.status_code == 200
    kinds = r.json().get("settings_host_browse_kinds")
    assert kinds == ["file", "directory", "archive_relative"]
