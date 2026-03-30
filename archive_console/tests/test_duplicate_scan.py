"""Duplicate scan: hashing, grouping, apply dry-run, API allowlist."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.duplicate_scan import apply_duplicate_removals, find_duplicate_groups
from app.main import app
import app.main as main


@pytest.fixture
def dup_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import app.settings as sm

    ar = tmp_path / "archive"
    ar.mkdir()
    (ar / "videos").mkdir(parents=True)
    st_path = tmp_path / "state.json"
    st_path.write_text(
        json.dumps(
            {
                "host": "127.0.0.1",
                "port": 8756,
                "archive_root": str(ar),
                "allowlisted_rel_prefixes": ["videos", "logs"],
                "duplicates_quarantine_rel": "logs/_dup_q",
                "duplicates_prefer_quarantine": True,
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
    main._dup_manager = None
    with TestClient(app) as client:
        yield client, ar


def test_find_duplicate_groups_identical_bytes(tmp_path: Path) -> None:
    root = tmp_path / "ar"
    root.mkdir()
    d = root / "videos"
    d.mkdir()
    content = b"hello world identical"
    (d / "a.mp4").write_bytes(content)
    (d / "b.mp4").write_bytes(content)
    (d / "c.mp4").write_bytes(b"different")
    groups, stats = find_duplicate_groups(
        root,
        ["videos"],
        ["videos"],
        include_video=True,
        include_images=False,
    )
    assert stats["duplicate_groups"] == 1
    assert len(groups) == 1
    rels = sorted(f["rel"] for f in groups[0].files)
    assert rels == ["videos/a.mp4", "videos/b.mp4"]


def test_find_duplicate_groups_same_size_different_content(tmp_path: Path) -> None:
    root = tmp_path / "ar"
    root.mkdir()
    d = root / "videos"
    d.mkdir()
    (d / "a.mp4").write_bytes(b"x" * 100)
    (d / "b.mp4").write_bytes(b"y" * 100)
    groups, _stats = find_duplicate_groups(
        root,
        ["videos"],
        ["videos"],
        include_video=True,
        include_images=False,
    )
    assert len(groups) == 0


def test_find_duplicate_groups_empty_files(tmp_path: Path) -> None:
    root = tmp_path / "ar"
    root.mkdir()
    d = root / "videos"
    d.mkdir()
    (d / "e1.mp4").write_bytes(b"")
    (d / "e2.mp4").write_bytes(b"")
    groups, stats = find_duplicate_groups(
        root,
        ["videos"],
        ["videos"],
        include_video=True,
        include_images=False,
    )
    assert stats["duplicate_groups"] == 1
    assert len(groups[0].files) == 2


def test_apply_duplicate_removals_dry_run_no_disk_change(tmp_path: Path) -> None:
    root = tmp_path / "ar"
    root.mkdir()
    d = root / "videos"
    d.mkdir()
    (d / "keep.mp4").write_bytes(b"a")
    (d / "drop.mp4").write_bytes(b"a")
    out = apply_duplicate_removals(
        root,
        ["videos"],
        [{"keep_rel": "videos/keep.mp4", "remove_rels": ["videos/drop.mp4"]}],
        "delete",
        "logs/_dup_q",
        dry_run=True,
    )
    assert out["removed_count"] == 1
    assert (d / "drop.mp4").is_file()
    assert (d / "keep.mp4").is_file()


def test_apply_duplicate_removals_quarantine(tmp_path: Path) -> None:
    root = tmp_path / "ar"
    root.mkdir()
    (root / "videos").mkdir()
    (root / "logs" / "_dup_q").mkdir(parents=True)
    (root / "videos" / "keep.mp4").write_bytes(b"z")
    (root / "videos" / "drop.mp4").write_bytes(b"z")
    out = apply_duplicate_removals(
        root,
        ["videos", "logs"],
        [{"keep_rel": "videos/keep.mp4", "remove_rels": ["videos/drop.mp4"]}],
        "quarantine",
        "logs/_dup_q",
        dry_run=False,
    )
    assert out["removed_count"] == 1
    assert not (root / "videos" / "drop.mp4").is_file()
    qdir = root / "logs" / "_dup_q"
    assert any(qdir.iterdir())


def test_duplicates_apply_api_403_bad_path(dup_env) -> None:
    client, ar = dup_env
    (ar / "videos" / "keep403.mp4").write_bytes(b"k")
    r = client.post(
        "/api/duplicates/apply",
        json={
            "dry_run": True,
            "mode": "delete",
            "items": [
                {"keep_rel": "videos/keep403.mp4", "remove_rels": ["secrets/x.mp4"]},
            ],
            "confirm": "",
        },
    )
    assert r.status_code == 403


def test_duplicates_apply_confirm_required(dup_env) -> None:
    client, ar = dup_env
    (ar / "videos" / "k.mp4").write_bytes(b"1")
    (ar / "videos" / "d.mp4").write_bytes(b"2")
    r = client.post(
        "/api/duplicates/apply",
        json={
            "dry_run": False,
            "mode": "delete",
            "items": [
                {"keep_rel": "videos/k.mp4", "remove_rels": ["videos/d.mp4"]},
            ],
            "confirm": "",
        },
    )
    assert r.status_code == 400


def test_duplicates_scan_api(dup_env) -> None:
    client, ar = dup_env
    (ar / "videos" / "a.mp4").write_bytes(b"dup")
    (ar / "videos" / "b.mp4").write_bytes(b"dup")
    r = client.post(
        "/api/duplicates/scan",
        json={
            "root_rels": ["videos"],
            "include_video": True,
            "include_images": False,
        },
    )
    assert r.status_code == 200
    import time

    for _ in range(40):
        st = client.get("/api/duplicates/status").json()
        if st.get("phase") != "running":
            break
        time.sleep(0.1)
    st = client.get("/api/duplicates/status").json()
    assert st.get("phase") == "success"
    scan = st.get("scan") or {}
    groups = scan.get("groups") or []
    assert len(groups) >= 1
