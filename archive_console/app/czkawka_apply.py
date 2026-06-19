"""Apply duplicate removals from Czkawka scan results (absolute host paths)."""

from __future__ import annotations

import json
import logging
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Literal

from .duplicate_scan import Mode, _unique_dest
from .paths import normalize_rel

logger = logging.getLogger(__name__)

CZKAWKA_APPLY_CONFIRM = "DELETE_CZKAWKA_DUPLICATES"


def path_key(p: Path) -> str:
    s = str(p.resolve())
    if sys.platform == "win32":
        return s.casefold()
    return s


def resolve_host_file(raw: str) -> Path:
    s = (raw or "").strip().strip('"')
    if not s or "\0" in s:
        raise ValueError("invalid file path")
    try:
        p = Path(s).expanduser().resolve()
    except OSError as e:
        raise ValueError(f"invalid file path: {e}") from e
    if not p.is_file():
        raise ValueError(f"not a file or missing: {p}")
    return p


def resolve_quarantine_dir(
    archive_root: Path,
    *,
    quarantine_rel: str,
    override_abs: str | None = None,
) -> Path:
    if override_abs and override_abs.strip():
        p = Path(override_abs.strip()).expanduser()
        try:
            resolved = p.resolve()
        except OSError as e:
            raise ValueError(f"invalid quarantine_dir: {e}") from e
        if not resolved.is_dir():
            raise ValueError(f"quarantine_dir is not a directory: {resolved}")
        return resolved
    root = archive_root.expanduser().resolve()
    rel = normalize_rel((quarantine_rel or "logs/_duplicates_quarantine").strip())
    qdir = (root / rel).resolve()
    return qdir


def group_paths_index(results: dict[str, Any] | None) -> dict[str, dict[str, str]]:
    """
    Map group_id -> {path_key: original path string from scan}.
    """
    out: dict[str, dict[str, str]] = {}
    if not results:
        return out
    for g in results.get("groups") or []:
        if not isinstance(g, dict):
            continue
        gid = str(g.get("group_id") or "").strip()
        if not gid:
            continue
        paths: dict[str, str] = {}
        for f in g.get("files") or []:
            if not isinstance(f, dict):
                continue
            raw = f.get("path")
            if not raw:
                continue
            try:
                key = path_key(Path(str(raw)))
            except OSError:
                continue
            paths[key] = str(raw)
        if len(paths) >= 2:
            out[gid] = paths
    return out


def validate_apply_items(
    items: list[dict[str, Any]],
    *,
    group_index: dict[str, dict[str, str]],
) -> list[dict[str, Any]]:
    """Normalize and validate keep/remove selections against scan groups."""
    if not items:
        raise ValueError("items required")
    normalized: list[dict[str, Any]] = []
    for it in items:
        gid = str(it.get("group_id") or "").strip()
        keep_raw = str(it.get("keep_path") or "").strip()
        removes_raw = it.get("remove_paths") or []
        if not gid or not keep_raw or not isinstance(removes_raw, list):
            raise ValueError("each item needs group_id, keep_path, remove_paths[]")
        allowed = group_index.get(gid)
        if not allowed:
            raise ValueError(f"unknown or empty group_id: {gid}")
        keep = resolve_host_file(keep_raw)
        keep_k = path_key(keep)
        if keep_k not in allowed:
            raise ValueError(f"keep_path not in scan group {gid}")
        remove_paths: list[Path] = []
        seen: set[str] = set()
        for r in removes_raw:
            rel_s = str(r).strip()
            if not rel_s:
                continue
            fp = resolve_host_file(rel_s)
            fk = path_key(fp)
            if fk == keep_k:
                raise ValueError("remove_path cannot equal keep_path")
            if fk not in allowed:
                raise ValueError(f"remove_path not in scan group {gid}: {fp}")
            if fk in seen:
                continue
            seen.add(fk)
            remove_paths.append(fp)
        if not remove_paths:
            continue
        normalized.append(
            {
                "group_id": gid,
                "keep_path": keep,
                "remove_paths": remove_paths,
            }
        )
    if not normalized:
        raise ValueError("no removals selected")
    return normalized


def apply_czkawka_removals(
    *,
    items: list[dict[str, Any]],
    mode: Mode,
    quarantine_dir: Path,
    dry_run: bool,
    audit_log_path: Path | None = None,
) -> dict[str, Any]:
    preview: list[dict[str, str]] = []
    removed_count = 0
    bytes_reclaimed = 0
    q_dir: Path | None = None
    if mode == "quarantine":
        q_dir = quarantine_dir
        if not dry_run:
            q_dir.mkdir(parents=True, exist_ok=True)

    for it in items:
        keep: Path = it["keep_path"]
        for full in it["remove_paths"]:
            try:
                sz = full.stat().st_size
            except OSError as e:
                raise ValueError(f"stat failed: {full}") from e

            if mode == "quarantine" and q_dir is not None:
                dest = _unique_dest(q_dir, full.name)
                preview.append(
                    {
                        "action": "quarantine",
                        "from_path": str(full),
                        "to_path": str(dest),
                    }
                )
                if not dry_run:
                    shutil.move(str(full), str(dest))
            else:
                preview.append(
                    {"action": "delete", "from_path": str(full), "to_path": ""}
                )
                if not dry_run:
                    full.unlink()

            removed_count += 1
            bytes_reclaimed += sz
            logger.info(
                "czkawka apply %s keep=%s target=%s dry_run=%s",
                mode,
                keep,
                full,
                dry_run,
            )

    result = {
        "removed_count": removed_count,
        "bytes_reclaimed": bytes_reclaimed,
        "preview": preview,
        "dry_run": dry_run,
        "mode": mode,
    }
    if audit_log_path is not None and not dry_run:
        try:
            audit_log_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "applied_unix": time.time(),
                "mode": mode,
                "quarantine_dir": str(quarantine_dir) if mode == "quarantine" else "",
                **result,
            }
            audit_log_path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError as e:
            logger.warning("czkawka apply audit log failed: %s", e)
    return result


def prune_results_after_apply(
    results: dict[str, Any],
    removed_path_keys: set[str],
) -> dict[str, Any]:
    """Return a copy of results with removed files dropped; empty groups removed."""
    if not results or not removed_path_keys:
        return results
    new_groups: list[dict[str, Any]] = []
    for g in results.get("groups") or []:
        if not isinstance(g, dict):
            continue
        files = []
        for f in g.get("files") or []:
            if not isinstance(f, dict) or not f.get("path"):
                continue
            try:
                key = path_key(Path(str(f["path"])))
            except OSError:
                files.append(f)
                continue
            if key not in removed_path_keys:
                files.append(f)
        if len(files) >= 2:
            ng = dict(g)
            ng["files"] = files
            new_groups.append(ng)
    out = dict(results)
    out["groups"] = new_groups
    out["group_count"] = len(new_groups)
    return out
