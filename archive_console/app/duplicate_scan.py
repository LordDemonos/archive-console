"""
Exact duplicate detection under allowlisted archive paths (pure Python).

Phase 1 — size buckets: walk selected roots recursively, collect regular files whose
suffix matches the requested categories, and group by byte size. Unique sizes cannot
contain duplicates (except empty files, which share size 0 and must still be hashed).

Phase 2 — SHA-256: for each size bucket with more than one file, hash each file with
chunked reads and group by digest. Only groups with two or more paths are returned.

We do **not** use MediaInfo (duration, resolution, etc.) as a pre-hash bucket for exact
duplicates: different files can share container stats; that would be unsound for
byte-identical detection. Perceptual / re-encode similarity is out of scope for v1.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
import uuid
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal

from .paths import PathNotAllowedError, assert_allowed_path, normalize_rel

logger = logging.getLogger(__name__)

READ_CHUNK = 4 * 1024 * 1024

VIDEO_SUFFIXES: frozenset[str] = frozenset(
    {
        ".mp4",
        ".mkv",
        ".webm",
        ".mov",
        ".m4v",
        ".avi",
        ".wmv",
        ".flv",
        ".mpeg",
        ".mpg",
        ".ts",
        ".m2ts",
        ".ogv",
    }
)

IMAGE_SUFFIXES: frozenset[str] = frozenset(
    {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff"}
)


def _suffix_allowed(path: Path, *, video: bool, images: bool) -> bool:
    suf = path.suffix.lower()
    if video and suf in VIDEO_SUFFIXES:
        return True
    if images and suf in IMAGE_SUFFIXES:
        return True
    return False


@dataclass
class DuplicateGroup:
    group_id: str
    content_hash: str
    total_size: int
    files: list[dict[str, float | int | str]]  # rel, size, mtime


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(READ_CHUNK)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def collect_files_by_size(
    archive_root: Path,
    allowed_prefixes: list[str],
    root_rels: list[str],
    *,
    include_video: bool,
    include_images: bool,
    on_file_scanned: Callable[[int], None] | None = None,
) -> dict[int, list[tuple[str, int, float]]]:
    """
    Map size -> list of (rel, size, mtime). Only files passing suffix filters.
    """
    root = archive_root.resolve()
    by_size: dict[int, list[tuple[str, int, float]]] = defaultdict(list)
    scanned = 0

    for root_rel in root_rels:
        rel_n = root_rel.strip().replace("\\", "/")
        dir_full = assert_allowed_path(root, rel_n, allowed_prefixes)
        if not dir_full.is_dir():
            continue

        stack = [dir_full]
        while stack:
            current = stack.pop()
            try:
                with os_scandir(current) as it:
                    for entry in it:
                        scanned += 1
                        if on_file_scanned and scanned % 500 == 0:
                            on_file_scanned(scanned)
                        try:
                            if entry.is_dir(follow_symlinks=False):
                                stack.append(Path(entry.path))
                                continue
                            if not entry.is_file(follow_symlinks=False):
                                continue
                        except OSError:
                            continue
                        full = Path(entry.path)
                        try:
                            rel = full.relative_to(root).as_posix()
                        except ValueError:
                            continue
                        try:
                            assert_allowed_path(root, rel, allowed_prefixes)
                        except PathNotAllowedError:
                            continue
                        if not _suffix_allowed(full, video=include_video, images=include_images):
                            continue
                        try:
                            st = full.stat()
                        except OSError:
                            continue
                        by_size[st.st_size].append((rel, int(st.st_size), float(st.st_mtime)))
            except OSError as e:
                logger.warning("duplicate scan: cannot read dir: %s", e)

    return by_size


def os_scandir(path: Path):
    """Delegate for tests (patch duplicate_scan.os_scandir)."""
    import os

    return os.scandir(path)


def find_duplicate_groups(
    archive_root: Path,
    allowed_prefixes: list[str],
    root_rels: list[str],
    *,
    include_video: bool,
    include_images: bool,
    on_progress: Callable[[int, int, int], None] | None = None,
) -> tuple[list[DuplicateGroup], dict[str, int]]:
    """
    Returns (groups, stats) where stats has files_scanned, files_hashed, size_groups.
    on_progress(files_scanned, files_hashed, groups_found_so_far) optional.
    """
    root = archive_root.resolve()
    groups: list[DuplicateGroup] = []

    def on_scan(n: int) -> None:
        if on_progress:
            on_progress(n, 0, 0)

    by_size = collect_files_by_size(
        root,
        allowed_prefixes,
        root_rels,
        include_video=include_video,
        include_images=include_images,
        on_file_scanned=on_scan,
    )
    files_scanned = sum(len(v) for v in by_size.values())
    size_groups_multi = sum(1 for v in by_size.values() if len(v) > 1)
    hashed = 0
    for size, entries in by_size.items():
        if len(entries) < 2:
            continue
        by_hash: dict[str, list[tuple[str, int, float]]] = defaultdict(list)
        for rel, sz, mtime in entries:
            try:
                full = assert_allowed_path(root, rel, allowed_prefixes)
            except PathNotAllowedError:
                continue
            if not full.is_file():
                continue
            try:
                digest = _hash_file(full)
            except OSError as e:
                logger.warning("duplicate scan: hash failed rel=%s err=%s", rel, e)
                continue
            hashed += 1
            if on_progress and hashed % 50 == 0:
                on_progress(files_scanned, hashed, len(groups))
            by_hash[digest].append((rel, sz, mtime))

        for digest, flist in by_hash.items():
            if len(flist) < 2:
                continue
            flist.sort(key=lambda x: (x[0].lower()))
            gid = uuid.uuid4().hex[:12]
            first_size = flist[0][1]
            groups.append(
                DuplicateGroup(
                    group_id=gid,
                    content_hash=digest,
                    total_size=first_size,
                    files=[
                        {"rel": r, "size": sz, "mtime": mt} for r, sz, mt in flist
                    ],
                )
            )

    stats = {
        "files_scanned": files_scanned,
        "files_hashed": hashed,
        "size_groups_multi": size_groups_multi,
        "duplicate_groups": len(groups),
    }
    return groups, stats


Mode = Literal["delete", "quarantine"]


def _unique_dest(quarantine_dir: Path, basename: str) -> Path:
    dest = quarantine_dir / basename
    if not dest.exists():
        return dest
    stem = Path(basename).stem
    suf = Path(basename).suffix
    for i in range(1, 10_000):
        cand = quarantine_dir / f"{stem}_dup{i}{suf}"
        if not cand.exists():
            return cand
    raise OSError("could not allocate quarantine name")


def apply_duplicate_removals(
    archive_root: Path,
    allowed_prefixes: list[str],
    items: list[dict[str, Any]],
    mode: Mode,
    quarantine_rel: str,
    *,
    dry_run: bool,
) -> dict[str, Any]:
    """
    For each item: keep keep_rel; process remove_rels (delete or move to quarantine).
    All paths must be allowlisted regular files.
    """
    root = archive_root.resolve()
    preview: list[dict[str, str]] = []
    removed_count = 0
    bytes_reclaimed = 0

    q_dir: Path | None = None
    if mode == "quarantine":
        rel_q = normalize_rel(quarantine_rel.strip())
        q_dir = assert_allowed_path(root, rel_q, allowed_prefixes)
        if not dry_run:
            q_dir.mkdir(parents=True, exist_ok=True)

    for it in items:
        keep = (it.get("keep_rel") or "").strip().replace("\\", "/")
        removes = it.get("remove_rels") or []
        if not keep or not isinstance(removes, list):
            raise ValueError("each item needs keep_rel and remove_rels[]")
        keep_full = assert_allowed_path(root, keep, allowed_prefixes)
        if not keep_full.is_file():
            raise ValueError(f"keep_rel is not a file: {keep}")

        for r in removes:
            rel = str(r).strip().replace("\\", "/")
            if rel == keep:
                raise ValueError("remove_rel cannot equal keep_rel")
            full = assert_allowed_path(root, rel, allowed_prefixes)
            if not full.is_file():
                raise ValueError(f"not a file or missing: {rel}")
            try:
                sz = full.stat().st_size
            except OSError as e:
                raise ValueError(f"stat failed: {rel}") from e

            if mode == "quarantine" and q_dir is not None:
                dest = _unique_dest(q_dir, full.name)
                preview.append(
                    {
                        "action": "quarantine",
                        "from_rel": rel,
                        "to_rel": dest.relative_to(root).as_posix(),
                    }
                )
                if not dry_run:
                    shutil.move(str(full), str(dest))
            else:
                preview.append({"action": "delete", "from_rel": rel, "to_rel": ""})
                if not dry_run:
                    full.unlink()

            removed_count += 1
            bytes_reclaimed += sz

    return {
        "removed_count": removed_count,
        "bytes_reclaimed": bytes_reclaimed,
        "preview": preview,
        "dry_run": dry_run,
    }
