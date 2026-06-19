"""Gallery source URL registry (galleries/gallery_sources.json)."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from .gallery_util import is_twitter_gallery_url, normalize_gallery_url, stable_row_id

_REDDIT_USER_SUBMITTED_SUFFIX = re.compile(
    r"^(https?://(?:www\.)?reddit\.com/user/[^/?#]+)/submitted/?(?=[?#]|$)",
    re.I,
)


def gallery_source_display_url(url: str) -> str:
    """UI-friendly URL; omits Reddit user ``/submitted/`` (still used internally for runs)."""
    u = (url or "").strip()
    if not u:
        return u
    m = _REDDIT_USER_SUBMITTED_SUFFIX.match(u)
    if m:
        return m.group(1)
    return u

GALLERY_SOURCES_REL = "galleries/gallery_sources.json"
GALLERY_SOURCES_TXT_REL = "galleries/gallery_sources.txt"
_SCHEMA_VERSION = 1


def gallery_sources_json_path(archive_root: Path) -> Path:
    return archive_root / GALLERY_SOURCES_REL


def gallery_sources_txt_path(archive_root: Path) -> Path:
    return archive_root / GALLERY_SOURCES_TXT_REL


def gallery_source_label(url: str) -> str:
    """Short display label, e.g. r/pics or u/name."""
    try:
        norm = normalize_gallery_url(url)
    except ValueError:
        return (url or "").strip()[:80] or "?"
    from urllib.parse import urlparse

    path = (urlparse(norm).path or "/").strip("/")
    parts = [p for p in path.split("/") if p]
    if len(parts) >= 2 and parts[0].lower() == "r":
        return f"r/{parts[1]}"
    if len(parts) >= 2 and parts[0].lower() == "user":
        return f"u/{parts[1]}"
    return path[:80] or norm[:80]


def _empty_store() -> dict[str, Any]:
    return {"schema_version": _SCHEMA_VERSION, "entries": []}


def load_gallery_sources(archive_root: Path) -> dict[str, Any]:
    path = gallery_sources_json_path(archive_root)
    if not path.is_file():
        return _empty_store()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _empty_store()
    if not isinstance(raw, dict):
        return _empty_store()
    entries = raw.get("entries")
    if not isinstance(entries, list):
        return _empty_store()
    return {
        "schema_version": int(raw.get("schema_version") or _SCHEMA_VERSION),
        "entries": [e for e in entries if isinstance(e, dict)],
    }


def _entry_index(entries: list[dict[str, Any]], entry_id: str) -> int:
    for i, e in enumerate(entries):
        if str(e.get("id") or "") == entry_id:
            return i
    return -1


def _write_store(archive_root: Path, store: dict[str, Any]) -> None:
    path = gallery_sources_json_path(archive_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    entries = store.get("entries")
    if not isinstance(entries, list):
        entries = []
    sorted_entries = sorted(
        entries,
        key=lambda e: (
            -(float(e.get("last_run_unix") or 0)),
            str(e.get("label") or e.get("url") or ""),
        ),
    )
    out = {
        "schema_version": _SCHEMA_VERSION,
        "entries": sorted_entries,
    }
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    txt = gallery_sources_txt_path(archive_root)
    lines = [str(e.get("url") or "").strip() for e in sorted_entries if e.get("url")]
    txt.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def upsert_gallery_source(
    archive_root: Path,
    url: str,
    *,
    url_input: str | None = None,
    run_id: str | None = None,
    exit_code: int | None = None,
    started_unix: float | None = None,
    touch_only: bool = False,
) -> dict[str, Any]:
    """
    Add or update a source URL. When ``touch_only`` is False and run metadata is
    provided, increments ``run_count`` and updates last-run fields.

    ``url`` is the canonical normalized URL used for re-runs. ``url_input`` is
    optional text the operator typed when it differs cosmetically (e.g. before
    ``/submitted/`` is appended for Reddit user profiles).
    """
    norm = normalize_gallery_url(url)
    raw_in = (url_input or "").strip()
    now = time.time()
    entry_id = stable_row_id(norm)
    store = load_gallery_sources(archive_root)
    entries: list[dict[str, Any]] = list(store.get("entries") or [])
    ix = _entry_index(entries, entry_id)
    if ix >= 0:
        row = dict(entries[ix])
    else:
        row = {
            "id": entry_id,
            "url": norm,
            "label": gallery_source_label(norm),
            "first_added_unix": now,
            "first_run_unix": None,
            "last_run_unix": None,
            "last_exit_code": None,
            "last_run_id": None,
            "run_count": 0,
        }
        entries.append(row)
        ix = len(entries) - 1

    row["url"] = norm
    row["label"] = gallery_source_label(norm)
    if raw_in and raw_in.rstrip("/") != norm.rstrip("/"):
        row["url_input"] = raw_in

    if not touch_only and run_id is not None:
        ts = float(started_unix if started_unix is not None else now)
        if row.get("first_run_unix") is None:
            row["first_run_unix"] = ts
        row["last_run_unix"] = ts
        row["last_exit_code"] = exit_code
        row["last_run_id"] = run_id
        row["run_count"] = int(row.get("run_count") or 0) + 1
    elif touch_only and ix < 0:
        row["first_added_unix"] = now

    entries[ix] = row
    store["entries"] = entries
    _write_store(archive_root, store)
    return row


def record_gallery_source_after_run(archive_root: Path, finished: Any) -> None:
    """Append/update saved sources after a **successful** Galleries run only."""
    from .run_manager import RunPhase

    if finished is None or getattr(finished, "job", None) != "galleries":
        return
    if getattr(finished, "dry_run", False):
        return
    if getattr(finished, "phase", None) == RunPhase.canceled:
        return
    exit_code = getattr(finished, "exit_code", None)
    if exit_code not in (0, 4):
        return
    meta = getattr(finished, "run_meta", None) or {}
    gurl = (meta.get("gallery_url") or "").strip()
    if not gurl:
        return
    url_input = (meta.get("gallery_url_input") or "").strip() or None
    upsert_gallery_source(
        archive_root,
        gurl,
        url_input=url_input,
        run_id=getattr(finished, "run_id", None),
        exit_code=exit_code,
        started_unix=getattr(finished, "started_unix", None),
    )


def remove_gallery_sources(archive_root: Path, ids: list[str]) -> int:
    want = {i.strip() for i in ids if i and i.strip()}
    if not want:
        return 0
    store = load_gallery_sources(archive_root)
    entries = store.get("entries") or []
    if not isinstance(entries, list):
        return 0
    kept = [e for e in entries if isinstance(e, dict) and str(e.get("id") or "") not in want]
    removed = len(entries) - len(kept)
    if removed:
        store["entries"] = kept
        _write_store(archive_root, store)
    return removed


def iter_gallery_sources_for_run(
    archive_root: Path,
    *,
    deprioritize_twitter: bool = False,
) -> list[tuple[str, str | None]]:
    """Saved sources in list order (same sort as API): (canonical url, url_input|None)."""
    api = list_gallery_sources_for_api(archive_root)
    out: list[tuple[str, str | None]] = []
    seen: set[str] = set()
    for e in api.get("entries") or []:
        if not isinstance(e, dict):
            continue
        url = str(e.get("url") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        raw_in = str(e.get("url_input") or "").strip() or None
        out.append((url, raw_in))
    if deprioritize_twitter and len(out) > 1:
        non_tw = [row for row in out if not is_twitter_gallery_url(row[0])]
        tw = [row for row in out if is_twitter_gallery_url(row[0])]
        if tw and non_tw:
            out = non_tw + tw
    return out


def list_gallery_sources_for_api(archive_root: Path) -> dict[str, Any]:
    store = load_gallery_sources(archive_root)
    entries = list(store.get("entries") or [])
    entries.sort(
        key=lambda e: (
            -(float(e.get("last_run_unix") or e.get("first_added_unix") or 0)),
            str(e.get("label") or ""),
        ),
    )
    for e in entries:
        if isinstance(e, dict):
            raw = str(e.get("url_input") or e.get("url") or "")
            e["url_display"] = gallery_source_display_url(raw)
    return {
        "schema_version": store.get("schema_version", _SCHEMA_VERSION),
        "json_rel": GALLERY_SOURCES_REL,
        "txt_rel": GALLERY_SOURCES_TXT_REL,
        "entries": entries,
    }
