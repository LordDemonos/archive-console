"""Resolve `logs/latest_run*.txt` to a path relative to archive_root."""

from __future__ import annotations

from pathlib import Path

LATEST_POINTER_REL: dict[str, str] = {
    "watch_later": "logs/latest_run.txt",
    "channels": "logs/latest_run_channel.txt",
    "videos": "logs/latest_run_videos.txt",
    "oneoff": "logs/latest_run_oneoff.txt",
    "galleries": "logs/latest_run_galleries.txt",
}


def read_latest_run_folder_rel(archive_root: Path, job: str) -> str | None:
    rel_file = LATEST_POINTER_REL.get(job)
    if not rel_file:
        return None
    p = (archive_root / rel_file).resolve()
    if not p.is_file():
        return None
    raw = p.read_text(encoding="utf-8", errors="replace").strip()
    if not raw:
        return None
    target = Path(raw).expanduser()
    if not target.is_absolute():
        target = (archive_root / target).resolve()
    else:
        target = target.resolve()
    try:
        return target.relative_to(archive_root.resolve()).as_posix()
    except ValueError:
        return None


def list_recent_archive_runs(archive_root: Path, *, limit: int = 40) -> list[str]:
    """Basenames under logs/archive_run_* sorted by name descending (UTC ids sort lexically)."""
    logs = archive_root / "logs"
    if not logs.is_dir():
        return []
    names: list[str] = []
    for child in logs.iterdir():
        if child.is_dir() and child.name.startswith("archive_run_"):
            names.append(child.name)
    names.sort(reverse=True)
    return names[:limit]
