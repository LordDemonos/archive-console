"""Folder-scoped rename batch: enumerate candidates and skip already-done files."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .paths import PathNotAllowedError, assert_allowed_path, normalize_rel
from .rename_pipeline import RenamePreviewOptions

# Sidecars / incomplete downloads — not rename targets in folder batch.
_SKIP_SUFFIXES = frozenset({".json", ".description", ".ytdl", ".part"})
_MAX_ENUMERATE = 50_000


def pipeline_fingerprint(
    opt: RenamePreviewOptions,
    *,
    target_lang: str,
    source_lang: str,
    endpoint_mode: str,
) -> str:
    payload = {
        "opt": opt.model_dump(),
        "target_lang": (target_lang or "").strip(),
        "source_lang": (source_lang or "").strip(),
        "endpoint_mode": (endpoint_mode or "auto").strip(),
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def _is_rename_candidate(path: Path) -> bool:
    name = path.name
    if not name or name.startswith("."):
        return False
    lower = name.lower()
    if lower.endswith(".part"):
        return False
    suf = path.suffix.lower()
    if suf in _SKIP_SUFFIXES:
        return False
    return path.is_file()


def collect_rename_rels_under_dir(
    archive_root: Path,
    folder_rel: str,
    allowed_prefixes: list[str],
    *,
    recursive: bool = True,
    max_files: int = _MAX_ENUMERATE,
) -> list[str]:
    """List archive-relative file paths under folder_rel (sorted)."""
    rel_n = normalize_rel(folder_rel)
    if not rel_n:
        raise PathNotAllowedError("folder path is empty")
    folder = assert_allowed_path(archive_root, rel_n, allowed_prefixes)
    if not folder.is_dir():
        raise PathNotAllowedError("not a directory")

    cap = max(1, min(int(max_files), _MAX_ENUMERATE))
    out: list[str] = []
    root = archive_root.resolve()
    prefix = rel_n.rstrip("/") + "/"

    if recursive:
        iterator = folder.rglob("*")
    else:
        iterator = folder.iterdir()

    for path in sorted(iterator, key=lambda p: p.as_posix().lower()):
        if len(out) >= cap:
            break
        if not _is_rename_candidate(path):
            continue
        try:
            rel = path.resolve().relative_to(root).as_posix()
        except ValueError:
            continue
        if rel == rel_n or not rel.startswith(prefix):
            continue
        try:
            assert_allowed_path(archive_root, rel, allowed_prefixes)
        except PathNotAllowedError:
            continue
        out.append(rel)
    return out


def done_new_rels_for_batch(
    log: list[dict[str, Any]],
    *,
    folder_rel: str,
    pipeline_fp: str,
) -> set[str]:
    """Paths already successfully processed (destination rel) for folder + pipeline."""
    folder = normalize_rel(folder_rel).rstrip("/")
    if not folder:
        return set()
    prefix = folder + "/"
    done: set[str] = set()
    for entry in log:
        if str(entry.get("pipeline_fp") or "") != pipeline_fp:
            continue
        if str(entry.get("folder_rel") or "").rstrip("/") != folder:
            continue
        if str(entry.get("status") or "") not in ("ok", "skip"):
            continue
        new_rel = str(entry.get("new_rel") or entry.get("old_rel") or "").replace(
            "\\", "/"
        )
        if not new_rel:
            continue
        if new_rel == folder or new_rel.startswith(prefix):
            done.add(new_rel)
    return done


def partition_pending_rels(
    rels: list[str],
    done_new: set[str],
) -> tuple[list[str], int]:
    pending: list[str] = []
    skipped = 0
    for rel in rels:
        if rel in done_new:
            skipped += 1
            continue
        pending.append(rel)
    return pending, skipped


def folder_candidates_payload(
    *,
    archive_root: Path,
    allowed_prefixes: list[str],
    folder_rel: str,
    done_log: list[dict[str, Any]],
    opt: RenamePreviewOptions,
    target_lang: str,
    source_lang: str,
    endpoint_mode: str,
    recursive: bool = True,
    skip_done: bool = True,
    max_files: int = _MAX_ENUMERATE,
) -> dict[str, Any]:
    rel_n = normalize_rel(folder_rel)
    fp = pipeline_fingerprint(
        opt,
        target_lang=target_lang,
        source_lang=source_lang,
        endpoint_mode=endpoint_mode,
    )
    all_rels = collect_rename_rels_under_dir(
        archive_root,
        rel_n,
        allowed_prefixes,
        recursive=recursive,
        max_files=max_files,
    )
    done_new = done_new_rels_for_batch(
        done_log,
        folder_rel=rel_n,
        pipeline_fp=fp,
    )
    if skip_done:
        pending, skipped_done = partition_pending_rels(all_rels, done_new)
    else:
        pending, skipped_done = all_rels, 0
    log_for_batch = sum(
        1
        for e in done_log
        if str(e.get("folder_rel") or "").rstrip("/") == rel_n.rstrip("/")
        and str(e.get("pipeline_fp") or "") == fp
    )
    return {
        "folder_rel": rel_n,
        "pipeline_fp": fp,
        "recursive": recursive,
        "total_in_folder": len(all_rels),
        "skipped_done": skipped_done,
        "pending_rels": pending,
        "pending_count": len(pending),
        "done_log_entries": log_for_batch,
        "max_enumerate": max(1, min(int(max_files), _MAX_ENUMERATE)),
    }
