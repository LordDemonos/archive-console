"""Rename folder browse API."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def rename_browse_folder_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> TestClient:
    root = tmp_path / "ar"
    (root / "playlists" / "arch").mkdir(parents=True)
    state_path = tmp_path / "state.json"
    monkeypatch.setenv("ARCHIVE_CONSOLE_STATE_PATH", str(state_path))
    from app import main as main_mod

    main_mod._state = None
    st = main_mod.load_state()
    st.archive_root = str(root)
    main_mod.save_state(st, state_path)
    main_mod._state = st
    return TestClient(main_mod.app)


def test_rename_browse_folder_picked(
    rename_browse_folder_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from app import main as main_mod

    picked = tmp_path / "ar" / "playlists" / "arch"

    def fake_pick(_title: str, initial: str | None = None) -> tuple[str, str]:
        return ("picked", str(picked))

    monkeypatch.setattr(main_mod, "pick_directory_host", fake_pick)
    r = rename_browse_folder_client.post(
        "/api/rename/browse-folder",
        json={"initial_path": "playlists/arch"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["folder_rel"] == "playlists/arch"


def test_browse_host_archive_relative_uses_archive_root_initial(
    rename_browse_folder_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from app import main as main_mod

    seen: list[str | None] = []
    picked = tmp_path / "ar" / "playlists" / "arch"

    def fake_pick(_title: str, initial: str | None = None) -> tuple[str, str]:
        seen.append(initial)
        return ("picked", str(picked))

    monkeypatch.setattr(main_mod, "pick_directory_host", fake_pick)
    r = rename_browse_folder_client.post(
        "/api/settings/browse-host",
        json={
            "kind": "archive_relative",
            "title": "Choose folder",
            "initial_path": "playlists/arch",
        },
    )
    assert r.status_code == 200, r.text
    assert seen == [str(picked.resolve())]
    assert r.json()["rel"] == "playlists/arch"
