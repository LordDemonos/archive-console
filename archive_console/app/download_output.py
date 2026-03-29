"""Per-job download output roots: validate under archive root, env vars for Python drivers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .paths import PathNotAllowedError, is_allowed, resolve_under_root
from .run_manager import JobName
from .settings import DownloadDirsSettings

ENV_PLAYLIST = "ARCHIVE_OUT_PLAYLIST"
ENV_CHANNEL = "ARCHIVE_OUT_CHANNEL"
ENV_VIDEOS = "ARCHIVE_OUT_VIDEOS"

# Matches archive_*_run.py defaults when env is unset.
DEFAULT_REL: dict[JobName, str] = {
    "watch_later": "playlists",
    "channels": "channels",
    "videos": "videos",
}

_JOB_ENV: dict[JobName, tuple[str, str]] = {
    "watch_later": ("watch_later", ENV_PLAYLIST),
    "channels": ("channels", ENV_CHANNEL),
    "videos": ("videos", ENV_VIDEOS),
}


def effective_output_root(archive_root: Path, job: JobName, rel_override: str) -> Path:
    rel = (rel_override or "").strip()
    if not rel:
        rel = DEFAULT_REL[job]
    return resolve_under_root(archive_root, rel)


def validate_download_dirs(
    archive_root: Path,
    dd: DownloadDirsSettings,
    allowed_prefixes: list[str],
) -> None:
    for job in _JOB_ENV:
        field, _ = _JOB_ENV[job]
        rel = (getattr(dd, field) or "").strip()
        if rel:
            full = resolve_under_root(archive_root, rel)
            if not is_allowed(archive_root, full, allowed_prefixes):
                raise PathNotAllowedError(
                    "path not covered by Settings allowlist — add its prefix there first"
                )


def abs_folder_to_rel(
    archive_root: Path,
    selected_abs: Path,
    allowed_prefixes: list[str],
) -> tuple[str, Path]:
    """Return (relative posix path, resolved full path) or raise PathNotAllowedError."""
    root_r = archive_root.resolve()
    try:
        sel_r = selected_abs.expanduser().resolve()
    except OSError as e:
        raise PathNotAllowedError("invalid selected path") from e
    try:
        rel = sel_r.relative_to(root_r)
    except ValueError as e:
        raise PathNotAllowedError("selected folder is outside archive root") from e
    if rel.as_posix() in (".", ""):
        raise PathNotAllowedError("pick a folder inside the archive root, not the root itself")
    rel_s = rel.as_posix()
    if not is_allowed(archive_root, sel_r, allowed_prefixes):
        raise PathNotAllowedError(
            "path not covered by Settings allowlist — add its prefix first"
        )
    return rel_s, sel_r


def extra_env_for_job(
    archive_root: Path,
    dd: DownloadDirsSettings,
    job: JobName,
) -> dict[str, str]:
    field, env_key = _JOB_ENV[job]
    rel = (getattr(dd, field) or "").strip()
    if not rel:
        return {}
    p = resolve_under_root(archive_root, rel)
    return {env_key: str(p)}


def download_dirs_api_payload(archive_root: Path, dd: DownloadDirsSettings) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for job in _JOB_ENV:
        field, _ = _JOB_ENV[job]
        configured = (getattr(dd, field) or "").strip()
        try:
            eff = effective_output_root(archive_root, job, configured)
        except PathNotAllowedError:
            eff = None
        out[job] = {
            "configured_rel": configured or None,
            "default_rel": DEFAULT_REL[job],
            "effective_rel": DEFAULT_REL[job] if not configured else configured,
            "effective_abs": str(eff) if eff is not None else None,
        }
    return out
