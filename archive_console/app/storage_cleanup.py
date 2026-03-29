"""Preview and execute retention cleanup under archive_root (allowlist only)."""

from __future__ import annotations

import logging
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .latest_pointer import LATEST_POINTER_REL, read_latest_run_folder_rel
from .operator_backup import BACKUP_ZIP_GLOB
from .paths import PathNotAllowedError, assert_allowed_path, is_allowed
from .settings import ConsoleState, StorageRetentionConfig

logger = logging.getLogger(__name__)

ARCHIVE_RUN_PREFIX = "archive_run_"


def _protected_pointer_targets(archive_root: Path) -> set[str]:
    """Relative posix paths pointed to by latest_run*.txt (may be missing on disk)."""
    out: set[str] = set()
    for job in LATEST_POINTER_REL:
        rel = read_latest_run_folder_rel(archive_root, job)
        if rel:
            out.add(rel.replace("\\", "/"))
    return out


def _active_run_folder_rel(
    archive_root: Path,
    *,
    running_log_folder_rel: str | None,
) -> set[str]:
    if not running_log_folder_rel:
        return set()
    p = (archive_root / running_log_folder_rel).resolve()
    root = archive_root.resolve()
    try:
        rel = p.relative_to(root).as_posix()
    except ValueError:
        return set()
    return {rel}


@dataclass
class CategoryPreview:
    count: int = 0
    bytes: int = 0
    items: list[str] = field(default_factory=list)
    max_sample: int = 200


@dataclass
class CleanupPreview:
    retention_days: int
    cutoff_unix: float
    archive_runs: CategoryPreview = field(default_factory=CategoryPreview)
    operator_zips: CategoryPreview = field(default_factory=CategoryPreview)
    skipped_protected_pointer: int = 0
    skipped_active_run: int = 0


def _dir_size_bytes(path: Path) -> int:
    total = 0
    try:
        for sub in path.rglob("*"):
            if sub.is_file():
                try:
                    total += sub.stat().st_size
                except OSError:
                    pass
    except OSError:
        pass
    return total


def _collect_archive_run_candidates(
    root: Path,
    prefixes: list[str],
    cutoff: float,
    ptr_targets: set[str],
    active: set[str],
    sample_limit: int,
) -> tuple[list[Path], int, int, int]:
    """paths to delete, total bytes, skipped (pointer target), skipped (active run)."""
    logs = root / "logs"
    if not logs.is_dir():
        return [], 0, 0, 0
    if not is_allowed(root, logs, prefixes):
        return [], 0, 0, 0

    dirs: list[tuple[Path, float, str]] = []
    skipped_ptr = 0
    skipped_active = 0
    for child in logs.iterdir():
        if not child.is_dir():
            continue
        if not child.name.startswith(ARCHIVE_RUN_PREFIX):
            continue
        if not is_allowed(root, child, prefixes):
            continue
        try:
            rel = child.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            continue
        if rel in ptr_targets:
            skipped_ptr += 1
            continue
        if rel in active:
            skipped_active += 1
            continue
        try:
            mtime = child.stat().st_mtime
        except OSError:
            continue
        if mtime >= cutoff:
            continue
        dirs.append((child, mtime, rel))

    dirs.sort(key=lambda x: x[1], reverse=True)
    paths = [d[0] for d in dirs]
    total_bytes = sum(_dir_size_bytes(p) for p in paths)
    return paths, total_bytes, skipped_ptr, skipped_active


def _collect_zip_candidates(
    root: Path,
    dest_rel: str,
    prefixes: list[str],
    cutoff: float,
    sample_limit: int,
) -> tuple[list[Path], int]:
    try:
        dest = assert_allowed_path(root, dest_rel, prefixes)
    except PathNotAllowedError:
        return [], 0
    if not dest.is_dir():
        return [], 0
    zips: list[tuple[Path, float]] = []
    for z in dest.glob(BACKUP_ZIP_GLOB):
        if not z.is_file():
            continue
        if not is_allowed(root, z, prefixes):
            continue
        try:
            mtime = z.stat().st_mtime
        except OSError:
            continue
        if mtime >= cutoff:
            continue
        zips.append((z, mtime))
    zips.sort(key=lambda x: x[1], reverse=True)
    paths = [x[0] for x in zips]
    total = 0
    for p in paths:
        try:
            if p.is_file():
                total += p.stat().st_size
        except OSError:
            pass
    return paths, total


