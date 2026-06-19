"""Rename queue multi-file browse API."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def rename_browse_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    root = tmp_path / "ar"
    root.mkdir()
    (root / "galleries").mkdir()
    state_path = tmp_path / "state.json"
    monkeypatch.setenv("ARCHIVE_CONSOLE_STATE_PATH", str(state_path))
    from app import main as main_mod

    main_mod._state = None
    st = main_mod.load_state()
    st.archive_root = str(root)
    st.allowlisted_rel_prefixes = ["galleries", "logs"]
    main_mod.save_state(st, state_path)
    main_mod._state = st
    return TestClient(main_mod.app)


def test_rename_browse_files_picked(
    rename_browse_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from app import main as main_mod

    a = tmp_path / "ar" / "galleries" / "a.jpg"
    b = tmp_path / "ar" / "galleries" / "b.jpg"
    a.write_bytes(b"x")
    b.write_bytes(b"y")
    outside = tmp_path / "outside.jpg"
    outside.write_bytes(b"z")

    def fake_pick(_title: str, _initial: str | None = None) -> tuple[str, list[str]]:
        return ("picked", [str(a), str(b), str(outside)])

    monkeypatch.setattr(main_mod, "pick_files_host", fake_pick)
    r = rename_browse_client.post("/api/rename/browse-files", json={})
    assert r.status_code == 200
    j = r.json()
    assert j["rels"] == ["galleries/a.jpg", "galleries/b.jpg"]
    assert len(j["skipped"]) == 1
    assert "outside archive" in j["skipped"][0]["reason"]


def test_rename_browse_files_cancelled(
    rename_browse_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app import main as main_mod

    def fake_pick(_title: str, _initial: str | None = None) -> tuple[str, list[str]]:
        return ("cancelled", [])

    monkeypatch.setattr(main_mod, "pick_files_host", fake_pick)
    r = rename_browse_client.post("/api/rename/browse-files", json={})
    assert r.status_code == 204


def test_rename_browse_files_all_skipped(
    rename_browse_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from app import main as main_mod

    outside = tmp_path / "outside.jpg"
    outside.write_bytes(b"z")

    def fake_pick(_title: str, _initial: str | None = None) -> tuple[str, list[str]]:
        return ("picked", [str(outside)])

    monkeypatch.setattr(main_mod, "pick_files_host", fake_pick)
    r = rename_browse_client.post("/api/rename/browse-files", json={})
    assert r.status_code == 400
    assert "allowlist" in r.json()["detail"].lower() or "archive" in r.json()["detail"].lower()


def test_rename_browse_files_unavailable(
    rename_browse_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app import main as main_mod

    def fake_pick(_title: str, _initial: str | None = None) -> tuple[str, list[str]]:
        return ("unavailable", [])

    monkeypatch.setattr(main_mod, "pick_files_host", fake_pick)
    r = rename_browse_client.post("/api/rename/browse-files", json={})
    assert r.status_code == 503
