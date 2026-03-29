"""Operator-initiated ZIP backups under archive_root (allowlist-enforced)."""

from __future__ import annotations

import logging
import shutil
import tempfile
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from .paths import PathNotAllowedError, assert_allowed_path, is_allowed, normalize_rel
from .settings import DEFAULT_STATE_PATH, LastOperatorBackup, ConsoleState

logger = logging.getLogger(__name__)

BACKUP_ZIP_GLOB = "archive_console_backup_*.zip"


def _apply_retention(dest_dir: Path, max_files: int, max_days: int) -> None:
    """Drop backups older than max_days (if >0), then keep only newest max_files."""
    now = time.time()
    paths = [p for p in dest_dir.glob(BACKUP_ZIP_GLOB) if p.is_file()]
    for p in paths:
        if max_days > 0 and (now - p.stat().st_mtime) > max_days * 86400:
            try:
                p.unlink()
            except OSError as e:
                logger.warning("retention delete failed %s: %s", p, e)
    paths = sorted(
        [p for p in dest_dir.glob(BACKUP_ZIP_GLOB) if p.is_file()],
        key=lambda x: x.stat().st_mtime,
        reverse=True,
    )
    for p in paths[max_files:]:
        try:
            p.unlink()
        except OSError as e:
            logger.warning("retention cap delete failed %s: %s", p, e)


def _add_tree(zf: zipfile.ZipFile, root: Path, tree_root: Path) -> None:
    if not tree_root.exists():
        return
    if tree_root.is_file():
        zf.write(tree_root, arcname=tree_root.relative_to(root).as_posix())
        return
    for fp in sorted(tree_root.rglob("*")):
        if fp.is_file():
            zf.write(fp, arcname=fp.relative_to(root).as_posix())


def run_operator_backup(st: ConsoleState) -> LastOperatorBackup:
    """Create a ZIP in destination_rel; update retention. Reads state snapshot only."""
    started = time.time()
    cfg = st.operator_backup
    root = Path(st.archive_root).expanduser().resolve()
    prefixes = st.allowlisted_rel_prefixes

    try:
        dest_dir = assert_allowed_path(root, cfg.destination_rel, prefixes)
        dest_dir.mkdir(parents=True, exist_ok=True)
    except PathNotAllowedError as e:
        return LastOperatorBackup(
            started_unix=started,
            finished_unix=time.time(),
            success=False,
            summary=f"forbidden destination: {e}",
        )
    except OSError as e:
        logger.warning("operator backup dest: %s", e)
        return LastOperatorBackup(
            started_unix=started,
            finished_unix=time.time(),
            success=False,
            summary="cannot create destination folder",
        )

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    zip_name = f"archive_console_backup_{stamp}.zip"
    tmp_path: Path | None = None
    try:
        fd, tmp_s = tempfile.mkstemp(suffix=".zip")
        tmp_path = Path(tmp_s)
        import os

        os.close(fd)
        with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zf:
            if cfg.include_state_json and DEFAULT_STATE_PATH.is_file():
                zf.write(DEFAULT_STATE_PATH, arcname="archive_console/state.json")
            if cfg.include_logs_dir:
                logs_full = root / "logs"
                if logs_full.is_dir() and is_allowed_logs(root, logs_full, prefixes):
                    _add_tree(zf, root, logs_full)
            for extra in cfg.include_extra_rel_prefixes:
                try:
                    er = normalize_rel(extra)
                except PathNotAllowedError:
                    continue
                if not er:
                    continue
                try:
                    p = assert_allowed_path(root, er, prefixes)
                except PathNotAllowedError:
                    continue
                _add_tree(zf, root, p)

        final_path = dest_dir / zip_name
        partial = dest_dir / (zip_name + ".partial")
        shutil.move(str(tmp_path), str(partial))
        partial.replace(final_path)
        tmp_path = None

        _apply_retention(dest_dir, cfg.retention_max_files, cfg.retention_days)
        rel = final_path.relative_to(root).as_posix()
        return LastOperatorBackup(
            started_unix=started,
            finished_unix=time.time(),
            success=True,
            summary=rel,
        )
    except Exception as e:
        logger.warning("operator backup failed: %s", e, exc_info=True)
        return LastOperatorBackup(
            started_unix=started,
            finished_unix=time.time(),
            success=False,
            summary="backup failed (see server log)",
        )
    finally:
        if tmp_path is not None:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass


def is_allowed_logs(root: Path, logs_path: Path, prefixes: list[str]) -> bool:
    try:
        logs_path.resolve().relative_to(root)
    except ValueError:
        return False
    return is_allowed(root, logs_path, prefixes)
