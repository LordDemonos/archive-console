"""Czkawka API routes."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def czk_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    root = tmp_path / "ar"
    root.mkdir()
    (root / "logs").mkdir()
    state_path = tmp_path / "state.json"
    monkeypatch.setenv("ARCHIVE_CONSOLE_STATE_PATH", str(state_path))
    from app import main as main_mod

    main_mod._state = None
    main_mod._czk_manager = None
    st = main_mod.load_state()
    st.archive_root = str(root)
    st.allowlisted_rel_prefixes = ["logs", "galleries"]
    main_mod.save_state(st, state_path)
    main_mod._state = st
    return TestClient(main_mod.app)


def test_czkawka_scan_requires_directory(czk_client: TestClient) -> None:
    r = czk_client.post("/api/czkawka/scan", json={"mode": "dup", "directories": []})
    assert r.status_code == 422 or r.status_code == 400


def test_czkawka_status_idle(czk_client: TestClient) -> None:
    r = czk_client.get("/api/czkawka/status")
    assert r.status_code == 200
    assert r.json().get("phase") == "idle"


def test_czkawka_suggested_paths(czk_client: TestClient) -> None:
    r = czk_client.get("/api/czkawka/suggested-paths")
    assert r.status_code == 200
    j = r.json()
    assert "galleries_abs" in j
    assert j["galleries_abs"]
    assert "galleries" in j["galleries_abs"].replace("\\", "/").lower()


def test_czkawka_reset_idle(czk_client: TestClient) -> None:
    r = czk_client.post("/api/czkawka/reset")
    assert r.status_code == 200
    j = r.json()
    assert j.get("ok") is True
    assert j.get("reset") is False
    assert j.get("stopped") is False


def test_czkawka_reset_stops_running_scan(czk_client: TestClient, monkeypatch) -> None:
    from app import main as main_mod
    from app.czkawka_scan_manager import CzkScanPhase, CzkScanState

    mgr = main_mod._get_czk_manager()
    mgr._current = CzkScanState(
        scan_id="stop1",
        phase=CzkScanPhase.running,
        started_unix=0,
        mode="dup",
        directories=["C:\\test"],
    )
    monkeypatch.setattr(mgr, "_kill_process", lambda _proc: None)

    r = czk_client.post("/api/czkawka/reset")
    assert r.status_code == 200
    j = r.json()
    assert j.get("stopped") is True
    assert mgr._current is not None
    assert mgr._current.phase == CzkScanPhase.failed
    assert "Stopped" in (mgr._current.error or "")
