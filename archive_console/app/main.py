"""FastAPI operator console — localhost only."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Literal

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pydantic import BaseModel, Field, field_validator, model_validator

from .clip_export import ClipExportManager, validate_ffmpeg_exe_setting
from .mediainfo_cli import (
    mediainfo_for_file,
    resolve_mediainfo_bin,
    validate_mediainfo_exe_setting,
)
from .duplicate_scan import apply_duplicate_removals
from .duplicate_scan_manager import DuplicateScanManager
from .cookie_reminder import cookie_hygiene_anchor_if_needed, cookie_reminder_payload
from .download_output import (
    abs_folder_to_rel,
    download_dirs_api_payload,
    extra_env_for_galleries,
    extra_env_for_job,
    extra_env_for_oneoff,
    validate_download_dirs,
)
from .gallery_cli import (
    gallery_dl_executable_ready,
    resolve_gallery_dl_exe,
    run_gallery_dl_json_dump,
)
from .gallery_util import (
    cookie_likely_needed,
    normalize_gallery_url,
    parse_gallery_dl_json_lines,
)
from .folder_browse import pick_directory_host
from .config_smoke import conf_syntax_smoke
from .editor_backup import write_backup_copy
from .editor_files import (
    COOKIES_TXT,
    EDITABLE_FILENAMES,
    resolve_editor_file,
    strip_blank_lines,
)
from .file_serve import (
    allowlisted_file_response,
    assert_reports_file_not_sensitive,
    collect_playable_rels_under_dir,
)
from .report_html_rewrite import rewrite_report_html
from .yt_dlp_config_model import FORMAT_PRESETS, TIER_A_GROUPS, YtdlpUiModel
from .yt_dlp_conf_io import (
    extract_generated_banner_info,
    parse_conf,
    parse_conf_with_report,
    preview_cli,
    serialize_conf,
    tier_b_allowed,
)
from .yt_dlp_presets import PRESET_META, apply_builtin_preset
from .yt_dlp_ui_state import load_ui_state, save_ui_state
from .latest_pointer import (
    LATEST_POINTER_REL,
    list_recent_archive_runs,
    read_latest_run_folder_rel,
)
from .operator_backup import run_operator_backup
from .run_summary import enrich_history_entry_for_api, merge_run_summary_into_history_entry
from .oneoff_report_read import oneoff_rolling_payload
from .oneoff_url import normalize_oneoff_youtube_url
from .paths import (
    PathNotAllowedError,
    assert_allowed_path,
    is_allowed,
    normalize_rel,
    resolve_under_root,
)
from .exiftool_read import validate_exiftool_exe_setting
from .rename_pipeline import (
    RenamePreviewOptions,
    apply_rename_preview,
    build_rename_preview,
)
from .run_manager import BATCH_NAMES, JobName, MonthlyJobName, RunManager, RunState
from .schedule_util import next_run_iso
from .storage_cleanup import build_preview, execute_cleanup, preview_to_api_dict
from .supported_sites import build_supported_sites_payload
from .pre_run_notify import pre_run_reminder_banner
from .deepl_translate import (
    DeepLClientError,
    effective_deepl_api_key,
)
from .settings import (
    CONSOLE_DIR,
    CookieHygieneSettings,
    ConsoleState,
    DownloadDirsSettings,
    OperatorBackupConfig,
    PreRunReminderSettings,
    ScheduleEntry,
    StorageRetentionConfig,
    append_history,
    append_rename_run,
    effective_tray_notify_port,
    load_state,
    save_state,
)

logger = logging.getLogger(__name__)

# POST /api/settings/download-dirs/browse — body.field must be one of these (includes One-off).
DOWNLOAD_DIR_BROWSE_FIELDS: tuple[str, ...] = (
    "watch_later",
    "channels",
    "videos",
    "oneoff",
    "galleries",
)

APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR.parent / "static"
TEMPLATES_DIR = APP_DIR.parent / "templates"
RUN_STAMP_DIR = CONSOLE_DIR / ".run"
PID_FILE = RUN_STAMP_DIR / "uvicorn.pid"

jinja = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
)

_state: ConsoleState | None = None
_manager: RunManager | None = None
_clip_manager: ClipExportManager | None = None
_dup_manager: DuplicateScanManager | None = None


def _get_state() -> ConsoleState:
    global _state
    if _state is None:
        _state = load_state()
    return _state


def _get_manager() -> RunManager:
    global _manager
    st = _get_state()
    root = Path(st.archive_root).expanduser().resolve()
    if _manager is None or _manager.archive_root.resolve() != root:
        _manager = RunManager(archive_root=root)
    return _manager


def _persist_state(st: ConsoleState) -> None:
    save_state(st)
    global _state
    _state = st


def _get_clip_manager() -> ClipExportManager:
    global _clip_manager
    if _clip_manager is None:
        _clip_manager = ClipExportManager(
            get_state=_get_state,
            persist_state=_persist_state,
        )
    return _clip_manager


def _get_dup_manager() -> DuplicateScanManager:
    global _dup_manager
    if _dup_manager is None:
        _dup_manager = DuplicateScanManager(get_state=_get_state)
    return _dup_manager


async def _on_run_complete(finished: RunState | None) -> None:
    if finished is None:
        return
    st = _get_state()
    root = Path(st.archive_root).expanduser().resolve()
    entry: dict[str, Any] = {
        "run_id": finished.run_id,
        "job": finished.job,
        "started_unix": finished.started_unix,
        "ended_unix": finished.ended_unix,
        "exit_code": finished.exit_code,
        "log_folder_rel": finished.log_folder_rel,
        "phase": finished.phase.value,
    }
    entry = merge_run_summary_into_history_entry(root, entry)
    st = append_history(st, entry)
    save_state(st)
    global _state
    _state = st


def _run_download_env(job: MonthlyJobName) -> dict[str, str] | None:
    st = _get_state()
    root = Path(st.archive_root).expanduser().resolve()
    try:
        extra = extra_env_for_job(root, st.download_dirs, job)
    except PathNotAllowedError as e:
        raise HTTPException(
            status_code=400,
            detail=f"download_dirs invalid for run: {e}",
        ) from e
    return extra or None


def _enforce_loopback_host() -> None:
    global _state
    st = _state if _state is not None else load_state()
    if st.host != "127.0.0.1":
        st = st.model_copy(update={"host": "127.0.0.1"})
        save_state(st)
    _state = st


_shutdown_hooks: list[Any] = []


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global _shutdown_hooks
    _enforce_loopback_host()
    RUN_STAMP_DIR.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()), encoding="utf-8")
    _shutdown_hooks = []
    st0 = load_state()
    if st0.features.scheduler_enabled:
        from . import console_scheduler

        _shutdown_hooks.append(
            console_scheduler.start_background_scheduler(
                _get_manager,
                _on_run_complete,
            )
        )
    from . import tray_notify_service

    _shutdown_hooks.append(tray_notify_service.start_tray_notify_scheduler())
    logger.info(
        "Browse output folder API accepts field=%s",
        ", ".join(DOWNLOAD_DIR_BROWSE_FIELDS),
    )
    try:
        yield
    finally:
        for hook in reversed(_shutdown_hooks):
            await hook()
        try:
            PID_FILE.unlink(missing_ok=True)
        except OSError:
            pass


app = FastAPI(title="Archive Console", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/api/health")
def health() -> dict[str, Any]:
    """Include browse API fields so operators can verify the running server build."""
    return {
        "status": "ok",
        "download_dir_browse_fields": list(DOWNLOAD_DIR_BROWSE_FIELDS),
        "gallery_dl_on_path": gallery_dl_executable_ready(),
    }


@app.get("/api/supported-sites")
async def api_supported_sites(
    refresh: bool = Query(
        False,
        description="Bypass short-TTL cache and re-query yt-dlp / gallery-dl CLIs",
    ),
) -> dict[str, Any]:
    """Extractor/site lists from locally installed yt-dlp and gallery-dl (read-only, cached)."""
    return await asyncio.to_thread(
        lambda: build_supported_sites_payload(force_refresh=refresh),
    )


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    tpl = jinja.get_template("index.html")
    return tpl.render()


@app.get("/logs")
def legacy_logs_redirect() -> RedirectResponse:
    """Shallow alias: older bookmarks expecting a Logs screen."""
    return RedirectResponse(
        url="/?view=history&section=outcomes",
        status_code=302,
    )


@app.get("/reports")
def legacy_reports_redirect() -> RedirectResponse:
    """Shallow alias: older bookmarks expecting a Reports screen."""
    return RedirectResponse(
        url="/?view=history&section=reports",
        status_code=302,
    )


class SettingsPatch(BaseModel):
    port: int | None = Field(None, ge=1024, le=65535)
    allowlisted_rel_prefixes: list[str] | None = None
    editor_backup_max: int | None = Field(None, ge=1, le=100)
    operator_backup: OperatorBackupConfig | None = None
    cookie_hygiene: CookieHygieneSettings | None = None
    pre_run_reminder: PreRunReminderSettings | None = None
    download_dirs: DownloadDirsSettings | None = None
    storage_retention: StorageRetentionConfig | None = None
    oneoff_report_retention_days: int | None = Field(None, ge=1, le=3650)
    oneoff_cookie_reminder_last_unix: float | None = None
    require_cookie_confirm_manual: bool | None = None
    tray_notify_before_schedule: bool | None = None
    tray_notify_port: int | None = Field(None, ge=0, le=65535)
    ffmpeg_exe: str | None = None
    mediainfo_exe: str | None = None
    duplicates_quarantine_rel: str | None = None
    duplicates_prefer_quarantine: bool | None = None
    exiftool_exe: str | None = None
    exiftool_timeout_sec: float | None = Field(None, ge=5.0, le=600.0)
    # DeepL: set non-empty to replace stored key; use deepl_api_key_clear to remove.
    deepl_api_key: str | None = None
    deepl_api_key_clear: bool | None = None
    deepl_endpoint_mode: Literal["auto", "free", "pro"] | None = None
    deepl_source_lang: str | None = None
    deepl_target_lang: str | None = None


class RenamePreviewBody(BaseModel):
    rels: list[str]
    options: RenamePreviewOptions = Field(default_factory=RenamePreviewOptions)
    max_files: int = Field(50, ge=1, le=200)


class RenameApplyBody(BaseModel):
    preview_id: str = Field(..., min_length=8)


class StorageCleanupPreviewBody(BaseModel):
    retention_days: int | None = Field(None, ge=1, le=3650)
    prune_archive_runs: bool | None = None
    prune_operator_backup_zips: bool | None = None


class StorageCleanupRunBody(BaseModel):
    confirm: bool = False
    retention_days: int | None = Field(None, ge=1, le=3650)
    prune_archive_runs: bool | None = None
    prune_operator_backup_zips: bool | None = None


def _effective_storage_retention(
    st: ConsoleState, body: StorageCleanupPreviewBody | StorageCleanupRunBody
) -> StorageRetentionConfig:
    base = st.storage_retention.model_dump()
    if body.retention_days is not None:
        base["retention_days"] = body.retention_days
    if body.prune_archive_runs is not None:
        base["prune_archive_runs"] = body.prune_archive_runs
    if body.prune_operator_backup_zips is not None:
        base["prune_operator_backup_zips"] = body.prune_operator_backup_zips
    return StorageRetentionConfig.model_validate(base)


class SchedulesReplaceBody(BaseModel):
    schedules: list[ScheduleEntry]


class CookieHygieneAckBody(BaseModel):
    snooze_days: int = Field(0, ge=0, le=0)  # removed from UX; kept for API stability
    snooze_minutes: int = Field(0, ge=0, le=180)


class PreRunReminderActionBody(BaseModel):
    ack: bool = False
    snooze_minutes: int = Field(0, ge=0, le=120)


class BrowseDownloadDirBody(BaseModel):
    field: str

    @field_validator("field")
    @classmethod
    def _field_allowed(cls, v: str) -> str:
        v = (v or "").strip()
        if v not in DOWNLOAD_DIR_BROWSE_FIELDS:
            raise ValueError(
                "field must be one of: " + ", ".join(DOWNLOAD_DIR_BROWSE_FIELDS)
            )
        return v


class DuplicatesScanBody(BaseModel):
    root_rels: list[str]
    include_video: bool = True
    include_images: bool = False


class DuplicateApplyItem(BaseModel):
    keep_rel: str
    remove_rels: list[str]


class DuplicatesApplyBody(BaseModel):
    dry_run: bool = True
    mode: Literal["delete", "quarantine"] = "quarantine"
    items: list[DuplicateApplyItem]
    confirm: str = ""


class ClipStartBody(BaseModel):
    source_rel: str
    output_dir_rel: str
    start_sec: float = Field(0.0, ge=0.0, le=86400.0 * 48)
    end_sec: float | None = Field(None, ge=0.0)
    duration_sec: float | None = Field(None, gt=0.0)
    format: Literal["mp4", "webm", "gif"] = "mp4"
    basename: str = ""

    @model_validator(mode="after")
    def _end_or_duration(self) -> ClipStartBody:
        if self.end_sec is not None and self.duration_sec is not None:
            raise ValueError("provide end_sec or duration_sec, not both")
        if self.end_sec is None and self.duration_sec is None:
            raise ValueError("end_sec or duration_sec required")
        return self


class ShutdownBody(BaseModel):
    confirm: Literal["SHUTDOWN"]


def _shutdown_client_allowed(request: Request) -> bool:
    c = request.client
    if not c:
        return False
    host = (c.host or "").lower()
    if host in ("127.0.0.1", "::1"):
        return True
    if host == "testclient" and os.environ.get("ARCHIVE_CONSOLE_PYTEST_SHUTDOWN") == "1":
        return True
    return False


@app.post("/api/shutdown")
def api_shutdown(
    request: Request,
    background_tasks: BackgroundTasks,
    payload: ShutdownBody,
) -> dict[str, bool]:
    """
    Terminate this server process (frees the listen port). Loopback-only; not on GET.
    Optional env ARCHIVE_SHUTDOWN_TOKEN: require matching X-Archive-Shutdown-Token header.
    """
    if not _shutdown_client_allowed(request):
        raise HTTPException(
            status_code=403,
            detail="Shutdown is only allowed from loopback clients.",
        )
    token = (os.environ.get("ARCHIVE_SHUTDOWN_TOKEN") or "").strip()
    if token:
        supplied = (request.headers.get("x-archive-shutdown-token") or "").strip()
        if supplied != token:
            raise HTTPException(status_code=403, detail="Invalid shutdown token.")
    from .shutdown import request_shutdown

    background_tasks.add_task(request_shutdown, "api_shutdown")
    return {"ok": True}


def _pre_run_banner(st: ConsoleState) -> dict[str, Any]:
    return pre_run_reminder_banner(st)


@app.get("/api/settings/cookie-reminder")
def api_cookie_reminder_only() -> dict[str, Any]:
    return cookie_reminder_payload(_get_state().cookie_hygiene)


@app.get("/api/settings/reminders")
def api_settings_reminders() -> dict[str, Any]:
    st = _get_state()
    return {
        "cookie_reminder": cookie_reminder_payload(st.cookie_hygiene),
        "pre_run_reminder": _pre_run_banner(st),
        "require_cookie_confirm_manual": st.features.require_cookie_confirm_manual,
    }


@app.get("/api/settings")
def api_settings() -> dict[str, Any]:
    st = _get_state()
    root = Path(st.archive_root).resolve()
    sched_on = st.features.scheduler_enabled
    return {
        "host": st.host,
        "port": st.port,
        "archive_root": str(root),
        "allowlisted_rel_prefixes": st.allowlisted_rel_prefixes,
        "jobs": list(BATCH_NAMES.keys()),
        "features": st.features.model_dump(),
        "settings_schema_version": st.settings_schema_version,
        "schedules": [s.model_dump() for s in st.schedules],
        "schedule_hints": [
            {"schedule": s.model_dump(), "next_run": next_run_iso(s)}
            for s in st.schedules
        ],
        "scheduler_backend_active": sched_on,
        "scheduler_note": (
            "In-process scheduler is active: saved schedules run monthly on the clamped calendar day "
            "at the set hour/minute (local machine time), same jobs as Run. "
            "Missed ticks while the PC sleeps are not replayed. Restart the server after toggling "
            "features.scheduler_enabled in state.json."
            if sched_on
            else "Scheduler backend is inactive. Set features.scheduler_enabled in state.json and restart "
            "so entries below run in-process; otherwise mirror them in Windows Task Scheduler."
        ),
        "editable_files": sorted(EDITABLE_FILENAMES),
        "editor_backup_max": st.editor_backup_max,
        "operator_backup": st.operator_backup.model_dump(),
        "last_operator_backup": st.last_operator_backup.model_dump()
        if st.last_operator_backup
        else None,
        "cookie_hygiene": st.cookie_hygiene.model_dump(),
        "pre_run_reminder_settings": st.pre_run_reminder.model_dump(),
        "cookie_reminder": cookie_reminder_payload(st.cookie_hygiene),
        "pre_run_reminder": _pre_run_banner(st),
        "tray_notify_effective_port": effective_tray_notify_port(st),
        "tray_notify_port": st.tray_notify_port,
        "tray_notify_last_failure_unix": st.tray_notify_last_failure_unix,
        "tray_notify_last_failure_message": st.tray_notify_last_failure_message,
        "download_dirs": st.download_dirs.model_dump(),
        "download_dirs_effective": download_dirs_api_payload(root, st.download_dirs),
        "storage_retention": st.storage_retention.model_dump(),
        "oneoff_report_retention_days": st.oneoff_report_retention_days,
        "oneoff_cookie_reminder_last_unix": st.oneoff_cookie_reminder_last_unix,
        "ffmpeg_exe": st.ffmpeg_exe,
        "mediainfo_exe": st.mediainfo_exe,
        "exiftool_exe": st.exiftool_exe,
        "exiftool_timeout_sec": st.exiftool_timeout_sec,
        "duplicates_quarantine_rel": st.duplicates_quarantine_rel,
        "duplicates_prefer_quarantine": st.duplicates_prefer_quarantine,
        "deepl_api_key_configured": bool(effective_deepl_api_key(st.deepl_api_key)),
        "deepl_endpoint_mode": st.deepl_endpoint_mode,
        "deepl_source_lang": st.deepl_source_lang,
        "deepl_target_lang": st.deepl_target_lang,
        "rename_runs_max": st.rename_runs_max,
    }


@app.post("/api/settings")
def api_settings_update(patch: SettingsPatch) -> dict[str, str]:
    st = _get_state()
    updates: dict[str, Any] = {}
    if patch.port is not None:
        updates["port"] = patch.port
    if patch.allowlisted_rel_prefixes is not None:
        try:
            cleaned = [
                normalize_rel(p) if p else "" for p in patch.allowlisted_rel_prefixes
            ]
        except PathNotAllowedError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        updates["allowlisted_rel_prefixes"] = cleaned
    if patch.editor_backup_max is not None:
        updates["editor_backup_max"] = patch.editor_backup_max
    if patch.operator_backup is not None:
        updates["operator_backup"] = patch.operator_backup
    if patch.cookie_hygiene is not None:
        updates["cookie_hygiene"] = cookie_hygiene_anchor_if_needed(patch.cookie_hygiene)
    if patch.pre_run_reminder is not None:
        updates["pre_run_reminder"] = patch.pre_run_reminder
    if patch.download_dirs is not None:
        root = Path(st.archive_root).expanduser().resolve()
        try:
            validate_download_dirs(
                root, patch.download_dirs, st.allowlisted_rel_prefixes
            )
        except PathNotAllowedError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        updates["download_dirs"] = patch.download_dirs
    if patch.storage_retention is not None:
        updates["storage_retention"] = patch.storage_retention
    if patch.oneoff_report_retention_days is not None:
        updates["oneoff_report_retention_days"] = patch.oneoff_report_retention_days
    if patch.oneoff_cookie_reminder_last_unix is not None:
        updates["oneoff_cookie_reminder_last_unix"] = patch.oneoff_cookie_reminder_last_unix
    feat_up: dict[str, Any] = {}
    if patch.require_cookie_confirm_manual is not None:
        feat_up["require_cookie_confirm_manual"] = patch.require_cookie_confirm_manual
    if patch.tray_notify_before_schedule is not None:
        feat_up["tray_notify_before_schedule"] = patch.tray_notify_before_schedule
    if feat_up:
        updates["features"] = st.features.model_copy(update=feat_up)
    if patch.tray_notify_port is not None:
        updates["tray_notify_port"] = patch.tray_notify_port
    if patch.ffmpeg_exe is not None:
        try:
            updates["ffmpeg_exe"] = validate_ffmpeg_exe_setting(patch.ffmpeg_exe)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
    if patch.mediainfo_exe is not None:
        try:
            updates["mediainfo_exe"] = validate_mediainfo_exe_setting(patch.mediainfo_exe)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
    if patch.exiftool_exe is not None:
        try:
            updates["exiftool_exe"] = validate_exiftool_exe_setting(patch.exiftool_exe)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
    if patch.exiftool_timeout_sec is not None:
        updates["exiftool_timeout_sec"] = patch.exiftool_timeout_sec
    if patch.duplicates_quarantine_rel is not None:
        root = Path(st.archive_root).expanduser().resolve()
        try:
            rel_n = normalize_rel(patch.duplicates_quarantine_rel.strip())
        except PathNotAllowedError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        if not rel_n:
            raise HTTPException(
                status_code=400,
                detail="duplicates_quarantine_rel cannot be empty",
            )
        try:
            q_full = assert_allowed_path(root, rel_n, st.allowlisted_rel_prefixes)
        except PathNotAllowedError as e:
            raise HTTPException(
                status_code=400,
                detail=f"duplicates quarantine path not allowlisted: {e}",
            ) from e
        updates["duplicates_quarantine_rel"] = rel_n
    if patch.duplicates_prefer_quarantine is not None:
        updates["duplicates_prefer_quarantine"] = patch.duplicates_prefer_quarantine
    if patch.deepl_api_key_clear is True:
        updates["deepl_api_key"] = ""
    elif patch.deepl_api_key is not None:
        nk = patch.deepl_api_key.strip()
        if nk:
            updates["deepl_api_key"] = nk
    if patch.deepl_endpoint_mode is not None:
        updates["deepl_endpoint_mode"] = patch.deepl_endpoint_mode
    if patch.deepl_source_lang is not None:
        updates["deepl_source_lang"] = patch.deepl_source_lang.strip()
    if patch.deepl_target_lang is not None:
        updates["deepl_target_lang"] = patch.deepl_target_lang.strip()
    st = st.model_copy(update=updates)
    save_state(st)
    global _state
    _state = st
    return {"ok": "true", "restart": "port change requires console restart"}


@app.post("/api/settings/download-dirs/preview")
def api_download_dirs_preview(body: DownloadDirsSettings) -> dict[str, Any]:
    st = _get_state()
    root = Path(st.archive_root).expanduser().resolve()
    try:
        validate_download_dirs(root, body, st.allowlisted_rel_prefixes)
    except PathNotAllowedError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"download_dirs_effective": download_dirs_api_payload(root, body)}


@app.post("/api/settings/download-dirs/browse")
async def api_download_dirs_browse(body: BrowseDownloadDirBody) -> Any:
    st = _get_state()
    root = Path(st.archive_root).expanduser().resolve()
    labels: dict[str, str] = {
        "watch_later": "Watch Later / playlists output folder",
        "channels": "Channels batch output folder",
        "videos": "Videos list output folder",
        "oneoff": "One-off downloads output folder",
        "galleries": "Galleries (gallery-dl) output folder",
    }
    title = labels.get(body.field, "Choose output folder")
    status, payload = await asyncio.to_thread(pick_directory_host, title)
    if status == "unavailable":
        logger.warning("download-dirs browse: picker unavailable")
        raise HTTPException(
            status_code=503,
            detail=(
                "Folder picker is not available on this host (needs GUI/tkinter). "
                "Type a path relative to the archive root, or run the console on Windows desktop."
            ),
        )
    if status == "cancelled":
        return Response(status_code=204)
    try:
        rel_s, resolved = abs_folder_to_rel(
            root, Path(payload), st.allowlisted_rel_prefixes
        )
    except PathNotAllowedError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    logger.info("download-dirs browse picked field=%s", body.field)
    return {
        "field": body.field,
        "rel": rel_s,
        "effective_abs": str(resolved),
    }


@app.post("/api/clip/browse-output")
async def api_clip_browse_output() -> Any:
    st = _get_state()
    root = Path(st.archive_root).expanduser().resolve()
    status, payload = await asyncio.to_thread(
        pick_directory_host, "Clip export output folder"
    )
    if status == "unavailable":
        logger.warning("clip browse-output: picker unavailable")
        raise HTTPException(
            status_code=503,
            detail=(
                "Folder picker is not available on this host (needs GUI/tkinter). "
                "Type a path relative to the archive root, or run the console on Windows desktop."
            ),
        )
    if status == "cancelled":
        return Response(status_code=204)
    try:
        rel_s, resolved = abs_folder_to_rel(
            root, Path(payload), st.allowlisted_rel_prefixes
        )
    except PathNotAllowedError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    logger.info("clip browse-output picked rel=%s", rel_s)
    return {"rel": rel_s, "effective_abs": str(resolved)}


@app.post("/api/clip/start")
async def api_clip_start(body: ClipStartBody) -> dict[str, str]:
    mgr = _get_clip_manager()
    try:
        clip_id = await mgr.start(
            source_rel=body.source_rel,
            output_dir_rel=body.output_dir_rel,
            start_sec=body.start_sec,
            end_sec=body.end_sec,
            duration_sec=body.duration_sec,
            fmt=body.format,
            basename=body.basename,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except PathNotAllowedError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"clip_id": clip_id}


@app.get("/api/clip/status")
def api_clip_status() -> dict[str, Any]:
    return _get_clip_manager().status()


@app.post("/api/duplicates/scan")
async def api_duplicates_scan(body: DuplicatesScanBody) -> dict[str, str]:
    mgr = _get_dup_manager()
    try:
        scan_id = await mgr.start_scan(
            root_rels=body.root_rels,
            include_video=body.include_video,
            include_images=body.include_images,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"scan_id": scan_id}


@app.get("/api/duplicates/status")
def api_duplicates_status() -> dict[str, Any]:
    return _get_dup_manager().status()


@app.post("/api/duplicates/apply")
def api_duplicates_apply(body: DuplicatesApplyBody) -> dict[str, Any]:
    if not body.items:
        raise HTTPException(status_code=400, detail="items required")
    if not body.dry_run:
        if (body.confirm or "").strip() != "DELETE_DUPLICATES":
            raise HTTPException(
                status_code=400,
                detail='Set confirm to "DELETE_DUPLICATES" to apply removals',
            )
    st = _get_state()
    root = Path(st.archive_root).expanduser().resolve()
    prefixes = st.allowlisted_rel_prefixes
    mode = body.mode
    qrel = (st.duplicates_quarantine_rel or "logs/_duplicates_quarantine").strip()
    items_dump = [it.model_dump() for it in body.items]
    try:
        return apply_duplicate_removals(
            root,
            prefixes,
            items_dump,
            mode,
            qrel,
            dry_run=body.dry_run,
        )
    except PathNotAllowedError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.post("/api/rename/preview")
def api_rename_preview(body: RenamePreviewBody) -> dict[str, Any]:
    st = _get_state()
    root = Path(st.archive_root).expanduser().resolve()
    try:
        return build_rename_preview(
            archive_root=root,
            allowed_prefixes=st.allowlisted_rel_prefixes,
            rels=body.rels,
            opt=body.options,
            stored_api_key=st.deepl_api_key,
            endpoint_mode=st.deepl_endpoint_mode,
            source_lang=st.deepl_source_lang,
            target_lang=st.deepl_target_lang,
            max_files=body.max_files,
            exiftool_exe=st.exiftool_exe,
            exiftool_timeout_sec=st.exiftool_timeout_sec,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except DeepLClientError as e:
        code = 429 if e.code == "deepl_rate_limit" else 502
        raise HTTPException(status_code=code, detail=str(e)) from e


@app.post("/api/rename/apply")
def api_rename_apply(body: RenameApplyBody) -> dict[str, Any]:
    st = _get_state()
    root = Path(st.archive_root).expanduser().resolve()
    t0 = time.time()
    try:
        summary, pipeline_op = apply_rename_preview(
            archive_root=root,
            allowed_prefixes=st.allowlisted_rel_prefixes,
            preview_id=body.preview_id.strip(),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    entry: dict[str, Any] = {
        "run_id": summary["run_id"],
        "operation": pipeline_op,
        "started_unix": t0,
        "ended_unix": time.time(),
        "ok": summary["ok"],
        "skip": summary["skip"],
        "fail": summary["fail"],
        "items": summary["items"],
    }
    st2 = append_rename_run(st, entry)
    save_state(st2)
    global _state
    _state = st2
    return summary


@app.get("/api/rename/history")
def api_rename_history() -> dict[str, Any]:
    st = _get_state()
    return {"items": st.rename_runs, "max": st.rename_runs_max}


@app.post("/api/settings/schedules")
def api_settings_schedules(body: SchedulesReplaceBody) -> dict[str, str]:
    valid = set(BATCH_NAMES.keys())
    for s in body.schedules:
        if s.job not in valid:
            raise HTTPException(status_code=400, detail=f"invalid job: {s.job}")
    st = _get_state()
    st = st.model_copy(update={"schedules": list(body.schedules)})
    save_state(st)
    global _state
    _state = st
    return {"ok": "true"}


@app.post("/api/settings/pre-run-reminder/action")
def api_pre_run_reminder_action(body: PreRunReminderActionBody) -> dict[str, str]:
    st = _get_state()
    pr = st.pre_run_reminder
    pending = _pre_run_banner(st)
    fk = str(pending.get("fire_key") or "")
    if body.snooze_minutes > 0:
        pr = pr.model_copy(
            update={"snooze_until_unix": time.time() + body.snooze_minutes * 60},
        )
    elif body.ack and pending.get("show") and fk:
        pr = pr.model_copy(
            update={"acknowledged_fire_key": fk, "snooze_until_unix": 0.0},
        )
    st = st.model_copy(update={"pre_run_reminder": pr})
    save_state(st)
    global _state
    _state = st
    return {"ok": "true"}


@app.post("/api/settings/cookie-hygiene/ack")
def api_cookie_hygiene_ack(body: CookieHygieneAckBody) -> dict[str, str]:
    st = _get_state()
    ch = st.cookie_hygiene
    now = time.time()
    if body.snooze_minutes > 0:
        ch = ch.model_copy(
            update={"snooze_until_unix": now + body.snooze_minutes * 60},
        )
    else:
        ch = ch.model_copy(
            update={
                "last_acknowledged_unix": now,
                "snooze_until_unix": 0.0,
            }
        )
    st = st.model_copy(update={"cookie_hygiene": ch})
    save_state(st)
    global _state
    _state = st
    return {"ok": "true"}


@app.post("/api/settings/operator-backup/run")
async def api_operator_backup_run() -> dict[str, Any]:
    mgr = _get_manager()
    if (await mgr.status()).get("phase") == "running":
        raise HTTPException(
            status_code=409,
            detail="A download job is running; run backup when idle.",
        )
    st0 = _get_state()
    result = await asyncio.to_thread(run_operator_backup, st0)
    st1 = _get_state().model_copy(update={"last_operator_backup": result})
    save_state(st1)
    global _state
    _state = st1
    return result.model_dump()


@app.post("/api/settings/storage-cleanup/preview")
async def api_storage_cleanup_preview(
    body: StorageCleanupPreviewBody,
) -> dict[str, Any]:
    st = _get_state()
    cfg = _effective_storage_retention(st, body)
    mgr = _get_manager()
    mst = await mgr.status()
    running_rel: str | None = None
    if mst.get("phase") == "running":
        run = mst.get("run") or {}
        running_rel = run.get("log_folder_rel")
    prev = build_preview(st, cfg=cfg, running_log_folder_rel=running_rel)
    return preview_to_api_dict(prev)


@app.post("/api/settings/storage-cleanup/run")
async def api_storage_cleanup_run(body: StorageCleanupRunBody) -> dict[str, Any]:
    if not body.confirm:
        raise HTTPException(
            status_code=400,
            detail="confirm must be true",
        )
    mgr = _get_manager()
    if (await mgr.status()).get("phase") == "running":
        raise HTTPException(
            status_code=409,
            detail="Cannot run storage cleanup while a download job is running.",
        )
    st = _get_state()
    cfg = _effective_storage_retention(st, body)
    return await asyncio.to_thread(
        execute_cleanup,
        st,
        cfg=cfg,
        running_log_folder_rel=None,
    )


class RunStartBody(BaseModel):
    job: MonthlyJobName
    dry_run: bool = False
    skip_ytdlp_update: bool = False
    # Default True: monthly bats historically did not self-upgrade pip; matches double-click runs.
    skip_pip_update: bool = True
    cookie_confirm: bool = False


@app.post("/api/run/start")
async def run_start(body: RunStartBody) -> Any:
    st0 = _get_state()
    if (
        st0.features.require_cookie_confirm_manual
        and not body.dry_run
        and not body.cookie_confirm
    ):
        return JSONResponse(
            status_code=428,
            content={
                "error": "cookie_confirm_required",
                "message": (
                    "Confirm you have refreshed cookies.txt (Netscape format for youtube.com) "
                    "before starting this run."
                ),
            },
        )
    mgr = _get_manager()
    extra = _run_download_env(body.job)
    if extra:
        logger.info("run start job=%s download_dir override active", body.job)
    try:
        r = await mgr.start(
            body.job,
            dry_run=body.dry_run,
            skip_ytdlp_update=body.skip_ytdlp_update,
            skip_pip_update=body.skip_pip_update,
            on_complete=_on_run_complete,
            extra_env=extra,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    return {
        "run_id": r.run_id,
        "job": r.job,
        "started_unix": r.started_unix,
    }


class OneoffStartBody(BaseModel):
    url: str = ""
    output_rel: str = ""
    dry_run: bool = False
    skip_ytdlp_update: bool = False
    skip_pip_update: bool = True
    cookie_confirm: bool = False


@app.post("/api/oneoff/start")
async def oneoff_start(body: OneoffStartBody) -> Any:
    st0 = _get_state()
    try:
        url_norm = normalize_oneoff_youtube_url(body.url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    if (
        st0.features.require_cookie_confirm_manual
        and not body.dry_run
        and not body.cookie_confirm
    ):
        return JSONResponse(
            status_code=428,
            content={
                "error": "cookie_confirm_required",
                "message": (
                    "Confirm you have refreshed cookies.txt (Netscape format for youtube.com) "
                    "before starting this run."
                ),
            },
        )

    root = Path(st0.archive_root).expanduser().resolve()
    prefixes = st0.allowlisted_rel_prefixes
    extra: dict[str, str] = {
        "ARCHIVE_ONEOFF_URL": url_norm,
        "ARCHIVE_ONEOFF_RETENTION_DAYS": str(st0.oneoff_report_retention_days),
    }
    if body.output_rel.strip():
        try:
            rel = normalize_rel(body.output_rel.strip())
        except PathNotAllowedError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        try:
            full = resolve_under_root(root, rel)
        except PathNotAllowedError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        if not is_allowed(root, full, prefixes):
            raise HTTPException(
                status_code=400,
                detail="Output path is not covered by Settings allowlist",
            )
        extra["ARCHIVE_OUT_ONEOFF"] = str(full)
    else:
        try:
            validate_download_dirs(root, st0.download_dirs, prefixes)
            extra.update(extra_env_for_oneoff(root, st0.download_dirs))
        except PathNotAllowedError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    mgr = _get_manager()
    logger.info("oneoff start url=%s", url_norm[:80])
    try:
        r = await mgr.start(
            "oneoff",
            dry_run=body.dry_run,
            skip_ytdlp_update=body.skip_ytdlp_update,
            skip_pip_update=body.skip_pip_update,
            on_complete=_on_run_complete,
            extra_env=extra,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    return {
        "run_id": r.run_id,
        "job": r.job,
        "started_unix": r.started_unix,
    }


class GalleriesPreviewBody(BaseModel):
    url: str = ""
    timeout_sec: float = Field(120.0, ge=10.0, le=600.0)
    gallery_dl_exe: str = ""


@app.post("/api/galleries/preview")
async def galleries_preview(body: GalleriesPreviewBody) -> dict[str, Any]:
    st0 = _get_state()
    root = Path(st0.archive_root).expanduser().resolve()
    try:
        url_norm = normalize_gallery_url(body.url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    exe = resolve_gallery_dl_exe(body.gallery_dl_exe.strip() or None)
    cookies = root / "cookies.txt"
    conf = root / "gallery-dl.conf"
    code, stdout, combined = await asyncio.to_thread(
        run_gallery_dl_json_dump,
        exe=exe,
        url=url_norm,
        cwd=root,
        cookies_file=cookies if cookies.is_file() else None,
        conf_file=conf if conf.is_file() else None,
        timeout_sec=body.timeout_sec,
    )
    rows, parse_errs = parse_gallery_dl_json_lines(stdout, max_rows=500)
    truncated = len(rows) >= 500
    empty = len(rows) == 0
    cookie_hint = (empty and cookie_likely_needed(combined)) or (
        empty and code not in (0, None) and "not recognized" not in combined.lower()
    )
    return {
        "url": url_norm,
        "exit_code": code,
        "rows": rows,
        "parse_warnings": parse_errs[:20],
        "truncated": truncated,
        "cookie_required_hint": bool(cookie_hint and empty),
        "gallery_dl_exe": exe,
        "drift_note": (
            "Preview reflects extractors at this moment; counts can change if posts move "
            "or rate limits differ."
        ),
    }


class GalleriesStartBody(BaseModel):
    url: str = ""
    output_rel: str = ""
    dry_run: bool = False
    skip_ytdlp_update: bool = False
    skip_pip_update: bool = True
    cookie_confirm: bool = False
    gallery_dl_exe: str = ""
    video_fallback: bool = False
    preview_snapshot: dict[str, Any] | None = None


@app.post("/api/galleries/start")
async def galleries_start(body: GalleriesStartBody) -> Any:
    st0 = _get_state()
    try:
        url_norm = normalize_gallery_url(body.url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    if (
        st0.features.require_cookie_confirm_manual
        and not body.dry_run
        and not body.cookie_confirm
    ):
        return JSONResponse(
            status_code=428,
            content={
                "error": "cookie_confirm_required",
                "message": (
                    "Confirm you have refreshed cookies.txt (Netscape format) for YouTube, "
                    "Reddit, and other sites before starting this run."
                ),
            },
        )

    root = Path(st0.archive_root).expanduser().resolve()
    prefixes = st0.allowlisted_rel_prefixes
    extra: dict[str, str] = {
        "ARCHIVE_GALLERY_URL": url_norm,
    }
    gexe = (body.gallery_dl_exe or "").strip()
    if gexe:
        extra["ARCHIVE_GALLERY_DL_EXE"] = gexe
    if body.video_fallback:
        extra["ARCHIVE_GALLERY_VIDEO_FALLBACK"] = "1"

    if body.output_rel.strip():
        try:
            rel = normalize_rel(body.output_rel.strip())
        except PathNotAllowedError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        try:
            full = resolve_under_root(root, rel)
        except PathNotAllowedError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        if not is_allowed(root, full, prefixes):
            raise HTTPException(
                status_code=400,
                detail="Output path is not covered by Settings allowlist",
            )
        extra["ARCHIVE_OUT_GALLERIES"] = str(full)
    else:
        try:
            validate_download_dirs(root, st0.download_dirs, prefixes)
            extra.update(extra_env_for_galleries(root, st0.download_dirs))
        except PathNotAllowedError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    snap = body.preview_snapshot
    if snap is not None:
        try:
            logs_dir = root / "logs"
            logs_dir.mkdir(parents=True, exist_ok=True)
            tmp = logs_dir / f".gallery_preview_{uuid.uuid4().hex}.json"
            tmp.write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")
            extra["ARCHIVE_GALLERY_PREVIEW_JSON"] = str(tmp)
        except OSError as e:
            logger.warning("galleries preview snapshot write failed: %s", e)

    mgr = _get_manager()
    logger.info("galleries start url=%s", url_norm[:80])
    try:
        r = await mgr.start(
            "galleries",
            dry_run=body.dry_run,
            skip_ytdlp_update=body.skip_ytdlp_update,
            skip_pip_update=body.skip_pip_update,
            on_complete=_on_run_complete,
            extra_env=extra,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    return {
        "run_id": r.run_id,
        "job": r.job,
        "started_unix": r.started_unix,
    }


@app.get("/api/galleries/verification")
def galleries_verification(rel: str = Query(..., description="Run folder rel, e.g. logs/archive_run_*")) -> Any:
    st = _get_state()
    root = Path(st.archive_root).expanduser().resolve()
    try:
        folder = assert_allowed_path(root, rel, st.allowlisted_rel_prefixes)
    except PathNotAllowedError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    vf = folder / "verification.json"
    if not vf.is_file():
        raise HTTPException(status_code=404, detail="verification.json not found")
    try:
        data = json.loads(vf.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise HTTPException(status_code=500, detail="invalid verification.json")
    return data


@app.get("/api/oneoff/rolling")
def api_oneoff_rolling() -> dict[str, Any]:
    st = _get_state()
    root = Path(st.archive_root).expanduser().resolve()
    return oneoff_rolling_payload(root, st.allowlisted_rel_prefixes)


@app.post("/api/oneoff/cookie-reminder-ack")
def api_oneoff_cookie_reminder_ack() -> dict[str, str]:
    st = _get_state()
    st2 = st.model_copy(
        update={"oneoff_cookie_reminder_last_unix": time.time()},
    )
    save_state(st2)
    global _state
    _state = st2
    return {"ok": "true"}


@app.get("/api/run/status")
async def run_status() -> dict[str, Any]:
    return await _get_manager().status()


@app.post("/api/run/stop")
async def run_stop() -> dict[str, str]:
    """Stop the tracked batch tree (Windows: taskkill /T on the spawned cmd PID only)."""
    mgr = _get_manager()
    try:
        await mgr.stop()
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return {"ok": "true"}


@app.get("/api/run/stream")
async def run_stream(request: Request) -> StreamingResponse:
    mgr = _get_manager()

    async def gen() -> AsyncIterator[bytes]:
        q = await mgr.broadcaster.subscribe()
        try:
            status = await mgr.status()
            yield f"data: {json.dumps({'type': 'hello', 'status': status})}\n\n".encode(
                "utf-8"
            )
            while True:
                if await request.is_disconnected():
                    break
                try:
                    line = await asyncio.wait_for(q.get(), timeout=25.0)
                except asyncio.TimeoutError:
                    yield b": keepalive\n\n"
                    continue
                yield f"data: {line}\n\n".encode("utf-8")
        finally:
            await mgr.broadcaster.unsubscribe(q)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/reports/latest")
def reports_latest() -> dict[str, Any]:
    st = _get_state()
    root = Path(st.archive_root).resolve()
    out: dict[str, Any] = {"pointers": {}, "recent_runs": list_recent_archive_runs(root)}
    for job, rel_file in LATEST_POINTER_REL.items():
        p = root / rel_file
        text = ""
        if p.is_file():
            text = p.read_text(encoding="utf-8", errors="replace").strip()
        folder_rel = read_latest_run_folder_rel(root, job)  # type: ignore[arg-type]
        out["pointers"][job] = {
            "pointer_file": rel_file,
            "pointer_raw": text,
            "resolved_folder_rel": folder_rel,
        }
    return out


@app.get("/api/files/list")
def files_list(
    path: str = Query("", description="Relative path under archive_root"),
) -> dict[str, Any]:
    st = _get_state()
    root = Path(st.archive_root).resolve()
    prefixes = st.allowlisted_rel_prefixes
    rel_n = normalize_rel(path)
    if not rel_n:
        entries: list[dict[str, Any]] = []
        for pref in prefixes:
            if not pref.strip():
                continue
            top = pref.replace("\\", "/").split("/", 1)[0]
            child = (root / top).resolve()
            if not child.exists():
                continue
            try:
                assert_allowed_path(root, top, prefixes)
            except PathNotAllowedError:
                continue
            st_c = child.stat()
            entries.append(
                {
                    "name": child.name,
                    "rel": child.relative_to(root).as_posix(),
                    "is_dir": child.is_dir(),
                    "size": None if child.is_dir() else st_c.st_size,
                    "mtime": st_c.st_mtime,
                }
            )
        entries.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
        return {"path": ".", "type": "dir", "entries": entries, "virtual_root": True}
    try:
        full = assert_allowed_path(root, path, prefixes)
    except PathNotAllowedError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    if not full.exists():
        raise HTTPException(status_code=404, detail="path not found")
    if full.is_file():
        rel = full.relative_to(root).as_posix()
        st_l = full.stat()
        return {
            "path": rel,
            "type": "file",
            "size": st_l.st_size,
            "mtime": st_l.st_mtime,
        }
    entries: list[dict[str, Any]] = []
    try:
        for child in sorted(full.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            rel_c = child.relative_to(root).as_posix()
            try:
                assert_allowed_path(root, rel_c, prefixes)
            except PathNotAllowedError:
                continue
            st_c = child.stat()
            entries.append(
                {
                    "name": child.name,
                    "rel": rel_c,
                    "is_dir": child.is_dir(),
                    "size": None if child.is_dir() else st_c.st_size,
                    "mtime": st_c.st_mtime,
                }
            )
    except OSError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    parent_rel = full.relative_to(root).as_posix() if full != root else ""
    return {"path": parent_rel or ".", "type": "dir", "entries": entries}


@app.get("/api/files/metadata")
def files_metadata(path: str = Query(...)) -> dict[str, Any]:
    st = _get_state()
    root = Path(st.archive_root).resolve()
    try:
        full = assert_allowed_path(root, path, st.allowlisted_rel_prefixes)
    except PathNotAllowedError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    if not full.exists():
        raise HTTPException(status_code=404, detail="not found")
    st_l = full.stat()
    rel = full.relative_to(root).as_posix()
    return {
        "rel": rel,
        "is_dir": full.is_dir(),
        "size": st_l.st_size,
        "mtime": st_l.st_mtime,
    }


@app.get("/api/files/mediainfo")
async def files_mediainfo(path: str = Query(...)) -> dict[str, Any]:
    """Run MediaInfo CLI (JSON) off the event loop; allowlisted files only."""
    st = _get_state()
    root = Path(st.archive_root).resolve()
    try:
        full = assert_allowed_path(root, path, st.allowlisted_rel_prefixes)
    except PathNotAllowedError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    if not full.exists():
        raise HTTPException(status_code=404, detail="not found")
    exe = resolve_mediainfo_bin(st.mediainfo_exe)
    return await asyncio.to_thread(mediainfo_for_file, exe, full)


@app.get("/api/files/playable-enumerate")
def files_playable_enumerate(
    path: str = Query(
        ...,
        description="Directory relative to archive_root (allowlisted)",
    ),
    recursive: int = Query(
        0,
        ge=0,
        le=1,
        description="Ignored: only direct children of the folder are listed (non-recursive).",
    ),
    max_files: int = Query(1000, ge=1, le=2000),
) -> dict[str, Any]:
    """Queue builder: video/audio + slideshow images (jpg/jpeg/png/gif/webp) in one folder (no subfolder walk)."""
    st = _get_state()
    root = Path(st.archive_root).resolve()
    try:
        rel_n = normalize_rel(path)
    except PathNotAllowedError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    if not rel_n:
        raise HTTPException(
            status_code=400,
            detail="Choose a folder under Files (not the virtual roots view); path cannot be empty.",
        )
    try:
        rels = collect_playable_rels_under_dir(
            root,
            rel_n,
            st.allowlisted_rel_prefixes,
            recursive=False,
            max_files=max_files,
        )
    except PathNotAllowedError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    return {"rels": rels, "count": len(rels)}


class ExplorerBody(BaseModel):
    path: str


def _resolve_windows_explorer_exe() -> Path | None:
    """Locate explorer.exe (PATH or %SystemRoot%)."""
    which = shutil.which("explorer.exe")
    if which:
        p = Path(which)
        if p.is_file():
            return p
    system_root = os.environ.get("SystemRoot", r"C:\Windows")
    candidate = Path(system_root) / "explorer.exe"
    if candidate.is_file():
        return candidate
    return None


def explorer_launch_argv(explorer_exe: Path, target: Path) -> list[str]:
    """
    Build argv for Windows Explorer. ``/select`` must include the full path in the
    same argument (``/select,<path>``); a separate argv entry for the path is ignored.
    """
    resolved = str(target.resolve())
    if target.is_dir():
        return [str(explorer_exe), resolved]
    return [str(explorer_exe), f"/select,{resolved}"]


def _editor_path_error(e: PathNotAllowedError) -> HTTPException:
    msg = str(e) if e.args else "forbidden"
    if msg == "unknown_editable_file":
        return HTTPException(status_code=404, detail="Not an editable file")
    return HTTPException(status_code=403, detail=msg)


@app.get("/api/files/{name}")
async def get_editable_file(
    name: str,
    unlock_cookies: bool = Query(False),
) -> dict[str, Any]:
    st = _get_state()
    root = Path(st.archive_root).resolve()
    try:
        full = resolve_editor_file(root, name)
    except PathNotAllowedError as e:
        raise _editor_path_error(e) from e
    fname = full.relative_to(root).as_posix()
    if fname == COOKIES_TXT and not unlock_cookies:
        mtime: float | None = None
        size: int | None = None
        if full.is_file():
            stl = full.stat()
            mtime = stl.st_mtime
            size = stl.st_size
        return {
            "rel": fname,
            "mtime": mtime,
            "size": size,
            "content": None,
            "locked": True,
            "warnings": [
                "cookies.txt is locked. Use “Unlock cookies” in the UI to load or edit "
                "(sensitive: avoid sharing screen, history, or logs)."
            ],
        }
    if not full.exists():
        return {
            "rel": fname,
            "mtime": None,
            "size": None,
            "content": "",
            "locked": False,
            "warnings": [],
        }
    stl = full.stat()
    text = full.read_text(encoding="utf-8", errors="replace")
    return {
        "rel": fname,
        "mtime": stl.st_mtime,
        "size": stl.st_size,
        "content": text,
        "locked": False,
        "warnings": [],
    }


class EditorPutBody(BaseModel):
    content: str = ""
    strip_blank_lines: bool = False
    conf_smoke: bool = False
    unlock_cookies: bool = False


@app.put("/api/files/{name}")
async def put_editable_file(name: str, body: EditorPutBody) -> dict[str, Any]:
    mgr = _get_manager()
    st_m = await mgr.status()
    if st_m.get("phase") == "running":
        raise HTTPException(
            status_code=409,
            detail=(
                "A job is running — save blocked. Wait for it to finish. "
                "(yt-dlp may read yt-dlp.conf / cookies while running; editing mid-run is racy.)"
            ),
        )
    st = _get_state()
    root = Path(st.archive_root).resolve()
    try:
        full = resolve_editor_file(root, name)
    except PathNotAllowedError as e:
        raise _editor_path_error(e) from e
    fname = full.relative_to(root).as_posix()
    if fname == COOKIES_TXT and not body.unlock_cookies:
        raise HTTPException(
            status_code=403,
            detail="unlock_cookies=true required to write cookies.txt",
        )
    text = body.content
    if body.strip_blank_lines and fname in (
        "playlists_input.txt",
        "channels_input.txt",
        "videos_input.txt",
    ):
        text = strip_blank_lines(text)
    warnings: list[str] = []
    if fname == "yt-dlp.conf" and body.conf_smoke:
        warnings.extend(conf_syntax_smoke(text))
    backup_rel: str | None = None
    bk_max = st.editor_backup_max
    if full.is_file():
        dest = write_backup_copy(full, fname, bk_max)
        if dest is not None:
            backup_rel = dest.relative_to(CONSOLE_DIR).as_posix()
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(text, encoding="utf-8", newline="\n")
    stl = full.stat()
    return {
        "ok": True,
        "rel": fname,
        "mtime": stl.st_mtime,
        "backup": backup_rel,
        "warnings": warnings,
    }


@app.post("/api/files/open-explorer")
def open_explorer(body: ExplorerBody) -> dict[str, str]:
    st = _get_state()
    root = Path(st.archive_root).resolve()
    try:
        full = assert_allowed_path(root, body.path, st.allowlisted_rel_prefixes)
    except PathNotAllowedError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    if not full.exists():
        raise HTTPException(status_code=404, detail="not found")
    if os.name != "nt":
        raise HTTPException(
            status_code=501,
            detail="Windows Explorer integration is only available on Windows",
        )
    explorer = _resolve_windows_explorer_exe()
    if explorer is None:
        logger.warning("open_explorer: explorer.exe not found")
        raise HTTPException(status_code=500, detail="explorer.exe not found")
    argv = explorer_launch_argv(explorer, full)
    try:
        subprocess.Popen(argv, close_fds=False)
    except OSError as exc:
        logger.warning("open_explorer: failed to start Explorer: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="Could not start Windows Explorer",
        ) from exc
    return {"ok": "true"}


@app.get("/reports/file")
def reports_file(
    rel: str = Query(..., alias="rel"),
    download: int = Query(0, ge=0, le=1, description="1 = force download (attachment)"),
    disposition: str | None = Query(
        None,
        description='Use "attachment" to force download (same as download=1)',
    ),
) -> FileResponse:
    st = _get_state()
    root = Path(st.archive_root).resolve()
    try:
        full = assert_allowed_path(root, rel, st.allowlisted_rel_prefixes)
    except PathNotAllowedError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    if not full.is_file():
        raise HTTPException(status_code=404, detail="not a file")
    assert_reports_file_not_sensitive(full)
    as_attachment = bool(download) or (
        (disposition or "").strip().lower() == "attachment"
    )
    return allowlisted_file_response(full, as_attachment=as_attachment)


@app.get("/reports/view", response_class=HTMLResponse)
def reports_view(
    rel: str = Query(..., alias="rel"),
) -> HTMLResponse:
    """
    Same-origin report.html: rewrite file:// hrefs to /reports/file?rel=… and inject
    a small shim so JS-built filepath links also navigate in-tab (not mixed-content file:).
    """
    st = _get_state()
    root = Path(st.archive_root).resolve()
    try:
        full = assert_allowed_path(root, rel, st.allowlisted_rel_prefixes)
    except PathNotAllowedError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    if not full.is_file():
        raise HTTPException(status_code=404, detail="not a file")
    assert_reports_file_not_sensitive(full)
    if full.suffix.lower() not in (".html", ".htm"):
        raise HTTPException(status_code=400, detail="reports/view accepts .html only")
    text = full.read_text(encoding="utf-8", errors="replace")
    body = rewrite_report_html(text, root, st.allowlisted_rel_prefixes)
    return HTMLResponse(
        content=body,
        headers={
            "Content-Disposition": f'inline; filename="{full.name}"',
        },
    )


async def _ytdlp_require_idle() -> None:
    mgr = _get_manager()
    if (await mgr.status()).get("phase") == "running":
        raise HTTPException(
            status_code=409,
            detail="A download job is running. Wait for it to finish before changing yt-dlp.conf.",
        )


def _ytdlp_conf_path() -> Path:
    return Path(_get_state().archive_root).expanduser().resolve() / "yt-dlp.conf"


def _clip_text(s: str, max_len: int) -> str:
    if len(s) <= max_len:
        return s
    return s[: max_len - 1] + "…"


@app.get("/api/ytdlp/setup")
def api_ytdlp_setup() -> dict[str, Any]:
    p = _ytdlp_conf_path()
    exists = p.is_file()
    text = p.read_text(encoding="utf-8", errors="replace") if exists else ""
    model, parse_warnings = parse_conf_with_report(text)
    if not exists:
        parse_warnings.insert(
            0,
            f"No file on disk yet — showing defaults for a new {p.name} (Save creates it).",
        )
    ui = load_ui_state()
    _, banner_preset = extract_generated_banner_info(text)
    ser = serialize_conf(
        model,
        preset_id=ui.active_preset_id,
        human_note="",
    )
    tail = model.preserved_tail or ""
    tail_preview = _clip_text(tail, 16000)
    if len(tail) > 16000:
        tail_preview += "\n… [truncated for UI — full tail is saved with the file]\n"
    return {
        "model": model.model_dump(),
        "presets": PRESET_META,
        "active_preset_id": ui.active_preset_id,
        "preset_from_last_save": banner_preset,
        "tier_a_groups": TIER_A_GROUPS,
        "format_presets": FORMAT_PRESETS,
        "user_snapshot_present": ui.user_preferences_snapshot is not None,
        "conf_path": str(p),
        "conf_exists": exists,
        "parse_warnings": parse_warnings,
        "preview": preview_cli(model),
        "serialized_preview": ser,
        "preserved_tail_preview": tail_preview,
    }


class YtdlpModelBody(BaseModel):
    model: dict[str, Any]


@app.post("/api/ytdlp/setup/preview")
def api_ytdlp_preview(body: YtdlpModelBody) -> dict[str, Any]:
    m = YtdlpUiModel.model_validate(body.model)
    ui = load_ui_state()
    ser = serialize_conf(m, preset_id=ui.active_preset_id)
    tail = m.preserved_tail or ""
    tail_prev = _clip_text(tail, 16000)
    if len(tail) > 16000:
        tail_prev += "\n… [truncated for UI — full tail is saved with the file]\n"
    return {
        "preview": preview_cli(m),
        "serialized_preview": _clip_text(ser, 24000),
        "preserved_tail_preview": tail_prev,
    }


class YtdlpSaveBody(BaseModel):
    model: dict[str, Any]
    active_preset_id: str = "balanced"
    human_note: str = ""
    conf_smoke: bool = True


@app.post("/api/ytdlp/setup/save")
async def api_ytdlp_save(body: YtdlpSaveBody) -> dict[str, Any]:
    await _ytdlp_require_idle()
    st = _get_state()
    m = YtdlpUiModel.model_validate(body.model)
    for k, v in m.extra_kv.items():
        if not tier_b_allowed(k, v):
            raise HTTPException(
                status_code=400,
                detail=f"Tier B option blocked or invalid: {k}",
            )
    out_text = serialize_conf(
        m,
        preset_id=body.active_preset_id,
        human_note=body.human_note,
    )
    warnings: list[str] = []
    if body.conf_smoke:
        warnings.extend(conf_syntax_smoke(out_text))
    p = _ytdlp_conf_path()
    if p.is_file():
        dest = write_backup_copy(p, "yt-dlp.conf", st.editor_backup_max)
        if dest is None:
            pass
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(out_text, encoding="utf-8", newline="\n")
    ui = load_ui_state()
    save_ui_state(ui.model_copy(update={"active_preset_id": body.active_preset_id}))
    return {"ok": True, "warnings": warnings}


class YtdlpApplyBody(BaseModel):
    preset_id: str


@app.post("/api/ytdlp/setup/apply-preset")
def api_ytdlp_apply_preset(body: YtdlpApplyBody) -> dict[str, Any]:
    p = _ytdlp_conf_path()
    text = p.read_text(encoding="utf-8", errors="replace") if p.is_file() else ""
    current = (
        parse_conf(text).model_dump() if text.strip() else YtdlpUiModel().model_dump()
    )
    ui = load_ui_state()
    if body.preset_id == "user_preferences":
        if not ui.user_preferences_snapshot:
            raise HTTPException(
                status_code=400,
                detail="Capture User preferences from disk first.",
            )
        m = YtdlpUiModel.model_validate(ui.user_preferences_snapshot)
    elif body.preset_id not in {p["id"] for p in PRESET_META}:
        raise HTTPException(status_code=404, detail="Unknown preset")
    else:
        m = YtdlpUiModel.model_validate(
            apply_builtin_preset(current, body.preset_id)
        )
    save_ui_state(ui.model_copy(update={"active_preset_id": body.preset_id}))
    ser = serialize_conf(m, preset_id=body.preset_id, human_note="")
    tail = m.preserved_tail or ""
    tail_prev = _clip_text(tail, 16000)
    if len(tail) > 16000:
        tail_prev += "\n… [truncated for UI — full tail is saved with the file]\n"
    return {
        "model": m.model_dump(),
        "preview": preview_cli(m),
        "serialized_preview": ser,
        "preserved_tail_preview": tail_prev,
        "active_preset_id": body.preset_id,
    }


@app.post("/api/ytdlp/setup/capture-user")
def api_ytdlp_capture_user() -> dict[str, Any]:
    p = _ytdlp_conf_path()
    if not p.is_file():
        raise HTTPException(status_code=404, detail="yt-dlp.conf not found")
    text = p.read_text(encoding="utf-8", errors="replace")
    m = parse_conf(text)
    ui = load_ui_state()
    snap = m.model_dump()
    save_ui_state(
        ui.model_copy(
            update={
                "user_preferences_snapshot": snap,
                "active_preset_id": "user_preferences",
            }
        )
    )
    ser = serialize_conf(m, preset_id="user_preferences", human_note="")
    tail = m.preserved_tail or ""
    tail_prev = _clip_text(tail, 16000)
    if len(tail) > 16000:
        tail_prev += "\n… [truncated for UI — full tail is saved with the file]\n"
    return {
        "model": snap,
        "preview": preview_cli(m),
        "serialized_preview": ser,
        "preserved_tail_preview": tail_prev,
        "active_preset_id": "user_preferences",
    }


@app.get("/api/history")
def api_history() -> dict[str, Any]:
    st = _get_state()
    root = Path(st.archive_root).expanduser().resolve()
    items = [enrich_history_entry_for_api(root, dict(h)) for h in st.run_history]
    return {"items": items, "max": st.run_history_max}
