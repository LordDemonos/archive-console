"""Path allowlist: traversal-safe resolution under archive_root."""

from __future__ import annotations

import os
import re
from pathlib import Path


class PathNotAllowedError(ValueError):
    """Resolved path is outside allowlist or root."""


_WINDOWS_DEVICE = re.compile(r"^\\\\.[\\/](glob|)\.", re.I)


def _is_windows_reserved(p: Path) -> bool:
    if os.name != "nt":
        return False
    s = str(p)
    if _WINDOWS_DEVICE.search(s):
        return True
    return False


def normalize_rel(rel: str) -> str:
    """Normalize a relative path fragment; reject empty after norm and '..'."""
    if rel is None:
        raise PathNotAllowedError("missing path")
    rel = rel.strip().replace("\\", "/")
    if not rel or rel == ".":
        return ""
    parts: list[str] = []
    for seg in Path(rel).parts:
        if seg in (".", ""):
            continue
        if seg == "..":
            raise PathNotAllowedError("path traversal")
        parts.append(seg)
    return str(Path(*parts)).replace("\\", "/")


def resolve_under_root(archive_root: Path, rel: str) -> Path:
    """Resolve rel under archive_root; must stay under root after resolve()."""
    root = archive_root.resolve()
    rel_n = normalize_rel(rel)
    target = (root / rel_n).resolve()
    if _is_windows_reserved(target):
        raise PathNotAllowedError("reserved path")
    try:
        target.relative_to(root)
    except ValueError as e:
        raise PathNotAllowedError("outside archive root") from e
    return target


def is_allowed(
    archive_root: Path,
    full: Path,
    allowed_prefixes: list[str],
) -> bool:
    """
    full must be under archive_root; relative path must match one of allowed_prefixes.
    Prefix "" matches only the root directory itself (for listing virtual roots).
    """
    root = archive_root.resolve()
    full_r = full.resolve()
    try:
        rel = full_r.relative_to(root)
    except ValueError:
        return False
    rel_pos = rel.as_posix()
    if rel_pos == ".":
        return "" in allowed_prefixes
    rel_lower = rel_pos.lower()
    for pref in allowed_prefixes:
        if pref == "":
            continue
        pl = pref.strip("/").replace("\\", "/").lower()
        if rel_lower == pl or rel_lower.startswith(pl + "/"):
            return True
    return False


def assert_allowed_path(
    archive_root: Path,
    rel: str,
    allowed_prefixes: list[str],
) -> Path:
    full = resolve_under_root(archive_root, rel)
    if not is_allowed(archive_root, full, allowed_prefixes):
        raise PathNotAllowedError("not on allowlist")
    return full
