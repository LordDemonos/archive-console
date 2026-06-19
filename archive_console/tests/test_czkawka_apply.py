"""Czkawka apply removals."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.czkawka_apply import (
    CZKAWKA_APPLY_CONFIRM,
    apply_czkawka_removals,
    group_paths_index,
    path_key,
    prune_results_after_apply,
    validate_apply_items,
)


def test_group_paths_index() -> None:
    results = {
        "groups": [
            {
                "group_id": "100_0",
                "files": [{"path": r"C:\a\one.jpg"}, {"path": r"C:\a\two.jpg"}],
            }
        ]
    }
    idx = group_paths_index(results)
    assert "100_0" in idx
    assert len(idx["100_0"]) == 2


def test_validate_apply_items_rejects_unknown_path(tmp_path: Path) -> None:
    keep = tmp_path / "keep.bin"
    drop = tmp_path / "drop.bin"
    other = tmp_path / "other.bin"
    keep.write_bytes(b"x")
    drop.write_bytes(b"x")
    other.write_bytes(b"x")
    results = {
        "groups": [
            {
                "group_id": "g1",
                "files": [{"path": str(keep)}, {"path": str(drop)}],
            }
        ]
    }
    idx = group_paths_index(results)
    with pytest.raises(ValueError, match="not in scan group"):
        validate_apply_items(
            [
                {
                    "group_id": "g1",
                    "keep_path": str(keep),
                    "remove_paths": [str(other)],
                }
            ],
            group_index=idx,
        )


def test_apply_czkawka_removals_quarantine(tmp_path: Path) -> None:
    keep = tmp_path / "keep.bin"
    drop = tmp_path / "drop.bin"
    keep.write_bytes(b"same")
    drop.write_bytes(b"same")
    qdir = tmp_path / "quarantine"
    out = apply_czkawka_removals(
        items=[
            {
                "group_id": "g1",
                "keep_path": keep,
                "remove_paths": [drop],
            }
        ],
        mode="quarantine",
        quarantine_dir=qdir,
        dry_run=False,
    )
    assert out["removed_count"] == 1
    assert not drop.is_file()
    assert keep.is_file()
    assert any(qdir.iterdir())


def test_prune_results_after_apply() -> None:
    results = {
        "group_count": 1,
        "groups": [
            {
                "group_id": "g1",
                "files": [{"path": r"C:\a\keep.jpg"}, {"path": r"C:\a\gone.jpg"}],
            }
        ],
    }
    removed = {path_key(Path(r"C:\a\gone.jpg"))}
    out = prune_results_after_apply(results, removed)
    assert out["group_count"] == 0


@pytest.fixture()
def czk_apply_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    root = tmp_path / "ar"
    root.mkdir()
    (root / "logs" / "_czkawka_scans").mkdir(parents=True)
    state_path = tmp_path / "state.json"
    monkeypatch.setenv("ARCHIVE_CONSOLE_STATE_PATH", str(state_path))
    from app import main as main_mod

    main_mod._state = None
    main_mod._czk_manager = None
    st = main_mod.load_state()
    st.archive_root = str(root)
    st.allowlisted_rel_prefixes = ["logs"]
    main_mod.save_state(st, state_path)
    main_mod._state = st
    return TestClient(main_mod.app)


def test_czkawka_apply_api_dry_run(czk_apply_client: TestClient, tmp_path: Path) -> None:
    from app import main as main_mod
    from app.czkawka_scan_manager import CzkScanPhase, CzkScanState

    keep = tmp_path / "keep.bin"
    drop = tmp_path / "drop.bin"
    keep.write_bytes(b"z")
    drop.write_bytes(b"z")
    results = {
        "group_count": 1,
        "groups": [
            {
                "group_id": "g1",
                "files": [{"path": str(keep)}, {"path": str(drop)}],
            }
        ],
        "parse": "dup",
    }
    mgr = main_mod._get_czk_manager()
    mgr._current = CzkScanState(
        scan_id="abc123",
        phase=CzkScanPhase.success,
        started_unix=0,
        mode="dup",
        directories=[str(tmp_path)],
        results=results,
    )
    r = czk_apply_client.post(
        "/api/czkawka/apply",
        json={
            "scan_id": "abc123",
            "dry_run": True,
            "mode": "delete",
            "items": [
                {
                    "group_id": "g1",
                    "keep_path": str(keep),
                    "remove_paths": [str(drop)],
                }
            ],
        },
    )
    assert r.status_code == 200
    j = r.json()
    assert j["removed_count"] == 1
    assert drop.is_file()


def test_czkawka_apply_confirm_required(czk_apply_client: TestClient, tmp_path: Path) -> None:
    from app import main as main_mod
    from app.czkawka_scan_manager import CzkScanPhase, CzkScanState

    keep = tmp_path / "k.bin"
    drop = tmp_path / "d.bin"
    keep.write_bytes(b"1")
    drop.write_bytes(b"1")
    mgr = main_mod._get_czk_manager()
    mgr._current = CzkScanState(
        scan_id="x1",
        phase=CzkScanPhase.success,
        started_unix=0,
        mode="dup",
        directories=[str(tmp_path)],
        results={
            "groups": [
                {"group_id": "g1", "files": [{"path": str(keep)}, {"path": str(drop)}]}
            ]
        },
    )
    r = czk_apply_client.post(
        "/api/czkawka/apply",
        json={
            "scan_id": "x1",
            "dry_run": False,
            "mode": "delete",
            "items": [
                {
                    "group_id": "g1",
                    "keep_path": str(keep),
                    "remove_paths": [str(drop)],
                }
            ],
            "confirm": "",
        },
    )
    assert r.status_code == 400
    assert CZKAWKA_APPLY_CONFIRM in r.json()["detail"]
