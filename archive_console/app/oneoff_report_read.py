"""Read rolling one-off summary from disk (mirrors archive_oneoff_rolling fields)."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .file_serve import MEDIA_BY_SUFFIX, is_playable_media_path
from .paths import PathNotAllowedError, is_allowed, normalize_rel

REPORT_REL = "logs/oneoff_report/report.html"
JSONL_REL = "logs/oneoff_report/summary.jsonl"

_VIDEO_SUFFIXES = frozenset(
    ext for ext, mt in MEDIA_BY_SUFFIX.items() if mt.startswith("video/")
)


def _load_entries(archive_root: Path) -> list[dict[str, Any]]:
    p = archive_root / "logs" / "oneoff_report" / "summary.jsonl"
    if not p.is_file():
        return []
    rows: list[dict[str, Any]] = []
    text = p.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _abs_under_archive_to_rel(
    archive_root: Path,
    full: Path,
    allowed_prefixes: list[str],
) -> str | None:
    root = archive_root.resolve()
    try:
        full_r = full.expanduser().resolve()
    except OSError:
        return None
    try:
        rel = full_r.relative_to(root)
    except ValueError:
        return None
    if not full_r.is_file():
        return None
    if not is_playable_media_path(full_r):
        return None
    if not is_allowed(root, full_r, allowed_prefixes):
        return None
    rel_s = rel.as_posix()
    try:
        return normalize_rel(rel_s)
    except PathNotAllowedError:
        return None


def _media_path_to_rel(
    archive_root: Path,
    media_path: str,
    allowed_prefixes: list[str],
) -> str | None:
    s = (media_path or "").strip()
    if not s:
        return None
    return _abs_under_archive_to_rel(archive_root, Path(s), allowed_prefixes)


def _is_video_file(path: Path) -> bool:
    return path.suffix.lower() in _VIDEO_SUFFIXES


def _preferred_media_from_manifest(
    archive_root: Path,
    log_folder: str,
    allowed_prefixes: list[str],
) -> str | None:
    raw = (log_folder or "").strip().replace("\\", "/")
    if not raw:
        return None
    try:
        log_rel = normalize_rel(raw)
    except PathNotAllowedError:
        return None
    root = archive_root.resolve()
    manifest = (root / log_rel / "manifest.csv").resolve()
    try:
        manifest.relative_to(root)
    except ValueError:
        return None
    if not manifest.is_file():
        return None
    try:
        text = manifest.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    rows: list[dict[str, str]] = []
    try:
        for row in csv.DictReader(text.splitlines()):
            rows.append({str(k): str(v or "") for k, v in row.items()})
    except csv.Error:
        return None
    verified: list[dict[str, str]] = []
    for row in rows:
        st = (row.get("status") or "").strip()
        if not st.startswith("downloaded"):
            continue
        if (row.get("file_verified_ok") or "").strip() != "yes":
            continue
        verified.append(row)
    if not verified:
        return None
    video_candidates: list[str] = []
    other_candidates: list[str] = []
    for row in verified:
        fp = (row.get("filepath") or "").strip()
        if not fp:
            continue
        try:
            p = Path(fp).expanduser().resolve()
        except OSError:
            continue
        rel = _abs_under_archive_to_rel(archive_root, p, allowed_prefixes)
        if not rel:
            continue
        if _is_video_file(p):
            video_candidates.append(rel)
        else:
            other_candidates.append(rel)
    if video_candidates:
        return video_candidates[-1]
    if other_candidates:
        return other_candidates[-1]
    return None


def _media_rel_for_ok_entry(
    archive_root: Path,
    entry: dict[str, Any],
    allowed_prefixes: list[str],
) -> str | None:
    mf = _preferred_media_from_manifest(
        archive_root, str(entry.get("log_folder") or ""), allowed_prefixes
    )
    if mf:
        return mf
    return _media_path_to_rel(
        archive_root, str(entry.get("media_path") or ""), allowed_prefixes
    )


def last_ok_media_rel(
    archive_root: Path,
    entries: list[dict[str, Any]],
    allowed_prefixes: list[str],
) -> str | None:
    """Newest successful one-off row with an allowlisted playable file under archive_root."""
    for e in reversed(entries):
        if (e.get("outcome") or "") != "ok":
            continue
        rel = _media_rel_for_ok_entry(archive_root, e, allowed_prefixes)
        if rel:
            return rel
    return None


def rolling_stats(entries: list[dict[str, Any]]) -> dict[str, Any]:
    ok = sum(1 for e in entries if e.get("outcome") == "ok")
    fail = sum(1 for e in entries if e.get("outcome") == "fail")
    last = entries[-1] if entries else {}
    return {
        "total": len(entries),
        "ok": ok,
        "fail": fail,
        "last_url": last.get("url", ""),
        "last_completed_utc": last.get("completed_utc", ""),
        "last_outcome": last.get("outcome", ""),
    }


def oneoff_rolling_payload(
    archive_root: Path, allowed_prefixes: list[str]
) -> dict[str, Any]:
    root = archive_root.resolve()
    entries = _load_entries(root)
    report_path = root / "logs" / "oneoff_report" / "report.html"
    stats = rolling_stats(entries)
    stats["last_media_rel"] = last_ok_media_rel(root, entries, allowed_prefixes)
    return {
        "report_rel": REPORT_REL,
        "report_exists": report_path.is_file(),
        "stats": stats,
        "recent_entries": entries[-25:],
    }
