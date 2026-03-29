"""Storage retention preview and cleanup."""

from __future__ import annotations

import os
import time
from pathlib import Path

from app.settings import ConsoleState, OperatorBackupConfig, StorageRetentionConfig
from app.storage_cleanup import build_preview, execute_cleanup


def _touch_dir_old(path: Path, age_sec: float) -> None:
    t = time.time() - age_sec
    os.utime(path, (t, t))


def _make_state(root: Path) -> ConsoleState:
    return ConsoleState(
        archive_root=str(root),
        allowlisted_rel_prefixes=["logs"],
        operator_backup=OperatorBackupConfig(
            destination_rel="logs/archive_console_backups",
        ),
        storage_retention=StorageRetentionConfig(
            retention_days=30,
            prune_archive_runs=True,
            prune_operator_backup_zips=True,
        ),
    )


def test_preview_counts_old_run_folders(tmp_path: Path) -> None:
    root = tmp_path / "ar"
    logs = root / "logs"
    d_old = logs / "archive_run_old"
    d_new = logs / "archive_run_new"
    d_old.mkdir(parents=True)
    d_new.mkdir(parents=True)
    _touch_dir_old(d_old, 40 * 86400)
    _touch_dir_old(d_new, 5 * 86400)

    st = _make_state(root)
    prev = build_preview(st)
    assert prev.archive_runs.count == 1
    assert prev.archive_runs.bytes >= 0


def test_preview_protects_pointer_target(tmp_path: Path) -> None:
    root = tmp_path / "ar"
    logs = root / "logs"
    prot = logs / "archive_run_protected"
    old = logs / "archive_run_old"
    prot.mkdir(parents=True)
    old.mkdir(parents=True)
    _touch_dir_old(prot, 90 * 86400)
    _touch_dir_old(old, 90 * 86400)

    ptr = logs / "latest_run.txt"
    ptr.write_text("logs/archive_run_protected\n", encoding="utf-8")

    st = _make_state(root)
    prev = build_preview(st)
    assert prev.archive_runs.count == 1
    rels = set(prev.archive_runs.items)
    assert "logs/archive_run_old" in rels
    assert "logs/archive_run_protected" not in rels
    assert prev.skipped_protected_pointer >= 1


def test_preview_operator_zips_old(tmp_path: Path) -> None:
    root = tmp_path / "ar"
    dest = root / "logs" / "archive_console_backups"
    dest.mkdir(parents=True)
    z_old = dest / "archive_console_backup_20200101T000000Z.zip"
    z_new = dest / "not_operator_backup.zip"
    z_old.write_bytes(b"x")
    z_new.write_bytes(b"y")
    _touch_dir_old(z_old, 90 * 86400)
    _touch_dir_old(z_new, 5 * 86400)

    st = _make_state(root)
    st = st.model_copy(
        update={
            "storage_retention": StorageRetentionConfig(retention_days=30),
        }
    )
    prev = build_preview(st)
    assert prev.operator_zips.count == 1


def test_execute_removes_only_eligible(tmp_path: Path) -> None:
    root = tmp_path / "ar"
    logs = root / "logs"
    d_old = logs / "archive_run_old"
    d_new = logs / "archive_run_new"
    d_old.mkdir(parents=True)
    d_new.mkdir(parents=True)
    (d_old / "x.txt").write_text("a", encoding="utf-8")
    _touch_dir_old(d_old, 90 * 86400)
    _touch_dir_old(d_new, 5 * 86400)

    st = _make_state(root)
    st = st.model_copy(
        update={
            "storage_retention": StorageRetentionConfig(retention_days=30),
        }
    )
    res = execute_cleanup(st)
    assert res["deleted_count"] == 1
    assert not d_old.exists()
    assert d_new.is_dir()


def test_execute_idempotent_second_pass(tmp_path: Path) -> None:
    root = tmp_path / "ar"
    logs = root / "logs"
    d_old = logs / "archive_run_old"
    d_old.mkdir(parents=True)
    _touch_dir_old(d_old, 90 * 86400)

    st = _make_state(root)
    st = st.model_copy(
        update={
            "storage_retention": StorageRetentionConfig(retention_days=30),
        }
    )
    execute_cleanup(st)
    res2 = execute_cleanup(st)
    assert res2["deleted_count"] == 0


def test_zip_glob_only_archive_console_backup_pattern(tmp_path: Path) -> None:
    root = tmp_path / "ar"
    dest = root / "logs" / "archive_console_backups"
    dest.mkdir(parents=True)
    other = dest / "other.zip"
    good = dest / "archive_console_backup_20200101T000000Z.zip"
    other.write_bytes(b"a")
    good.write_bytes(b"b")
    _touch_dir_old(other, 90 * 86400)
    _touch_dir_old(good, 90 * 86400)

    st = _make_state(root)
    prev = build_preview(st)
    assert prev.operator_zips.count == 1
    assert "archive_console_backup_" in prev.operator_zips.items[0]


def test_allowlist_no_logs_prefix_empty_candidates(tmp_path: Path) -> None:
    root = tmp_path / "ar"
    logs = root / "logs"
    d_old = logs / "archive_run_old"
    d_old.mkdir(parents=True)
    _touch_dir_old(d_old, 90 * 86400)

    st = ConsoleState(
        archive_root=str(root),
        allowlisted_rel_prefixes=["playlists"],
        storage_retention=StorageRetentionConfig(retention_days=30),
    )
    prev = build_preview(st)
    assert prev.archive_runs.count == 0