def build_preview(
    st: ConsoleState,
    *,
    cfg: StorageRetentionConfig | None = None,
    running_log_folder_rel: str | None = None,
    sample_limit: int = 200,
) -> CleanupPreview:
    cfg = cfg or st.storage_retention
    root = Path(st.archive_root).expanduser().resolve()
    prefixes = st.allowlisted_rel_prefixes
    now = time.time()
    cutoff = now - cfg.retention_days * 86400

    ptr_targets = _protected_pointer_targets(root)
    active = _active_run_folder_rel(root, running_log_folder_rel=running_log_folder_rel)

    prev = CleanupPreview(retention_days=cfg.retention_days, cutoff_unix=cutoff)

    if cfg.prune_archive_runs:
        paths, b, skp, ska = _collect_archive_run_candidates(
            root, prefixes, cutoff, ptr_targets, active, sample_limit
        )
        prev.archive_runs.count = len(paths)
        prev.archive_runs.bytes = b
        prev.archive_runs.items = [
            p.resolve().relative_to(root).as_posix() for p in paths[:sample_limit]
        ]
        prev.skipped_protected_pointer = skp
        prev.skipped_active_run = ska

    if cfg.prune_operator_backup_zips:
        zpaths, zb = _collect_zip_candidates(
            root,
            st.operator_backup.destination_rel,
            prefixes,
            cutoff,
            sample_limit,
        )
        prev.operator_zips.count = len(zpaths)
        prev.operator_zips.bytes = zb
        prev.operator_zips.items = [
            z.resolve().relative_to(root).as_posix() for z in zpaths[:sample_limit]
        ]

    return prev


def _repair_pointers_if_broken(archive_root: Path) -> int:
    """Clear pointer files whose target no longer exists. Returns count cleared."""
    cleared = 0
    root = archive_root.resolve()
    for rel_file in LATEST_POINTER_REL.values():
        p = root / rel_file
        if not p.is_file():
            continue
        raw = p.read_text(encoding="utf-8", errors="replace").strip()
        if not raw:
            continue
        target = Path(raw).expanduser()
        if not target.is_absolute():
            target = (root / raw).resolve()
        else:
            target = target.resolve()
        try:
            target.relative_to(root)
        except ValueError:
            p.write_text("", encoding="utf-8")
            cleared += 1
            continue
        if not target.exists():
            p.write_text("", encoding="utf-8")
            cleared += 1
    return cleared


def execute_cleanup(
    st: ConsoleState,
    *,
    cfg: StorageRetentionConfig | None = None,
    running_log_folder_rel: str | None = None,
) -> dict[str, Any]:
    """Delete eligible paths; best-effort per item. Returns summary dict."""
    cfg = cfg or st.storage_retention
    root = Path(st.archive_root).expanduser().resolve()
    prefixes = st.allowlisted_rel_prefixes
    t0 = time.time()
    cutoff = time.time() - cfg.retention_days * 86400

    ptr_targets = _protected_pointer_targets(root)
    active = _active_run_folder_rel(root, running_log_folder_rel=running_log_folder_rel)

    deleted = 0
    bytes_freed = 0
    errors: list[str] = []

    if cfg.prune_archive_runs:
        paths, _, _, _ = _collect_archive_run_candidates(
            root, prefixes, cutoff, ptr_targets, active, 999999
        )
        for d in paths:
            b = _dir_size_bytes(d)
            try:
                shutil.rmtree(d)
                deleted += 1
                bytes_freed += b
            except OSError as e:
                errors.append(f"{d.name}: {e}")

    if cfg.prune_operator_backup_zips:
        zpaths, _ = _collect_zip_candidates(
            root,
            st.operator_backup.destination_rel,
            prefixes,
            cutoff,
            999999,
        )
        for z in zpaths:
            try:
                sz = z.stat().st_size if z.is_file() else 0
            except OSError:
                sz = 0
            try:
                z.unlink()
                deleted += 1
                bytes_freed += sz
            except OSError as e:
                errors.append(f"{z.name}: {e}")

    cleared_ptrs = _repair_pointers_if_broken(root)
    duration_s = round(time.time() - t0, 3)

    logger.info(
        "storage_cleanup summary deleted=%s bytes_freed=%s errors=%s "
        "pointers_cleared=%s duration_s=%s retention_days=%s",
        deleted,
        bytes_freed,
        len(errors),
        cleared_ptrs,
        duration_s,
        cfg.retention_days,
    )

    return {
        "deleted_count": deleted,
        "bytes_freed": bytes_freed,
        "errors": errors,
        "pointers_cleared": cleared_ptrs,
        "duration_s": duration_s,
    }


def preview_to_api_dict(prev: CleanupPreview) -> dict[str, Any]:
    return {
        "retention_days": prev.retention_days,
        "cutoff_unix": prev.cutoff_unix,
        "categories": {
            "archive_runs": {
                "count": prev.archive_runs.count,
                "bytes": prev.archive_runs.bytes,
                "items_sample": prev.archive_runs.items,
            },
            "operator_zips": {
                "count": prev.operator_zips.count,
                "bytes": prev.operator_zips.bytes,
                "items_sample": prev.operator_zips.items,
            },
        },
        "skipped_protected_pointer": prev.skipped_protected_pointer,
        "skipped_active_run": prev.skipped_active_run,
    }
