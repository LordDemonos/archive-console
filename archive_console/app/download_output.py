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
ENV_ONEOFF = "ARCHIVE_OUT_ONEOFF"
ENV_GALLERIES = "ARCHIVE_OUT_GALLERIES"

ONEOFF_DEFAULT_REL = "oneoff"
GALLERIES_DEFAULT_REL = "galleries"

# Matches archive_*_run.py defaults when env is unset.
DEFAULT_REL: dict[JobName, str] = {
    "watch_later": "playlists",
    "channels": "channels",
    "videos": "videos",
    "oneoff": "oneoff",
    "galleries": "galleries",
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
    orel = (dd.oneoff or "").strip()
    if orel:
        ofull = resolve_under_root(archive_root, orel)
        if not is_allowed(archive_root, ofull, allowed_prefixes):
            raise PathNotAllowedError(
                "path not covered by Settings allowlist — add its prefix there first"
            )
    grel = (dd.galleries or "").strip()
    if grel:
        gfull = resolve_under_root(archive_root, grel)
        if not is_allowed(archive_root, gfull, allowed_prefixes):
            raise PathNotAllowedError(
                "path not covered by Settings allowlist — add its prefix there first"
            )


def effective_oneoff_root(archive_root: Path, dd: DownloadDirsSettings) -> Path:
    rel = (dd.oneoff or "").strip()
    if not rel:
        rel = ONEOFF_DEFAULT_REL
    return resolve_under_root(archive_root, rel)


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


def extra_env_for_oneoff(archive_root: Path, dd: DownloadDirsSettings) -> dict[str, str]:
    """Always set ARCHIVE_OUT_ONEOFF (default subfolder oneoff/ when blank)."""
    p = effective_oneoff_root(archive_root, dd)
    return {ENV_ONEOFF: str(p)}


def effective_galleries_root(archive_root: Path, dd: DownloadDirsSettings) -> Path:
    rel = (dd.galleries or "").strip()
    if not rel:
        rel = GALLERIES_DEFAULT_REL
    return resolve_under_root(archive_root, rel)


def extra_env_for_galleries(archive_root: Path, dd: DownloadDirsSettings) -> dict[str, str]:
    p = effective_galleries_root(archive_root, dd)
    return {ENV_GALLERIES: str(p)}


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
    oc = (dd.oneoff or "").strip()
    try:
        oeff = effective_oneoff_root(archive_root, dd)
    except PathNotAllowedError:
        oeff = None
    out["oneoff"] = {
        "configured_rel": oc or None,
        "default_rel": ONEOFF_DEFAULT_REL,
        "effective_rel": ONEOFF_DEFAULT_REL if not oc else oc,
        "effective_abs": str(oeff) if oeff is not None else None,
    }
    gc = (dd.galleries or "").strip()
    try:
        geff = effective_galleries_root(archive_root, dd)
    except PathNotAllowedError:
        geff = None
    out["galleries"] = {
        "configured_rel": gc or None,
        "default_rel": GALLERIES_DEFAULT_REL,
        "effective_rel": GALLERIES_DEFAULT_REL if not gc else gc,
        "effective_abs": str(geff) if geff is not None else None,
    }
    return out
