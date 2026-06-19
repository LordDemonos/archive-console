"""Per-job download output roots: validate under archive root, env vars for Python drivers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .paths import PathNotAllowedError, is_allowed, normalize_rel, resolve_under_root
from .run_manager import JobName
from .settings import ConsoleState, DownloadDirsSettings, YtdlpBatchRunSettings

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

# Console paths always exposed (logs, run history, site cookies for gallery-dl).
SYSTEM_ALLOWLIST_PREFIXES: tuple[str, ...] = ("logs", "cookies")


def _add_allow_prefix(
    archive_root: Path,
    rel: str,
    seen: set[str],
    out: list[str],
) -> None:
    if not (rel or "").strip():
        return
    try:
        n = normalize_rel(rel.strip())
        resolve_under_root(archive_root, n)
    except PathNotAllowedError:
        return
    if n not in seen:
        seen.add(n)
        out.append(n)


def download_output_rel_prefixes(
    archive_root: Path,
    dd: DownloadDirsSettings,
) -> list[str]:
    """Effective download output roots (each includes all subfolders via is_allowed)."""
    root = archive_root.resolve()
    seen: set[str] = set()
    out: list[str] = []
    for job in _JOB_ENV:
        field, _ = _JOB_ENV[job]
        configured = (getattr(dd, field) or "").strip()
        _add_allow_prefix(root, configured or DEFAULT_REL[job], seen, out)
    _add_allow_prefix(root, (dd.oneoff or "").strip() or ONEOFF_DEFAULT_REL, seen, out)
    _add_allow_prefix(
        root, (dd.galleries or "").strip() or GALLERIES_DEFAULT_REL, seen, out
    )
    return out


def effective_allowlisted_prefixes(
    archive_root: Path,
    download_dirs: DownloadDirsSettings,
    *,
    legacy_manual: list[str] | None = None,
    operator_backup_extra: list[str] | None = None,
) -> list[str]:
    """
    Paths the console may read/write: system folders + download output roots +
    optional legacy manual entries and operator-backup extras.
    """
    root = archive_root.resolve()
    seen: set[str] = set()
    out: list[str] = []
    for p in SYSTEM_ALLOWLIST_PREFIXES:
        _add_allow_prefix(root, p, seen, out)
    for p in download_output_rel_prefixes(root, download_dirs):
        if p not in seen:
            seen.add(p)
            out.append(p)
    for p in operator_backup_extra or ():
        _add_allow_prefix(root, p, seen, out)
    for p in legacy_manual or ():
        _add_allow_prefix(root, p, seen, out)
    return out


def state_allowed_prefixes(st: ConsoleState) -> list[str]:
    """Runtime allowlist for Library, Rename, duplicates, file serve, etc."""
    root = Path(st.archive_root).expanduser().resolve()
    extras: list[str] = list(st.operator_backup.include_extra_rel_prefixes or [])
    q = (st.duplicates_quarantine_rel or "").strip()
    if q:
        extras.append(q)
    return effective_allowlisted_prefixes(
        root,
        st.download_dirs,
        legacy_manual=st.allowlisted_rel_prefixes,
        operator_backup_extra=extras,
    )


def effective_output_root(archive_root: Path, job: JobName, rel_override: str) -> Path:
    rel = (rel_override or "").strip()
    if not rel:
        rel = DEFAULT_REL[job]
    return resolve_under_root(archive_root, rel)


def _validate_rel_under_root(archive_root: Path, rel: str) -> None:
    resolve_under_root(archive_root, rel)


def validate_galleries_output_dir(
    archive_root: Path,
    dd: DownloadDirsSettings,
    allowed_prefixes: list[str] | None = None,
) -> None:
    """Galleries start/save: effective galleries root must resolve under archive_root."""
    del allowed_prefixes
    rel = (dd.galleries or "").strip() or GALLERIES_DEFAULT_REL
    _validate_rel_under_root(archive_root, rel)


def validate_oneoff_output_dir(
    archive_root: Path,
    dd: DownloadDirsSettings,
    allowed_prefixes: list[str] | None = None,
) -> None:
    """One-off start/save: effective oneoff root must resolve under archive_root."""
    del allowed_prefixes
    rel = (dd.oneoff or "").strip() or ONEOFF_DEFAULT_REL
    _validate_rel_under_root(archive_root, rel)


def validate_download_dirs(
    archive_root: Path,
    dd: DownloadDirsSettings,
    allowed_prefixes: list[str] | None = None,
) -> None:
    """Ensure configured output dirs resolve under archive_root (no manual allowlist)."""
    del allowed_prefixes
    for job in _JOB_ENV:
        field, _ = _JOB_ENV[job]
        rel = (getattr(dd, field) or "").strip()
        if rel:
            _validate_rel_under_root(archive_root, rel)
    for rel in (
        (dd.oneoff or "").strip() or ONEOFF_DEFAULT_REL,
        (dd.galleries or "").strip() or GALLERIES_DEFAULT_REL,
    ):
        _validate_rel_under_root(archive_root, rel)


def effective_oneoff_root(archive_root: Path, dd: DownloadDirsSettings) -> Path:
    rel = (dd.oneoff or "").strip()
    if not rel:
        rel = ONEOFF_DEFAULT_REL
    return resolve_under_root(archive_root, rel)


def abs_file_to_rel(
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
    if not sel_r.exists():
        raise PathNotAllowedError("selected path does not exist")
    if sel_r.is_dir():
        raise PathNotAllowedError("selected path is a folder, not a file")
    if not sel_r.is_file():
        raise PathNotAllowedError("selected path is not a file")
    try:
        rel = sel_r.relative_to(root_r)
    except ValueError as e:
        raise PathNotAllowedError("selected file is outside archive root") from e
    rel_s = rel.as_posix()
    if not is_allowed(archive_root, sel_r, allowed_prefixes):
        raise PathNotAllowedError(
            "path is outside download output folders — set the folder under "
            "Input lists → Download output folders (must be under the archive root)"
        )
    return rel_s, sel_r


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
        raise PathNotAllowedError(
            f"selected folder is outside archive root ({root_r}) — "
            "pick a folder under the archive root set in Settings, or fix Settings → archive root"
        ) from e
    if rel.as_posix() in (".", ""):
        raise PathNotAllowedError("pick a folder inside the archive root, not the root itself")
    rel_s = rel.as_posix()
    if not is_allowed(archive_root, sel_r, allowed_prefixes):
        raise PathNotAllowedError(
            "path is outside download output folders — set the folder under "
            "Input lists → Download output folders (must be under the archive root)"
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


def extra_env_for_ytdlp_batch(ybr: YtdlpBatchRunSettings) -> dict[str, str]:
    """ARCHIVE_PAUSE_ON_COOKIE_ERROR / ARCHIVE_COOKIE_AUTH_POLL_SEC for playlist drivers."""
    if ybr.pause_on_cookie_error:
        return {
            "ARCHIVE_PAUSE_ON_COOKIE_ERROR": "1",
            "ARCHIVE_COOKIE_AUTH_POLL_SEC": str(int(ybr.cookie_auth_poll_sec)),
        }
    return {
        "ARCHIVE_PAUSE_ON_COOKIE_ERROR": "",
        "ARCHIVE_COOKIE_AUTH_POLL_SEC": "",
    }


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
