"""Rotated backups under archive_console/backups/."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from .settings import CONSOLE_DIR

BACKUP_DIR = CONSOLE_DIR / "backups"
# Safe chunk of original filename for glob (no path sep)
_SAFE_NAME = re.compile(r"^[\w.\-]+$")


def backup_filename_stem(editor_basename: str) -> str:
    if not _SAFE_NAME.match(editor_basename):
        raise ValueError("invalid backup stem")
    return editor_basename


def rotate_backups(
    editor_basename: str,
    max_keep: int,
) -> None:
    if max_keep < 1:
        return
    stem = backup_filename_stem(editor_basename)
    pattern = f"{stem}.*.bak"
    candidates = sorted(
        BACKUP_DIR.glob(pattern),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for old in candidates[max_keep:]:
        try:
            old.unlink(missing_ok=True)
        except OSError:
            pass


def write_backup_copy(src: Path, editor_basename: str, max_keep: int) -> Path | None:
    """If src exists, copy to backups/<name>.<iso>.bak and rotate. Returns new path or None."""
    if not src.is_file():
        return None
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stem = backup_filename_stem(editor_basename)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = BACKUP_DIR / f"{stem}.{ts}.bak"
    dest.write_bytes(src.read_bytes())
    rotate_backups(editor_basename, max_keep)
    return dest

