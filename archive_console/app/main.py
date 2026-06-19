"""FastAPI operator console — localhost only."""

from __future__ import annotations

import asyncio
import copy
import json
import logging
import os
import shutil
import subprocess
import sys
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
from .czkawka_runner import validate_czkawka_exe_setting
from .czkawka_scan_manager import CzkawkaScanManager
from .czkawka_apply import (
    CZKAWKA_APPLY_CONFIRM,
    apply_czkawka_removals,
    group_paths_index,
    path_key,
    prune_results_after_apply,
    resolve_quarantine_dir,
    validate_apply_items,
)
from .cookie_reminder import cookie_hygiene_anchor_if_needed, cookie_reminder_payload
from .download_output import (
    abs_file_to_rel,
    abs_folder_to_rel,
    download_dirs_api_payload,
    effective_galleries_root,
    extra_env_for_galleries,
    extra_env_for_job,
    extra_env_for_oneoff,
    extra_env_for_ytdlp_batch,
    state_allowed_prefixes,
    validate_download_dirs,
    validate_galleries_output_dir,
    validate_oneoff_output_dir,
)
from .gallery_cli import (
    gallery_dl_executable_ready,
    resolve_gallery_dl_exe,
    run_gallery_dl_json_dump,
)
from .gallery_dl_setup import (
    PRESET_BAR_NOTE,
    PRESET_META as GDL_PRESET_META,
    TIER_A_GROUPS as GDL_TIER_A_GROUPS,
    apply_builtin_preset as gdl_apply_builtin_preset,
    apply_user_snapshot as gdl_apply_user_snapshot,
    clip_text as gdl_clip_text,
    model_from_client_dict,
    parse_gallery_dl_conf_text,
    preview_cli as gdl_preview_cli,
    serialize_gallery_dl_conf,
    smoke_gallery_dl_conf,
)
from .gifski_convert import (
    GifskyBatchManager,
    scan_gallery_videos,
    validate_gifski_exe_setting,
)
from .gifski_setup import (
    PRESET_META as GIFSKY_PRESET_META,
    TIER_A_GROUPS as GIFSKY_TIER_A_GROUPS,
    apply_builtin_preset as gifsky_apply_builtin_preset,
    gifsky_conf_path,
    model_from_client_dict as gifsky_model_from_client_dict,
    parse_gifsky_conf_text,
    preview_summary as gifsky_preview_summary,
    serialize_gifsky_conf,
)
from .gifski_ui_state import load_gifsky_ui_state, save_gifsky_ui_state
from .gallery_dl_ui_state import load_gallery_dl_ui_state, save_gallery_dl_ui_state
from .gallery_preview_names import (
    apply_smart_suggested_filenames,
    dedupe_gallery_preview_rows_by_primary_url,
)
from .gallery_reddit import (
    build_effective_gallery_conf_for_galleries,
    write_merged_conf_temp,
)
from .gallery_source_batch import (
    GALLERY_SOURCES_SCHEDULE_ID,
    GALLERY_SOURCES_SCHEDULE_JOB,
    stop_gallery_source_batch_after_user_cancel,
    continue_gallery_source_batch_if_any,
    flush_gallery_batch_gotify,
    is_gallery_batch_last_source,
    record_gallery_batch_source_result,
    start_gallery_sources_batch,
)
from .gallery_sources import (
    list_gallery_sources_for_api,
    record_gallery_source_after_run,
    remove_gallery_sources,
    upsert_gallery_source,
)
from .gallery_util import (
    cookie_likely_needed,
    normalize_gallery_url,
    parse_gallery_dl_json_lines,
    sanitize_gallery_dl_stderr,
)
from .folder_browse import pick_directory_host, pick_file_host, pick_files_host
from .config_smoke import conf_syntax_smoke
from .editor_backup import write_backup_copy
from .cookies_paths import (
    COOKIES_DIR_REL,
    ensure_cookies_dir,
    is_sensitive_cookie_rel,
    list_site_cookie_files,
    site_cookie_rel_from_basename,
)
from .editor_files import (
    COOKIES_TXT,
    EDITABLE_FILENAMES,
    resolve_editor_file,
    strip_blank_lines,
)

_SCRIPTS_ROOT = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))
from archive_cookies import (  # noqa: E402
    clear_cookie_refresh_request,
    cookie_refresh_request_payload,
    cookie_refresh_requested,
    cookie_request_is_preflight,
    looks_like_netscape_cookies,
)

from .cookie_preflight import CookiePreflightTimeoutError  # noqa: E402

from .file_serve import (
    allowlisted_file_response,
    assert_reports_file_not_sensitive,
    collect_playable_rels_under_dir,
)
from .report_html_rewrite import rewrite_report_html
from .yt_dlp_config_model import FORMAT_PRESETS, TIER_A_GROUPS, YtdlpUiModel, model_from_dict
from .yt_dlp_conf_io import (
    extract_generated_banner_info,
    parse_conf,
    parse_conf_with_report,
    preview_cli,
    rejected_ytdlp_cli_options,
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
from .run_error_record import make_error_record, record_to_sidecar_or_global
from .run_summary import enrich_history_entry_for_api, merge_run_summary_into_history_entry
from .oneoff_report_read import oneoff_rolling_payload
from .oneoff_url import normalize_oneoff_youtube_url
from .bookmark_utils import (
    MAX_BOOKMARK_URLS_PER_LABELS_REQUEST,
    assert_safe_http_url_for_ssrf,
    bookmark_labels_for_urls,
    fetch_bookmark_icon,
    normalize_bookmark_url,
)
from .weather_home import (
    effective_openweather_api_key,
    fetch_weather_home,
    normalize_and_validate_weather_lat_lon,
)
from .paths import (
    PathNotAllowedError,
    assert_allowed_path,
    is_allowed,
    normalize_rel,
    resolve_under_root,
)
from .exiftool_read import validate_exiftool_exe_setting
from .rename_folder import folder_candidates_payload
from .rename_pipeline import (
    MAX_FILES_HARD,
    RenamePreviewOptions,
    apply_rename_preview,
    build_rename_preview,
    preview_operation_label_from_options,
)
from .run_manager import (
    BATCH_NAMES,
    JobName,
    MonthlyJobName,
    RunManager,
    RunPhase,
    RunState,
)
from .schedule_util import next_run_iso
from .storage_cleanup import build_preview, execute_cleanup, preview_to_api_dict
from .supported_sites import build_supported_sites_payload, enrich_supported_sites_with_cookies
from .tool_versions import build_tools_versions_payload
from .pre_run_notify import pre_run_reminder_banner
from .deepl_translate import (
    DeepLClientError,
    DEEPL_MAX_TEXTS_PER_REQUEST,
    effective_deepl_api_key,
    fetch_usage,
    resolve_deepl_base_url,
)
from .gotify_notify import notify_run_finished, notify_run_started, send_test_message
from .settings import (
    CONSOLE_DIR,
    CookieHygieneSettings,
    ConsoleState,
    DEFAULT_LANDING_VIEWS,
    DownloadDirsSettings,
    HomeBookmark,
    OperatorBackupConfig,
    PreRunReminderSettings,
    ScheduleEntry,
    StorageRetentionConfig,
    YtdlpBatchRunSettings,
    append_history,
    append_rename_done_log,
    append_rename_failure_event,
    append_rename_run,
    effective_tray_notify_port,
    effective_gotify_app_token,
    load_state,
    normalize_gotify_base_url,
    save_state,
    validate_archive_root_setting,
    validate_gotify_app_token,
)

logger = logging.getLogger(__name__)

ARCHIVE_CONSOLE_DOC = CONSOLE_DIR / "ARCHIVE_CONSOLE.md"

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
_gifsky_manager: GifskyBatchManager | None = None
_dup_manager: DuplicateScanManager | None = None
_czk_manager: CzkawkaScanManager | None = None


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


def _get_gifsky_manager() -> GifskyBatchManager:
    global _gifsky_manager
    if _gifsky_manager is None:
        _gifsky_manager = GifskyBatchManager(
            get_state=_get_state,
            persist_state=_persist_state,
        )
    return _gifsky_manager


def _get_dup_manager() -> DuplicateScanManager:
    global _dup_manager
    if _dup_manager is None:
        _dup_manager = DuplicateScanManager(
            get_state=_get_state,
            persist_state=_persist_state,
        )
    return _dup_manager


def _get_czk_manager() -> CzkawkaScanManager:
    global _czk_manager
    if _czk_manager is None:
        _czk_manager = CzkawkaScanManager(
            get_state=_get_state,
            persist_state=_persist_state,
        )
    return _czk_manager


def _history_error_stage_for_job(job: str) -> str:
    if job == "galleries":
        return "galleries-dl"
    return "yt-dlp"


def _error_record_for_finished_run(
    finished: RunState,
    entry: dict[str, Any],
) -> dict[str, Any] | None:
    if (
        finished.phase == RunPhase.success
        and finished.exit_code == 0
        and not finished.failure_detail
    ):
        return None
    sev = "warning" if finished.phase == RunPhase.canceled else "error"
    parts: list[str] = []
    if finished.phase == RunPhase.canceled:
        parts.append("Run stopped by operator.")
    elif finished.phase == RunPhase.failed:
        parts.append("Run failed.")
    elif finished.exit_code not in (0, None):
        parts.append("Exited with non-zero status.")
    if finished.failure_detail:
        parts.append(str(finished.failure_detail))
    msg = " ".join(parts).strip() or "Run did not complete successfully."
    tech: dict[str, Any] = {
        "phase": finished.phase.value,
        "exit_code": finished.exit_code,
    }
    fd = entry.get("failure_detail")
    if fd:
        tech["failure_detail"] = str(fd)[:500]
    retry = finished.phase == RunPhase.failed and (
        finished.exit_code is None or finished.exit_code != 0
    )
    return make_error_record(
        stage=_history_error_stage_for_job(finished.job),  # type: ignore[arg-type]
        operation="download_run_complete",
        message=msg,
        severity=sev,  # type: ignore[arg-type]
        run_id=finished.run_id,
        technical=tech,
        retryable=retry,
    )


async def _on_run_complete(finished: RunState | None) -> None:
    if finished is None:
        return
    await asyncio.to_thread(_on_run_complete_sync, finished)
    if finished.job == "galleries" and finished.run_meta.get("gallery_batch_total"):
        try:
            if finished.phase == RunPhase.canceled:
                await stop_gallery_source_batch_after_user_cancel(finished)
            else:
                await continue_gallery_source_batch_if_any(
                    _get_manager(),
                    _on_run_complete,
                    finished=finished,
                )
        except Exception:
            logger.exception("gallery source batch continue failed")


def _on_run_complete_sync(finished: RunState) -> None:
    st = _get_state()
    root = Path(st.archive_root).expanduser().resolve()
    prefixes = list(state_allowed_prefixes(st))
    entry: dict[str, Any] = {
        "run_id": finished.run_id,
        "job": finished.job,
        "started_unix": finished.started_unix,
        "ended_unix": finished.ended_unix,
        "exit_code": finished.exit_code,
        "log_folder_rel": finished.log_folder_rel,
        "phase": finished.phase.value,
    }
    if finished.failure_detail:
        entry["failure_detail"] = finished.failure_detail
    entry = merge_run_summary_into_history_entry(root, entry)
    rec = _error_record_for_finished_run(finished, entry)
    error_message: str | None = None
    if rec:
        error_message = str(rec.get("message") or "").strip() or None
        st = record_to_sidecar_or_global(
            archive_root=root,
            allowed_prefixes=prefixes,
            log_folder_rel=entry.get("log_folder_rel"),
            record=rec,
            state=st,
        )
    st = append_history(st, entry)
    if finished.job == "galleries":
        try:
            record_gallery_source_after_run(root, finished)
        except (ValueError, OSError) as e:
            logger.warning("gallery source registry update failed: %s", e)
    save_state(st)
    global _state
    _state = st
    try:
        meta = finished.run_meta or {}
        if finished.job == "galleries" and meta.get("gallery_batch_total"):
            record_gallery_batch_source_result(finished, entry)
            if (
                is_gallery_batch_last_source(finished)
                and finished.phase != RunPhase.canceled
            ):
                flush_gallery_batch_gotify(st)
        else:
            notify_run_finished(st, finished, entry, error_message=error_message)
    except Exception:
        logger.exception("gotify notify on run complete failed")
    _state = load_state()


def _run_download_env(job: MonthlyJobName) -> dict[str, str] | None:
    st = _get_state()
    root = Path(st.archive_root).expanduser().resolve()
    extra: dict[str, str] = {}
    try:
        extra.update(extra_env_for_job(root, st.download_dirs, job))
    except PathNotAllowedError as e:
        raise HTTPException(
            status_code=400,
            detail=f"download_dirs invalid for run: {e}",
        ) from e
    extra.update(extra_env_for_ytdlp_batch(st.ytdlp_batch_run))
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
        "settings_host_browse_kinds": list(SETTINGS_HOST_BROWSE_KINDS),
        "gallery_dl_on_path": gallery_dl_executable_ready(),
        "gallery_sources_schedule_api": True,
        "schedule_jobs": [*BATCH_NAMES.keys(), GALLERY_SOURCES_SCHEDULE_JOB],
    }


@app.get("/api/tools/versions")
async def api_tools_versions() -> dict[str, Any]:
    """Read-only: yt-dlp, gallery-dl, ffmpeg --version (bounded); python from runtime."""
    st = _get_state()
    return await asyncio.to_thread(lambda: build_tools_versions_payload(st))


@app.get("/api/supported-sites")
async def api_supported_sites(
    refresh: bool = Query(
        False,
        description="Bypass short-TTL cache and re-query yt-dlp / gallery-dl CLIs",
    ),
) -> dict[str, Any]:
    """Extractor/site lists from locally installed yt-dlp and gallery-dl (read-only, cached)."""
    st = _get_state()
    root = Path(st.archive_root).expanduser().resolve()

    def _build() -> dict[str, Any]:
        payload = build_supported_sites_payload(force_refresh=refresh)
        return enrich_supported_sites_with_cookies(payload, root)

    return await asyncio.to_thread(_build)


def _static_asset_version(name: str) -> str:
    try:
        return str(int((STATIC_DIR / name).stat().st_mtime))
    except OSError:
        return "0"


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    tpl = jinja.get_template("index.html")
    return tpl.render(static_v=_static_asset_version("app.js"))


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


@app.get("/home")
def home_view_redirect() -> RedirectResponse:
    """Shallow alias: Flame-style Home / bookmarks dashboard."""
    return RedirectResponse(url="/?view=home", status_code=302)


class BookmarksLabelsBody(BaseModel):
    urls: list[str] = Field(default_factory=list)

    @field_validator("urls")
    @classmethod
    def _cap_urls(cls, v: list[str]) -> list[str]:
        if len(v) > MAX_BOOKMARK_URLS_PER_LABELS_REQUEST:
            raise ValueError(
                f"at most {MAX_BOOKMARK_URLS_PER_LABELS_REQUEST} URLs allowed"
            )
        return v


@app.post("/api/bookmarks/labels")
def api_bookmarks_labels(body: BookmarksLabelsBody) -> dict[str, Any]:
    """Stateless display labels for bookmark URLs (same-host collision rules)."""
    labels, titles = bookmark_labels_for_urls(body.urls)
    return {"labels": labels, "titles": titles}


MAX_HOME_BOOKMARKS = 200


class BookmarksReplaceBody(BaseModel):
    """Full replacement of the Home dashboard bookmark list."""

    bookmarks: list[HomeBookmark] = Field(default_factory=list)

    @field_validator("bookmarks")
    @classmethod
    def _cap_bookmarks(cls, v: list[HomeBookmark]) -> list[HomeBookmark]:
        if len(v) > MAX_HOME_BOOKMARKS:
            raise ValueError(f"at most {MAX_HOME_BOOKMARKS} bookmarks allowed")
        return v


def _bookmarks_payload(bookmarks: list[HomeBookmark]) -> dict[str, Any]:
    return {"bookmarks": [b.model_dump(by_alias=True) for b in bookmarks]}


@app.get("/api/bookmarks")
def api_bookmarks_get() -> dict[str, Any]:
    """Server-persisted Home bookmarks (survive host/port changes, unlike localStorage)."""
    return _bookmarks_payload(_get_state().home_bookmarks)


@app.put("/api/bookmarks")
def api_bookmarks_put(body: BookmarksReplaceBody) -> dict[str, Any]:
    """Replace the stored bookmark list; URLs are normalized and duplicate ids dropped."""
    cleaned: list[HomeBookmark] = []
    seen_ids: set[str] = set()
    for b in body.bookmarks:
        if b.id in seen_ids:
            continue
        try:
            url = normalize_bookmark_url(b.url)
        except ValueError as e:
            raise HTTPException(
                status_code=400, detail=f"invalid bookmark URL: {e}"
            ) from e
        seen_ids.add(b.id)
        cleaned.append(
            HomeBookmark(id=b.id, url=url, created_at=b.created_at or time.time())
        )
    st = _get_state().model_copy(update={"home_bookmarks": cleaned})
    _persist_state(st)
    return _bookmarks_payload(cleaned)


@app.get("/api/bookmark-icon")
async def api_bookmark_icon(
    url: str = Query(..., min_length=1, max_length=2048),
) -> Response:
    """Same-origin favicon proxy (SSRF-hardened)."""
    try:
        nu = normalize_bookmark_url(url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    try:
        assert_safe_http_url_for_ssrf(nu)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="URL not allowed") from e
    result = await asyncio.to_thread(fetch_bookmark_icon, nu)
    if not result:
        raise HTTPException(status_code=404, detail="icon not found")
    data, ct = result
    return Response(content=data, media_type=ct.split(";")[0].strip() or "application/octet-stream")


@app.get("/api/weather")
async def api_weather() -> dict[str, Any]:
    """Current conditions via Open-Meteo or OpenWeather (server-side; no client key leak)."""
    st = _get_state()
    return await asyncio.to_thread(fetch_weather_home, st)


class SettingsPatch(BaseModel):
    archive_root: str | None = None
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
    scheduler_enabled: bool | None = None
    tray_notify_port: int | None = Field(None, ge=0, le=65535)
    ffmpeg_exe: str | None = None
    gifski_exe: str | None = None
    czkawka_exe: str | None = None
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
    show_getting_started: bool | None = None
    getting_started_seen: bool | None = None
    default_landing_view: str | None = None
    # Home weather: both set together or both empty (env fallback). Key: store or clear.
    weather_latitude: str | None = None
    weather_longitude: str | None = None
    openweather_api_key: str | None = None
    openweather_api_key_clear: bool | None = None
    gotify_enabled: bool | None = None
    gotify_base_url: str | None = None
    gotify_app_token: str | None = None
    gotify_app_token_clear: bool | None = None
    gotify_notify_on_start: bool | None = None
    gotify_notify_on_complete: bool | None = None
    gotify_notify_scheduled: bool | None = None
    gotify_notify_manual: bool | None = None
    gotify_priority: int | None = Field(None, ge=0, le=10)
    ytdlp_batch_run: YtdlpBatchRunSettings | None = None


class RenamePreviewBody(BaseModel):
    rels: list[str]
    options: RenamePreviewOptions = Field(default_factory=RenamePreviewOptions)
    max_files: int = Field(50, ge=1, le=200)


class RenameApplyBody(BaseModel):
    preview_id: str = Field(..., min_length=8)
    folder_batch: "RenameFolderBatchContext | None" = None


class RenameFolderBatchContext(BaseModel):
    folder_rel: str = Field(..., min_length=1)
    pipeline_fp: str = Field(..., min_length=8)
    touch_mtime: bool = True


class RenameFolderCandidatesBody(BaseModel):
    folder_rel: str = Field(..., min_length=1)
    recursive: bool = True
    skip_done: bool = True
    options: RenamePreviewOptions = Field(default_factory=RenamePreviewOptions)


class RenameBrowseFolderBody(BaseModel):
    title: str = ""
    initial_path: str = ""


class RenameBrowseFilesBody(BaseModel):
    title: str = ""
    initial_path: str = ""


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


SETTINGS_HOST_BROWSE_KINDS: tuple[str, ...] = ("file", "directory", "archive_relative")


class SettingsHostBrowseBody(BaseModel):
    kind: str = "file"
    title: str = ""
    initial_path: str = ""

    @field_validator("kind")
    @classmethod
    def _kind_allowed(cls, v: str) -> str:
        v = (v or "file").strip()
        if v not in SETTINGS_HOST_BROWSE_KINDS:
            raise ValueError(
                "kind must be one of: " + ", ".join(SETTINGS_HOST_BROWSE_KINDS)
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


class CzkawkaScanBody(BaseModel):
    mode: str = "dup"
    directories: list[str]
    exclude_directories: list[str] = Field(default_factory=list)
    dup_method: str = "HASH"
    hash_type: str = "BLAKE3"
    minimal_file_size_kb: int = Field(1, ge=0, le=1_048_576)
    extension_macros: list[str] = Field(default_factory=list)
    number_of_big_files: int = Field(50, ge=1, le=10_000)


class CzkawkaApplyItem(BaseModel):
    group_id: str
    keep_path: str
    remove_paths: list[str]


class CzkawkaApplyBody(BaseModel):
    scan_id: str
    dry_run: bool = True
    mode: Literal["delete", "quarantine"] = "quarantine"
    quarantine_dir: str | None = None
    items: list[CzkawkaApplyItem]
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
        "allowlisted_rel_prefixes": state_allowed_prefixes(st),
        "allowlist_note": (
            "Derived automatically from Download output folders plus logs/ and cookies/. "
            "Each output root includes all subfolders (e.g. playlists/WL, "
            "playlists/Watch Later Archived)."
        ),
        "jobs": list(BATCH_NAMES.keys()),
        "schedule_jobs": [*BATCH_NAMES.keys(), GALLERY_SOURCES_SCHEDULE_JOB],
        "features": st.features.model_dump(),
        "ytdlp_batch_run": st.ytdlp_batch_run.model_dump(),
        "settings_schema_version": st.settings_schema_version,
        "schedules": [s.model_dump() for s in st.schedules],
        "schedule_hints": [
            {"schedule": s.model_dump(), "next_run": next_run_iso(s)}
            for s in st.schedules
        ],
        "scheduler_backend_active": sched_on,
        "scheduler_note": (
            "In-process scheduler is active: saved schedules on YouTube batch and Gallery batch "
            "run daily, weekly, or monthly at the set hour/minute (local machine time). "
            "Missed ticks while the PC sleeps are not replayed."
            if sched_on
            else "Scheduler is off. Enable it below, save, and restart the server. "
            "Configure job times on YouTube batch and Gallery batch → Saved sources."
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
        "gifski_exe": st.gifski_exe,
        "czkawka_exe": st.czkawka_exe,
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
        "show_getting_started": st.show_getting_started,
        "getting_started_seen": st.getting_started_seen,
        "default_landing_view": st.default_landing_view,
        "weather_latitude": st.weather_latitude,
        "weather_longitude": st.weather_longitude,
        "openweather_api_key_configured": bool(
            effective_openweather_api_key(st)
        ),
        "openweather_api_key_saved": bool((st.openweather_api_key or "").strip()),
        "gotify_enabled": st.gotify_enabled,
        "gotify_base_url": st.gotify_base_url,
        "gotify_app_token_configured": bool(effective_gotify_app_token(st)),
        "gotify_app_token_saved": bool((st.gotify_app_token or "").strip()),
        "gotify_notify_on_start": st.gotify_notify_on_start,
        "gotify_notify_on_complete": st.gotify_notify_on_complete,
        "gotify_notify_scheduled": st.gotify_notify_scheduled,
        "gotify_notify_manual": st.gotify_notify_manual,
        "gotify_priority": st.gotify_priority,
        "gotify_last_failure_unix": st.gotify_last_failure_unix,
        "gotify_last_failure_message": st.gotify_last_failure_message,
    }


@app.post("/api/settings")
def api_settings_update(patch: SettingsPatch) -> dict[str, str]:
    st = _get_state()
    updates: dict[str, Any] = {}
    if patch.archive_root is not None:
        try:
            updates["archive_root"] = validate_archive_root_setting(patch.archive_root)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
    if patch.port is not None:
        updates["port"] = patch.port
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
                root, patch.download_dirs, state_allowed_prefixes(st)
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
    if patch.scheduler_enabled is not None:
        feat_up["scheduler_enabled"] = patch.scheduler_enabled
    if feat_up:
        updates["features"] = st.features.model_copy(update=feat_up)
    if patch.tray_notify_port is not None:
        updates["tray_notify_port"] = patch.tray_notify_port
    if patch.ffmpeg_exe is not None:
        try:
            updates["ffmpeg_exe"] = validate_ffmpeg_exe_setting(patch.ffmpeg_exe)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
    if patch.gifski_exe is not None:
        try:
            updates["gifski_exe"] = validate_gifski_exe_setting(patch.gifski_exe)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
    if patch.czkawka_exe is not None:
        try:
            updates["czkawka_exe"] = validate_czkawka_exe_setting(patch.czkawka_exe)
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
            resolve_under_root(root, rel_n)
        except PathNotAllowedError as e:
            raise HTTPException(
                status_code=400,
                detail=f"duplicates quarantine path invalid: {e}",
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
    if patch.show_getting_started is not None:
        updates["show_getting_started"] = patch.show_getting_started
    if patch.getting_started_seen is not None:
        updates["getting_started_seen"] = bool(patch.getting_started_seen)
    if patch.default_landing_view is not None:
        dv = (patch.default_landing_view or "").strip()
        updates["default_landing_view"] = (
            dv if dv in DEFAULT_LANDING_VIEWS else "run"
        )
    if (
        patch.weather_latitude is not None
        or patch.weather_longitude is not None
    ):
        try:
            wlat, wlon = normalize_and_validate_weather_lat_lon(
                lat_in=patch.weather_latitude,
                lon_in=patch.weather_longitude,
                current_lat=st.weather_latitude,
                current_lon=st.weather_longitude,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        updates["weather_latitude"] = wlat
        updates["weather_longitude"] = wlon
    if patch.openweather_api_key_clear is True:
        updates["openweather_api_key"] = ""
    elif patch.openweather_api_key is not None:
        nk = patch.openweather_api_key.replace("\r", "").replace("\n", "").strip()
        if nk:
            updates["openweather_api_key"] = nk
    if patch.gotify_enabled is not None:
        updates["gotify_enabled"] = patch.gotify_enabled
    if patch.gotify_base_url is not None:
        raw_gu = (patch.gotify_base_url or "").strip()
        if raw_gu:
            try:
                updates["gotify_base_url"] = normalize_gotify_base_url(raw_gu)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e)) from e
        else:
            updates["gotify_base_url"] = ""
    if patch.gotify_app_token_clear is True:
        updates["gotify_app_token"] = ""
    elif patch.gotify_app_token is not None:
        raw_tok = patch.gotify_app_token.replace("\r", "").replace("\n", "").strip()
        if raw_tok:
            try:
                updates["gotify_app_token"] = validate_gotify_app_token(raw_tok)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e)) from e
    if patch.gotify_notify_on_start is not None:
        updates["gotify_notify_on_start"] = patch.gotify_notify_on_start
    if patch.gotify_notify_on_complete is not None:
        updates["gotify_notify_on_complete"] = patch.gotify_notify_on_complete
    if patch.gotify_notify_scheduled is not None:
        updates["gotify_notify_scheduled"] = patch.gotify_notify_scheduled
    if patch.gotify_notify_manual is not None:
        updates["gotify_notify_manual"] = patch.gotify_notify_manual
    if patch.gotify_priority is not None:
        updates["gotify_priority"] = patch.gotify_priority
    if patch.ytdlp_batch_run is not None:
        updates["ytdlp_batch_run"] = patch.ytdlp_batch_run
    st = st.model_copy(update=updates)
    if st.gotify_enabled:
        if not (st.gotify_base_url or "").strip():
            raise HTTPException(
                status_code=400,
                detail="gotify_base_url is required when Gotify is enabled",
            )
        if not effective_gotify_app_token(st):
            raise HTTPException(
                status_code=400,
                detail="gotify_app_token is required when Gotify is enabled",
            )
    save_state(st)
    global _state, _manager, _clip_manager, _gifsky_manager, _dup_manager, _czk_manager
    _state = st
    if patch.archive_root is not None:
        _manager = None
        _clip_manager = None
        _gifsky_manager = None
        _dup_manager = None
        _czk_manager = None
    return {"ok": "true", "restart": "port or archive root change requires console restart"}


@app.post("/api/settings/gotify/test")
def api_settings_gotify_test() -> dict[str, str]:
    st = _get_state()
    ok, detail = send_test_message(st)
    global _state
    _state = load_state()
    if not ok:
        raise HTTPException(status_code=502, detail=detail)
    return {"ok": "true", "message": detail}


@app.post("/api/settings/download-dirs/preview")
def api_download_dirs_preview(body: DownloadDirsSettings) -> dict[str, Any]:
    st = _get_state()
    root = Path(st.archive_root).expanduser().resolve()
    try:
        validate_download_dirs(root, body, state_allowed_prefixes(st))
    except PathNotAllowedError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"download_dirs_effective": download_dirs_api_payload(root, body)}


_PICKER_UNAVAILABLE_DETAIL = (
    "Native picker is not available on this host (needs GUI/tkinter). "
    "Type the path manually, or run the console on Windows desktop."
)


@app.post("/api/settings/browse-host")
async def api_settings_browse_host(body: SettingsHostBrowseBody) -> Any:
    """Native file or folder picker on the console host (Settings path fields)."""
    title = (body.title or "").strip() or "Choose path"
    initial_raw = (body.initial_path or "").strip()
    initial: str | None = initial_raw or None
    if body.kind == "archive_relative" and initial_raw:
        st = _get_state()
        root = Path(st.archive_root).expanduser().resolve()
        initial = _rename_browse_initial_dir(root, initial_raw)
    elif not initial_raw:
        initial = None
    if body.kind == "file":
        status, payload = await asyncio.to_thread(pick_file_host, title, initial)
        if status == "unavailable":
            logger.warning("settings browse-host file: picker unavailable")
            raise HTTPException(status_code=503, detail=_PICKER_UNAVAILABLE_DETAIL)
        if status == "cancelled":
            return Response(status_code=204)
        logger.info("settings browse-host file picked")
        return {"kind": body.kind, "path": payload}

    status, payload = await asyncio.to_thread(pick_directory_host, title, initial)
    if status == "unavailable":
        logger.warning("settings browse-host %s: picker unavailable", body.kind)
        raise HTTPException(status_code=503, detail=_PICKER_UNAVAILABLE_DETAIL)
    if status == "cancelled":
        return Response(status_code=204)

    if body.kind == "directory":
        logger.info("settings browse-host directory picked")
        return {"kind": body.kind, "path": payload}

    st = _get_state()
    root = Path(st.archive_root).expanduser().resolve()
    try:
        rel_s, resolved = abs_folder_to_rel(
            root, Path(payload), state_allowed_prefixes(st)
        )
    except PathNotAllowedError as e:
        msg = str(e)
        if "outside archive root" in msg:
            msg = f"{msg} (configured archive root: {root})"
        raise HTTPException(status_code=400, detail=msg) from e
    logger.info("settings browse-host archive_relative picked rel=%s", rel_s)
    return {
        "kind": body.kind,
        "rel": rel_s,
        "path": str(resolved),
    }


@app.post("/api/settings/download-dirs/browse")
async def api_download_dirs_browse(body: BrowseDownloadDirBody) -> Any:
    st = _get_state()
    root = Path(st.archive_root).expanduser().resolve()
    labels: dict[str, str] = {
        "watch_later": "Watch Later / playlists output folder",
        "channels": "Channels batch output folder",
        "videos": "Videos list output folder",
        "oneoff": "Single download output folder",
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
            root, Path(payload), state_allowed_prefixes(st)
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
            root, Path(payload), state_allowed_prefixes(st)
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
def api_duplicates_status(include_groups: bool = False) -> dict[str, Any]:
    return _get_dup_manager().status(include_groups=include_groups)


@app.get("/api/duplicates/results")
def api_duplicates_results() -> dict[str, Any]:
    return _get_dup_manager().results()


@app.post("/api/duplicates/reset")
async def api_duplicates_reset() -> dict[str, Any]:
    reset = await _get_dup_manager().force_reset_running("operator reset")
    return {"ok": True, "reset": reset}


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
    prefixes = state_allowed_prefixes(st)
    mode = body.mode
    qrel = (st.duplicates_quarantine_rel or "logs/_duplicates_quarantine").strip()
    items_dump = [it.model_dump() for it in body.items]
    try:
        result = apply_duplicate_removals(
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
    except OSError as e:
        rec = make_error_record(
            stage="duplicates",
            operation="apply_duplicate_removals",
            message=str(e),
            technical={"exception_class": type(e).__name__},
            context={"mode": mode, "dry_run": body.dry_run},
        )
        st2 = record_to_sidecar_or_global(
            archive_root=root,
            allowed_prefixes=prefixes,
            log_folder_rel=None,
            record=rec,
            state=st,
        )
        _persist_state(st2)
        raise HTTPException(status_code=500, detail=str(e)) from e
    if not body.dry_run:
        _get_dup_manager().clear_results_if_idle()
    return result


@app.post("/api/czkawka/browse-directory")
async def api_czkawka_browse_directory() -> dict[str, Any]:
    """Native folder picker on the console host (any directory — not limited to allowlist)."""
    status, payload = pick_directory_host("Choose folder to scan with Czkawka")
    if status == "unavailable":
        raise HTTPException(
            status_code=503,
            detail=payload or "Folder picker unavailable on this host",
        )
    if status == "cancelled":
        return {"ok": False, "cancelled": True, "path": ""}
    return {"ok": True, "cancelled": False, "path": payload}


@app.get("/api/czkawka/suggested-paths")
def api_czkawka_suggested_paths() -> dict[str, Any]:
    """Resolved absolute paths useful for quick-add (e.g. Galleries output root)."""
    st = _get_state()
    root = Path(st.archive_root).expanduser().resolve()
    try:
        galleries_abs = str(effective_galleries_root(root, st.download_dirs))
    except PathNotAllowedError:
        galleries_abs = None
    exists = bool(galleries_abs and Path(galleries_abs).is_dir())
    return {
        "archive_root": str(root),
        "galleries_abs": galleries_abs,
        "galleries_exists": exists,
        "archive_root_suspicious": "pytest-of" in str(root).lower()
        or "\\temp\\pytest" in str(root).lower(),
    }


@app.post("/api/czkawka/scan")
async def api_czkawka_scan(body: CzkawkaScanBody) -> dict[str, str]:
    mgr = _get_czk_manager()
    macros = [m.strip().upper() for m in body.extension_macros if m and m.strip()]
    try:
        scan_id = await mgr.start_scan(
            mode=body.mode.strip(),
            directories=body.directories,
            exclude_directories=body.exclude_directories,
            dup_method=body.dup_method.strip().upper(),
            hash_type=body.hash_type.strip().upper(),
            minimal_file_size=max(0, body.minimal_file_size_kb) * 1024,
            extension_macros=macros or None,
            number_of_big_files=body.number_of_big_files,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"scan_id": scan_id}


@app.get("/api/czkawka/status")
def api_czkawka_status(include_results: bool = False) -> dict[str, Any]:
    return _get_czk_manager().status(include_results=include_results)


@app.get("/api/czkawka/results")
def api_czkawka_results() -> dict[str, Any]:
    return _get_czk_manager().results()


@app.post("/api/czkawka/reset")
async def api_czkawka_reset() -> dict[str, Any]:
    reset = await _get_czk_manager().force_reset_running("Stopped by operator")
    return {"ok": True, "reset": reset, "stopped": reset}


@app.post("/api/czkawka/apply")
def api_czkawka_apply(body: CzkawkaApplyBody) -> dict[str, Any]:
    if not body.items:
        raise HTTPException(status_code=400, detail="items required")
    if not body.dry_run:
        if (body.confirm or "").strip() != CZKAWKA_APPLY_CONFIRM:
            raise HTTPException(
                status_code=400,
                detail=f'Set confirm to "{CZKAWKA_APPLY_CONFIRM}" to apply removals',
            )
    mgr = _get_czk_manager()
    scan = mgr.get_successful_scan(body.scan_id.strip())
    if scan is None:
        raise HTTPException(
            status_code=404,
            detail="scan not found or not finished successfully",
        )
    if scan.mode != "dup":
        raise HTTPException(
            status_code=400,
            detail="apply is only supported for duplicate (dup) scan mode",
        )
    results = scan.results
    if not results or not results.get("groups"):
        raise HTTPException(status_code=400, detail="scan has no duplicate groups")

    st = _get_state()
    root = Path(st.archive_root).expanduser().resolve()
    try:
        group_index = group_paths_index(results)
        normalized = validate_apply_items(
            [it.model_dump() for it in body.items],
            group_index=group_index,
        )
        qdir = resolve_quarantine_dir(
            root,
            quarantine_rel=st.duplicates_quarantine_rel,
            override_abs=body.quarantine_dir,
        )
        audit_path = (
            root
            / "logs"
            / "_czkawka_scans"
            / f"apply_{scan.scan_id}_{int(time.time())}.json"
        )
        out = apply_czkawka_removals(
            items=normalized,
            mode=body.mode,
            quarantine_dir=qdir,
            dry_run=body.dry_run,
            audit_log_path=audit_path if not body.dry_run else None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except OSError as e:
        rec = make_error_record(
            stage="czkawka",
            operation="czkawka_apply",
            message=str(e),
            technical={"exception_class": type(e).__name__},
            context={"mode": body.mode, "dry_run": body.dry_run},
        )
        st2 = record_to_sidecar_or_global(
            archive_root=root,
            allowed_prefixes=list(state_allowed_prefixes(st)),
            log_folder_rel=None,
            record=rec,
            state=st,
        )
        _persist_state(st2)
        raise HTTPException(status_code=500, detail=str(e)) from e

    if not body.dry_run:
        removed_keys: set[str] = set()
        for it in normalized:
            for fp in it["remove_paths"]:
                removed_keys.add(path_key(fp))
        updated = prune_results_after_apply(results, removed_keys)
        mgr.update_results(scan.scan_id, updated)
        out["results"] = updated
        out["group_count"] = updated.get("group_count", 0)
    else:
        out["quarantine_dir"] = str(qdir)
    return out


def _rename_preview_http_error(
    *,
    status_code: int,
    message: str,
    error_code: str,
) -> HTTPException:
    """Structured JSON detail for /api/rename/preview (no secrets or stack traces)."""
    return HTTPException(
        status_code=status_code,
        detail={"message": message, "error_code": error_code},
    )


def _rename_ledger_structured_record(
    *,
    error_code: str,
    message: str,
    diagnostic_ref: str,
    api_operation: str,
    preview_id: str | None = None,
    rel_count: int = 0,
) -> dict[str, Any]:
    stg = "deepL" if str(error_code).startswith("deepl") else "rename"
    ctx: dict[str, Any] = {"diagnostic_ref": diagnostic_ref[:32]}
    if preview_id:
        ctx["preview_id"] = preview_id[:64]
    if rel_count:
        ctx["rel_count"] = rel_count
    return make_error_record(
        stage=stg,  # type: ignore[arg-type]
        operation=api_operation,
        message=(message or "")[:800],
        technical={"error_code": str(error_code)[:120]},
        context=ctx,
        job_id=diagnostic_ref[:32],
    )


def _persist_preview_ledger_failure(
    st: ConsoleState,
    body: RenamePreviewBody,
    *,
    error_code: str,
    message: str,
    diagnostic_ref: str,
) -> ConsoleState:
    try:
        op = preview_operation_label_from_options(body.options)
    except Exception:
        op = "rename"
    rec = _rename_ledger_structured_record(
        error_code=error_code,
        message=message,
        diagnostic_ref=diagnostic_ref,
        api_operation="api_rename_preview",
        rel_count=len(body.rels or []),
    )
    st2 = append_rename_failure_event(
        st,
        ledger_kind="rename_preview_failed",
        operation=op,
        error_code=error_code,
        message=(message or "")[:800],
        rel_count=len(body.rels or []),
        diagnostic_ref=diagnostic_ref,
        error_records=[rec],
    )
    save_state(st2)
    logger.info(
        "Rename preview failed diagnostic_ref=%s error_code=%s",
        diagnostic_ref,
        error_code,
    )
    return st2


def _persist_apply_ledger_failure(
    st: ConsoleState,
    *,
    error_code: str,
    message: str,
    diagnostic_ref: str,
    preview_id: str,
) -> ConsoleState:
    rec = _rename_ledger_structured_record(
        error_code=error_code,
        message=message,
        diagnostic_ref=diagnostic_ref,
        api_operation="api_rename_apply",
        preview_id=preview_id,
    )
    st2 = append_rename_failure_event(
        st,
        ledger_kind="rename_apply_failed",
        operation="rename_apply",
        error_code=error_code,
        message=(message or "")[:800],
        rel_count=0,
        diagnostic_ref=diagnostic_ref,
        preview_id=preview_id,
        error_records=[rec],
    )
    save_state(st2)
    logger.info(
        "Rename apply failed diagnostic_ref=%s error_code=%s",
        diagnostic_ref,
        error_code,
    )
    return st2


@app.get("/docs/archive-console", response_class=FileResponse)
def archive_console_markdown() -> FileResponse:
    """Operator reference: Rename, ExifTool, DeepL, allowlist (markdown on disk)."""
    if not ARCHIVE_CONSOLE_DOC.is_file():
        raise HTTPException(status_code=404, detail="ARCHIVE_CONSOLE.md not found")
    return FileResponse(
        str(ARCHIVE_CONSOLE_DOC),
        media_type="text/markdown; charset=utf-8",
        filename="ARCHIVE_CONSOLE.md",
    )


def _rename_browse_initial_dir(
    archive_root: Path,
    initial_path: str,
) -> str:
    root = archive_root.resolve()
    initial = (initial_path or "").strip()
    if initial:
        try:
            p = Path(initial).expanduser()
            if not p.is_absolute():
                p = root / initial
            if p.is_file():
                return str(p.parent.resolve())
            if p.is_dir():
                return str(p.resolve())
            if p.parent.is_dir():
                return str(p.parent.resolve())
        except OSError:
            pass
    return str(root)


@app.post("/api/rename/browse-files")
async def api_rename_browse_files(
    body: RenameBrowseFilesBody | None = None,
) -> Any:
    """Native multi-select file picker; returns archive-relative paths for Rename queue."""
    req = body or RenameBrowseFilesBody()
    st = _get_state()
    root = Path(st.archive_root).expanduser().resolve()
    title = (req.title or "").strip() or "Choose files to rename"
    initial_dir = _rename_browse_initial_dir(root, req.initial_path)
    status, picked = await asyncio.to_thread(
        pick_files_host, title, initial_dir
    )
    if status == "unavailable":
        logger.warning("rename browse-files: picker unavailable")
        raise HTTPException(status_code=503, detail=_PICKER_UNAVAILABLE_DETAIL)
    if status == "cancelled":
        return Response(status_code=204)

    rels: list[str] = []
    skipped: list[dict[str, str]] = []
    seen: set[str] = set()
    for abs_s in picked:
        try:
            rel_s, _resolved = abs_file_to_rel(
                root, Path(abs_s), state_allowed_prefixes(st)
            )
        except PathNotAllowedError as e:
            reason = str(e)
            skipped.append({"path": abs_s, "reason": reason})
            continue
        if rel_s in seen:
            continue
        seen.add(rel_s)
        rels.append(rel_s)

    if not rels and skipped:
        raise HTTPException(
            status_code=400,
            detail=(
                "No selected files are under the archive root or your download output folders. "
                "Pick files inside a folder configured under Input lists → Download output folders, "
                "or under logs/. "
                + (
                    f"First skip reason: {skipped[0]['reason']}"
                    if skipped
                    else ""
                )
            ),
        )

    logger.info("rename browse-files picked count=%s skipped=%s", len(rels), len(skipped))
    return {"rels": rels, "skipped": skipped}


@app.post("/api/rename/browse-folder")
async def api_rename_browse_folder(
    body: RenameBrowseFolderBody | None = None,
) -> Any:
    """Native folder picker; returns archive-relative folder path for folder batch rename."""
    req = body or RenameBrowseFolderBody()
    st = _get_state()
    root = Path(st.archive_root).expanduser().resolve()
    title = (req.title or "").strip() or "Choose folder to rename files in"
    initial_dir = _rename_browse_initial_dir(root, req.initial_path)
    status, picked = await asyncio.to_thread(
        pick_directory_host, title, initial_dir
    )
    if status == "unavailable":
        raise HTTPException(status_code=503, detail=_PICKER_UNAVAILABLE_DETAIL)
    if status == "cancelled":
        return Response(status_code=204)
    try:
        rel_s, _resolved = abs_folder_to_rel(
            root, Path(picked), state_allowed_prefixes(st)
        )
    except PathNotAllowedError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"folder_rel": rel_s}


@app.post("/api/rename/folder-candidates")
def api_rename_folder_candidates(body: RenameFolderCandidatesBody) -> dict[str, Any]:
    """List files under a folder for batch rename; optionally skip prior successes."""
    st = _get_state()
    root = Path(st.archive_root).expanduser().resolve()
    try:
        return folder_candidates_payload(
            archive_root=root,
            allowed_prefixes=state_allowed_prefixes(st),
            folder_rel=body.folder_rel,
            done_log=st.rename_done_log,
            opt=body.options,
            target_lang=st.deepl_target_lang,
            source_lang=st.deepl_source_lang,
            endpoint_mode=st.deepl_endpoint_mode,
            recursive=body.recursive,
            skip_done=body.skip_done,
        )
    except PathNotAllowedError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.get("/api/rename/deepl-usage")
def api_rename_deepl_usage(
    queue_size: int = Query(0, ge=0, le=MAX_FILES_HARD),
) -> dict[str, Any]:
    """DeepL billing-period usage and limits for Rename queue planning."""
    st = _get_state()
    api_key = effective_deepl_api_key(st.deepl_api_key)
    if not api_key:
        return {
            "configured": False,
            "message": "DeepL API key is not configured (Settings → DeepL).",
        }
    base = resolve_deepl_base_url(api_key, st.deepl_endpoint_mode)
    try:
        usage = fetch_usage(api_key=api_key, endpoint_base=base)
    except DeepLClientError as e:
        return {
            "configured": True,
            "error_code": e.code,
            "message": str(e),
        }
    char_count = int(usage.get("character_count") or 0)
    char_limit = int(usage.get("character_limit") or 0)
    remaining = max(0, char_limit - char_count) if char_limit > 0 else None
    preview_cap = min(queue_size, MAX_FILES_HARD) if queue_size > 0 else MAX_FILES_HARD
    batch_count = (
        (preview_cap + DEEPL_MAX_TEXTS_PER_REQUEST - 1) // DEEPL_MAX_TEXTS_PER_REQUEST
        if preview_cap > 0
        else 0
    )
    return {
        "configured": True,
        "character_count": char_count,
        "character_limit": char_limit,
        "character_remaining": remaining,
        "document_count": usage.get("document_count"),
        "document_limit": usage.get("document_limit"),
        "queue_size": queue_size,
        "preview_cap": preview_cap,
        "deepl_batch_size": DEEPL_MAX_TEXTS_PER_REQUEST,
        "estimated_api_batches": batch_count,
        "limits_note": (
            f"DeepL allows up to {DEEPL_MAX_TEXTS_PER_REQUEST} texts per request; "
            "preview sends batched requests with short pauses (~50 req/s recommended)."
        ),
    }


@app.post("/api/rename/preview")
def api_rename_preview(body: RenamePreviewBody) -> dict[str, Any]:
    st = _get_state()
    root = Path(st.archive_root).expanduser().resolve()
    diagnostic_ref = uuid.uuid4().hex[:12]
    global _state
    try:
        return build_rename_preview(
            archive_root=root,
            allowed_prefixes=state_allowed_prefixes(st),
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
        msg = str(e)
        logger.info(
            "Rename preview validation failed diagnostic_ref=%s: %s",
            diagnostic_ref,
            msg,
        )
        _state = _persist_preview_ledger_failure(
            st,
            body,
            error_code="rename_preview_validation",
            message=msg,
            diagnostic_ref=diagnostic_ref,
        )
        raise _rename_preview_http_error(
            status_code=400,
            message=msg,
            error_code="rename_preview_validation",
        ) from e
    except TypeError as e:
        logger.exception(
            "Rename preview TypeError diagnostic_ref=%s (see traceback)",
            diagnostic_ref,
        )
        safe_msg = (
            "Rename preview failed due to an internal type error. "
            "Check the server log for details."
        )
        _state = _persist_preview_ledger_failure(
            st,
            body,
            error_code="rename_preview_type_error",
            message=safe_msg,
            diagnostic_ref=diagnostic_ref,
        )
        raise _rename_preview_http_error(
            status_code=502,
            message=safe_msg,
            error_code="rename_preview_type_error",
        ) from e
    except DeepLClientError as e:
        msg = str(e)
        if e.code == "deepl_key_missing":
            logger.info(
                "Rename preview: DeepL key missing diagnostic_ref=%s",
                diagnostic_ref,
            )
            _state = _persist_preview_ledger_failure(
                st,
                body,
                error_code=e.code,
                message=msg,
                diagnostic_ref=diagnostic_ref,
            )
            raise _rename_preview_http_error(
                status_code=400,
                message=msg,
                error_code=e.code,
            ) from e
        code = (
            429
            if e.code == "deepl_rate_limit"
            else 400
            if e.code in ("deepl_quota_exceeded", "deepl_payload_too_large")
            else 502
        )
        logger.warning(
            "Rename preview DeepL error %s diagnostic_ref=%s: %s",
            e.code,
            diagnostic_ref,
            msg,
        )
        _state = _persist_preview_ledger_failure(
            st,
            body,
            error_code=e.code,
            message=msg,
            diagnostic_ref=diagnostic_ref,
        )
        raise _rename_preview_http_error(
            status_code=code,
            message=msg,
            error_code=e.code,
        ) from e
    except Exception as e:
        logger.exception(
            "Rename preview failed (%s) diagnostic_ref=%s",
            type(e).__name__,
            diagnostic_ref,
        )
        safe_msg = (
            "Rename preview hit an unexpected server error. "
            f"Check the server log for {type(e).__name__}; details are not sent here."
        )
        _state = _persist_preview_ledger_failure(
            st,
            body,
            error_code="rename_preview_unexpected",
            message=safe_msg,
            diagnostic_ref=diagnostic_ref,
        )
        raise _rename_preview_http_error(
            status_code=502,
            message=safe_msg,
            error_code="rename_preview_unexpected",
        ) from e


@app.post("/api/rename/apply")
def api_rename_apply(body: RenameApplyBody) -> dict[str, Any]:
    st = _get_state()
    root = Path(st.archive_root).expanduser().resolve()
    t0 = time.time()
    diagnostic_ref = uuid.uuid4().hex[:12]
    preview_id_s = body.preview_id.strip()
    global _state
    try:
        summary, pipeline_op = apply_rename_preview(
            archive_root=root,
            allowed_prefixes=state_allowed_prefixes(st),
            preview_id=preview_id_s,
            touch_mtime=bool(
                body.folder_batch and body.folder_batch.touch_mtime
            ),
        )
    except ValueError as e:
        msg = str(e)
        logger.info(
            "Rename apply validation failed diagnostic_ref=%s: %s",
            diagnostic_ref,
            msg,
        )
        _state = _persist_apply_ledger_failure(
            st,
            error_code="rename_apply_validation",
            message=msg,
            diagnostic_ref=diagnostic_ref,
            preview_id=preview_id_s,
        )
        raise HTTPException(status_code=400, detail=msg) from e
    except Exception as e:
        logger.exception(
            "Rename apply failed (%s) diagnostic_ref=%s",
            type(e).__name__,
            diagnostic_ref,
        )
        safe_msg = "Rename apply hit an unexpected server error. Check the server log."
        _state = _persist_apply_ledger_failure(
            st,
            error_code="rename_apply_unexpected",
            message=safe_msg,
            diagnostic_ref=diagnostic_ref,
            preview_id=preview_id_s,
        )
        raise HTTPException(status_code=500, detail=safe_msg) from e
    entry: dict[str, Any] = {
        "run_id": summary["run_id"],
        "status": "ok",
        "operation": pipeline_op,
        "started_unix": t0,
        "ended_unix": time.time(),
        "ok": summary["ok"],
        "skip": summary["skip"],
        "fail": summary["fail"],
        "items": summary["items"],
    }
    fail_items = [it for it in summary["items"] if it.get("status") == "fail"]
    if fail_items:
        entry["errors"] = [
            make_error_record(
                stage="rename",
                operation="apply_rename_preview",
                message=str(it.get("reason") or "rename failed"),
                severity="warning",
                run_id=str(summary["run_id"]),
                context={"rel": str(it.get("rel") or "")[:500]},
            )
            for it in fail_items[:40]
        ]
    st2 = append_rename_run(st, entry)
    if body.folder_batch:
        st2 = append_rename_done_log(
            st2,
            folder_rel=body.folder_batch.folder_rel,
            pipeline_fp=body.folder_batch.pipeline_fp,
            run_id=str(summary["run_id"]),
            items=summary["items"],
        )
    save_state(st2)
    _state = st2
    return summary


@app.get("/api/rename/history")
def api_rename_history() -> dict[str, Any]:
    st = _get_state()
    return {"items": st.rename_runs, "max": st.rename_runs_max}


@app.post("/api/settings/schedules")
def api_settings_schedules(body: SchedulesReplaceBody) -> dict[str, str]:
    valid = {*BATCH_NAMES.keys(), GALLERY_SOURCES_SCHEDULE_JOB}
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


def _manual_cookie_confirm_required(
    st: Any, *, dry_run: bool, cookie_confirm: bool
) -> bool:
    """Manual checkbox gate; skipped when extension preflight will refresh cookies.txt."""
    if dry_run:
        return False
    if not st.features.require_cookie_confirm_manual:
        return False
    if st.ytdlp_batch_run.preflight_via_extension:
        return False
    return not cookie_confirm


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
    if _manual_cookie_confirm_required(
        st0, dry_run=body.dry_run, cookie_confirm=body.cookie_confirm
    ):
        return JSONResponse(
            status_code=428,
            content={
                "error": "cookie_confirm_required",
                "message": (
                    "Confirm you have refreshed cookies.txt (Netscape format for youtube.com) "
                    "before starting this run, or enable extension preflight under Settings."
                ),
            },
        )
    mgr = _get_manager()
    extra = _run_download_env(body.job)
    if extra:
        logger.info("run start job=%s download_dir override active", body.job)
    try:
        ybr = st0.ytdlp_batch_run
        r = await mgr.start(
            body.job,
            dry_run=body.dry_run,
            skip_ytdlp_update=body.skip_ytdlp_update,
            skip_pip_update=body.skip_pip_update,
            on_complete=_on_run_complete,
            extra_env=extra,
            run_meta={"trigger": "manual"},
            preflight_via_extension=ybr.preflight_via_extension,
            preflight_wait_sec=ybr.preflight_wait_sec,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    except CookiePreflightTimeoutError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    st_g = _get_state()
    asyncio.create_task(asyncio.to_thread(notify_run_started, st_g, r))
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

    if _manual_cookie_confirm_required(
        st0, dry_run=body.dry_run, cookie_confirm=body.cookie_confirm
    ):
        return JSONResponse(
            status_code=428,
            content={
                "error": "cookie_confirm_required",
                "message": (
                    "Confirm you have refreshed cookies.txt (Netscape format for youtube.com) "
                    "before starting this run, or enable extension preflight under Settings."
                ),
            },
        )

    root = Path(st0.archive_root).expanduser().resolve()
    prefixes = state_allowed_prefixes(st0)
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
                detail="Output path is not under a download output folder",
            )
        extra["ARCHIVE_OUT_ONEOFF"] = str(full)
    else:
        try:
            validate_oneoff_output_dir(root, st0.download_dirs, prefixes)
            extra.update(extra_env_for_oneoff(root, st0.download_dirs))
        except PathNotAllowedError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    mgr = _get_manager()
    logger.info("oneoff start url=%s", url_norm[:80])
    try:
        ybr = st0.ytdlp_batch_run
        r = await mgr.start(
            "oneoff",
            dry_run=body.dry_run,
            skip_ytdlp_update=body.skip_ytdlp_update,
            skip_pip_update=body.skip_pip_update,
            on_complete=_on_run_complete,
            extra_env=extra,
            preflight_via_extension=ybr.preflight_via_extension,
            preflight_wait_sec=ybr.preflight_wait_sec,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    except CookiePreflightTimeoutError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
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
    cookies_path = cookies
    cookies_present = cookies_path.is_file()
    galleries_out = effective_galleries_root(root, st0.download_dirs)
    eff_conf = build_effective_gallery_conf_for_galleries(root, galleries_out)
    tmp_conf = write_merged_conf_temp(eff_conf)
    try:
        code, stdout, stderr = await asyncio.to_thread(
            run_gallery_dl_json_dump,
            exe=exe,
            url=url_norm,
            cwd=root,
            cookies_file=cookies_path if cookies_present else None,
            conf_file=tmp_conf,
            timeout_sec=body.timeout_sec,
        )
    finally:
        tmp_conf.unlink(missing_ok=True)
    combined = (stdout or "") + ("\n" + stderr if stderr else "")
    rows, parse_errs = parse_gallery_dl_json_lines(stdout, max_rows=500)
    truncated = len(rows) >= 500
    rows = dedupe_gallery_preview_rows_by_primary_url(rows)
    apply_smart_suggested_filenames(rows)
    empty = len(rows) == 0
    cookie_hint = (empty and cookie_likely_needed(combined)) or (
        empty and code not in (0, None) and "not recognized" not in combined.lower()
    )
    stderr_preview = ""
    if (empty and (stderr or "").strip()) or (
        code not in (0, None) and (stderr or "").strip()
    ):
        stderr_preview = sanitize_gallery_dl_stderr(stderr)
    logger.info(
        "galleries preview exit=%s rows=%s cookies_on_disk=%s parse_warnings=%s",
        code,
        len(rows),
        cookies_present,
        len(parse_errs),
    )
    recs: list[dict[str, Any]] = []
    if code == -124:
        recs.append(
            make_error_record(
                stage="galleries-dl",
                operation="galleries_preview",
                message="gallery-dl preview timed out",
                technical={"exit_code": code},
                context={"url_hint": url_norm[:200]},
                retryable=True,
            )
        )
    elif code not in (0, None):
        recs.append(
            make_error_record(
                stage="galleries-dl",
                operation="galleries_preview",
                message=f"gallery-dl preview exited with code {code}",
                technical={
                    "exit_code": code,
                    "stderr_excerpt": stderr_preview or "",
                },
                context={"url_hint": url_norm[:200]},
                retryable=True,
            )
        )
    elif empty and parse_errs:
        recs.append(
            make_error_record(
                stage="galleries-dl",
                operation="galleries_preview",
                message="Preview JSON had parse issues; row list may be incomplete",
                severity="warning",
                technical={"parse_warnings_count": len(parse_errs)},
                context={"url_hint": url_norm[:200]},
            )
        )
    if recs:
        st_mut = st0
        prefixes = list(state_allowed_prefixes(st0))
        for rec in recs:
            st_mut = record_to_sidecar_or_global(
                archive_root=root,
                allowed_prefixes=prefixes,
                log_folder_rel=None,
                record=rec,
                state=st_mut,
            )
        _persist_state(st_mut)
    return {
        "url": url_norm,
        "exit_code": code,
        "rows": rows,
        "parse_warnings": parse_errs[:20],
        "truncated": truncated,
        "cookie_required_hint": bool(cookie_hint and empty),
        "cookies_file_present": cookies_present,
        "cookies_passed_to_gallery_dl": cookies_present,
        "stderr_preview": stderr_preview,
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
    update_gallery_dl: bool = False


@app.post("/api/galleries/start")
async def galleries_start(body: GalleriesStartBody) -> Any:
    st0 = _get_state()
    try:
        url_norm = normalize_gallery_url(body.url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    root = Path(st0.archive_root).expanduser().resolve()
    prefixes = state_allowed_prefixes(st0)
    raw_url = body.url.strip()
    extra: dict[str, str] = {
        "ARCHIVE_GALLERY_URL": url_norm,
    }
    if raw_url and raw_url.rstrip("/") != url_norm.rstrip("/"):
        extra["ARCHIVE_GALLERY_URL_INPUT"] = raw_url
    gexe = (body.gallery_dl_exe or "").strip()
    if gexe:
        extra["ARCHIVE_GALLERY_DL_EXE"] = gexe
    if body.video_fallback:
        extra["ARCHIVE_GALLERY_VIDEO_FALLBACK"] = "1"
    if body.update_gallery_dl:
        extra["ARCHIVE_GALLERY_DL_UPDATE"] = "1"

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
                detail="Output path is not under a download output folder",
            )
        extra["ARCHIVE_OUT_GALLERIES"] = str(full)
    else:
        try:
            validate_galleries_output_dir(root, st0.download_dirs, prefixes)
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
            run_meta={"trigger": "manual", "gallery_url": url_norm},
        )
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    st_g = _get_state()
    asyncio.create_task(asyncio.to_thread(notify_run_started, st_g, r))
    return {
        "run_id": r.run_id,
        "job": r.job,
        "started_unix": r.started_unix,
    }


class GallerySourcesAddBody(BaseModel):
    url: str = ""


class GallerySourcesRemoveBody(BaseModel):
    ids: list[str] = Field(default_factory=list)


@app.get("/api/galleries/sources")
def galleries_sources_list() -> dict[str, Any]:
    st = _get_state()
    root = Path(st.archive_root).expanduser().resolve()
    return list_gallery_sources_for_api(root)


@app.post("/api/galleries/sources")
def galleries_sources_add(body: GallerySourcesAddBody) -> dict[str, Any]:
    try:
        url_norm = normalize_gallery_url(body.url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    st = _get_state()
    root = Path(st.archive_root).expanduser().resolve()
    raw_url = body.url.strip()
    try:
        row = upsert_gallery_source(
            root,
            url_norm,
            url_input=raw_url if raw_url.rstrip("/") != url_norm.rstrip("/") else None,
            touch_only=True,
        )
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Could not save sources file: {e}") from e
    return {"entry": row}


@app.post("/api/galleries/sources/remove")
def galleries_sources_remove(body: GallerySourcesRemoveBody) -> dict[str, Any]:
    st = _get_state()
    root = Path(st.archive_root).expanduser().resolve()
    try:
        removed = remove_gallery_sources(root, body.ids)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Could not update sources file: {e}") from e
    return {"removed": removed}


def _gallery_sources_schedule_entry(st: ConsoleState) -> ScheduleEntry | None:
    for s in st.schedules:
        if s.job == GALLERY_SOURCES_SCHEDULE_JOB:
            return s
    return None


class GallerySourcesScheduleBody(BaseModel):
    enabled: bool = False
    frequency: str = "daily"
    day_of_month: int = Field(1, ge=1, le=31)
    day_of_week: int = Field(0, ge=0, le=6)
    hour: int = Field(2, ge=0, le=23)
    minute: int = Field(0, ge=0, le=59)
    scheduled_max_run_sec: int | None = None


@app.get("/api/galleries/sources/schedule")
def galleries_sources_schedule_get() -> dict[str, Any]:
    st = _get_state()
    entry = _gallery_sources_schedule_entry(st)
    max_sec = int(st.gallery_batch_run.scheduled_max_run_sec)
    if entry is None:
        return {
            "schedule": None,
            "next_run": None,
            "scheduler_enabled": st.features.scheduler_enabled,
            "scheduled_max_run_sec": max_sec,
        }
    return {
        "schedule": entry.model_dump(),
        "next_run": next_run_iso(entry),
        "scheduler_enabled": st.features.scheduler_enabled,
        "scheduled_max_run_sec": max_sec,
    }


@app.post("/api/galleries/sources/schedule")
def galleries_sources_schedule_save(body: GallerySourcesScheduleBody) -> dict[str, Any]:
    st = _get_state()
    freq = (body.frequency or "daily").strip().lower()
    if freq not in ("daily", "weekly", "monthly"):
        raise HTTPException(status_code=400, detail="frequency must be daily, weekly, or monthly")
    new_entry = ScheduleEntry(
        id=GALLERY_SOURCES_SCHEDULE_ID,
        job=GALLERY_SOURCES_SCHEDULE_JOB,
        frequency=freq,  # type: ignore[arg-type]
        day_of_month=body.day_of_month,
        day_of_week=body.day_of_week,
        hour=body.hour,
        minute=body.minute,
        enabled=body.enabled,
    )
    kept = [s for s in st.schedules if s.job != GALLERY_SOURCES_SCHEDULE_JOB]
    kept.append(new_entry)
    updates: dict[str, Any] = {"schedules": kept}
    if body.scheduled_max_run_sec is not None:
        gbr = st.gallery_batch_run.model_copy(
            update={"scheduled_max_run_sec": int(body.scheduled_max_run_sec)}
        )
        updates["gallery_batch_run"] = gbr
    st = st.model_copy(update=updates)
    save_state(st)
    global _state
    _state = st
    return {
        "ok": "true",
        "schedule": new_entry.model_dump(),
        "next_run": next_run_iso(new_entry) if new_entry.enabled else None,
        "scheduler_enabled": st.features.scheduler_enabled,
        "scheduled_max_run_sec": int(st.gallery_batch_run.scheduled_max_run_sec),
    }


@app.get("/api/galleries/verification")
def galleries_verification(rel: str = Query(..., description="Run folder rel, e.g. logs/archive_run_*")) -> Any:
    st = _get_state()
    root = Path(st.archive_root).expanduser().resolve()
    try:
        folder = assert_allowed_path(root, rel, state_allowed_prefixes(st))
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
    return oneoff_rolling_payload(root, state_allowed_prefixes(st))


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
async def run_stop() -> dict[str, Any]:
    """Stop the tracked batch tree (Windows: taskkill /T on the spawned cmd PID only)."""
    mgr = _get_manager()
    try:
        await mgr.stop()
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return {"ok": True}


@app.post("/api/run/force-reset")
async def run_force_reset() -> dict[str, Any]:
    """Clear a stuck running job when Stop/stream desync (loopback only)."""
    mgr = _get_manager()
    reset = await mgr.force_reset_running("operator force-reset")
    status = await mgr.status()
    return {"ok": True, "reset": reset, "phase": status.get("phase")}


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
    prefixes = state_allowed_prefixes(st)
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
        rec = make_error_record(
            stage="metadata",
            operation="files_browse_iterdir",
            message=str(e),
            technical={"exception_class": type(e).__name__},
            context={"path": path[:500]},
        )
        st2 = record_to_sidecar_or_global(
            archive_root=root,
            allowed_prefixes=prefixes,
            log_folder_rel=None,
            record=rec,
            state=st,
        )
        _persist_state(st2)
        raise HTTPException(status_code=500, detail=str(e)) from e
    parent_rel = full.relative_to(root).as_posix() if full != root else ""
    return {"path": parent_rel or ".", "type": "dir", "entries": entries}


@app.get("/api/files/metadata")
def files_metadata(path: str = Query(...)) -> dict[str, Any]:
    st = _get_state()
    root = Path(st.archive_root).resolve()
    try:
        full = assert_allowed_path(root, path, state_allowed_prefixes(st))
    except PathNotAllowedError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    if not full.exists():
        raise HTTPException(status_code=404, detail="not found")
    try:
        st_l = full.stat()
    except OSError as e:
        rec = make_error_record(
            stage="metadata",
            operation="files_metadata_stat",
            message=str(e),
            technical={"exception_class": type(e).__name__},
            context={"path": path[:500]},
        )
        st2 = record_to_sidecar_or_global(
            archive_root=root,
            allowed_prefixes=list(state_allowed_prefixes(st)),
            log_folder_rel=None,
            record=rec,
            state=st,
        )
        _persist_state(st2)
        raise HTTPException(status_code=500, detail=str(e)) from e
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
        full = assert_allowed_path(root, path, state_allowed_prefixes(st))
    except PathNotAllowedError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    if not full.exists():
        raise HTTPException(status_code=404, detail="not found")
    exe = resolve_mediainfo_bin(st.mediainfo_exe)
    result = await asyncio.to_thread(mediainfo_for_file, exe, full)
    if not result.get("ok"):
        ec = result.get("error_code")
        rec = make_error_record(
            stage="metadata",
            operation="files_mediainfo",
            message=str(result.get("error") or "MediaInfo failed"),
            technical={"error_code": ec},
            context={"path": path[:500]},
            retryable=ec in ("timeout", "cli_failed"),
        )
        st2 = record_to_sidecar_or_global(
            archive_root=root,
            allowed_prefixes=list(state_allowed_prefixes(st)),
            log_folder_rel=None,
            record=rec,
            state=st,
        )
        _persist_state(st2)
    return result


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
            state_allowed_prefixes(st),
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


class YoutubeCookiesPutBody(BaseModel):
    content: str
    unlock_cookies: bool = True


@app.get("/api/cookies/youtube-refresh")
async def api_cookies_youtube_refresh_status() -> dict[str, Any]:
    """
    Poll from a browser extension or helper while a yt-dlp job is running.
    When refresh_needed is true, export Netscape cookies and PUT /api/cookies/youtube.
    """
    st = _get_state()
    root = Path(st.archive_root).resolve()
    ck = root / COOKIES_TXT
    mtime: float | None = None
    size: int | None = None
    if ck.is_file():
        stl = ck.stat()
        mtime = stl.st_mtime
        size = stl.st_size
    mgr = _get_manager()
    run = await mgr.status()
    payload = cookie_refresh_request_payload(str(root))
    return {
        "refresh_needed": cookie_refresh_requested(str(root)),
        "preflight_needed": bool(payload and cookie_request_is_preflight(payload)),
        "request": payload,
        "cookies_txt_mtime": mtime,
        "cookies_txt_size": size,
        "run": run,
    }


@app.put("/api/cookies/youtube")
async def api_cookies_youtube_put(body: YoutubeCookiesPutBody) -> dict[str, Any]:
    """
    Replace root cookies.txt during a run (cookie-auth pause path).
    Unlike PUT /api/files/cookies.txt, allowed while phase=running.
    """
    if not body.unlock_cookies:
        raise HTTPException(
            status_code=403,
            detail="unlock_cookies=true required to write cookies.txt",
        )
    if not looks_like_netscape_cookies(body.content):
        raise HTTPException(
            status_code=400,
            detail="Body does not look like a Netscape HTTP cookie file",
        )
    st = _get_state()
    root = Path(st.archive_root).resolve()
    full = root / COOKIES_TXT
    backup_rel: str | None = None
    if full.is_file():
        dest = write_backup_copy(full, COOKIES_TXT, st.editor_backup_max)
        if dest is not None:
            backup_rel = dest.relative_to(CONSOLE_DIR).as_posix()
    full.write_text(body.content, encoding="utf-8", newline="\n")
    clear_cookie_refresh_request(str(root))
    stl = full.stat()
    mgr = _get_manager()
    run = await mgr.status()
    return {
        "rel": COOKIES_TXT,
        "mtime": stl.st_mtime,
        "size": stl.st_size,
        "backup_rel": backup_rel,
        "refresh_cleared": True,
        "run": run,
    }


@app.get("/api/cookies/site-files")
def api_cookies_site_files() -> dict[str, Any]:
    """List per-site cookie files under cookies/ (gallery-dl). Ensures folder exists."""
    st = _get_state()
    root = Path(st.archive_root).resolve()
    ensure_cookies_dir(root)
    files = list_site_cookie_files(root)
    prefixes = {p.strip("/").replace("\\", "/") for p in state_allowed_prefixes(st)}
    return {
        "dir_rel": COOKIES_DIR_REL,
        "files": files,
        "cookies_txt_present": (root / COOKIES_TXT).is_file(),
        "allowlist_has_cookies_dir": COOKIES_DIR_REL in prefixes,
    }


class SiteCookieCreateBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)


@app.post("/api/cookies/site-files")
def api_cookies_site_files_create(body: SiteCookieCreateBody) -> dict[str, Any]:
    """Create an empty cookies/<site>.txt for gallery-dl per-extractor paths."""
    st = _get_state()
    root = Path(st.archive_root).resolve()
    ensure_cookies_dir(root)
    try:
        rel = site_cookie_rel_from_basename(body.name)
    except PathNotAllowedError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    full = (root / rel).resolve()
    if not str(full).startswith(str(root)):
        raise HTTPException(status_code=400, detail="Invalid cookie path")
    if full.is_file():
        raise HTTPException(status_code=409, detail=f"{rel} already exists")
    full.write_text("", encoding="utf-8")
    return {"rel": rel, "created": True}


@app.get("/api/files/{name:path}")
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
    if is_sensitive_cookie_rel(fname) and not unlock_cookies:
        mtime: float | None = None
        size: int | None = None
        if full.is_file():
            stl = full.stat()
            mtime = stl.st_mtime
            size = stl.st_size
        label = fname if fname != COOKIES_TXT else "cookies.txt"
        return {
            "rel": fname,
            "mtime": mtime,
            "size": size,
            "content": None,
            "locked": True,
            "warnings": [
                f"{label} is locked. Use “Unlock cookies” in the UI to load or edit "
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


@app.put("/api/files/{name:path}")
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
    if is_sensitive_cookie_rel(fname) and not body.unlock_cookies:
        label = fname if fname != COOKIES_TXT else "cookies.txt"
        raise HTTPException(
            status_code=403,
            detail=f"unlock_cookies=true required to write {label}",
        )
    text = body.content
    if body.strip_blank_lines and fname in (
        "playlists_input.txt",
        "channels_input.txt",
        "videos_input.txt",
    ):
        text = strip_blank_lines(text)
    warnings: list[str] = []
    if fname == "yt-dlp.conf":
        cli_rejects = rejected_ytdlp_cli_options(text)
        if cli_rejects:
            raise HTTPException(
                status_code=400,
                detail="; ".join(cli_rejects[:6]),
            )
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
        full = assert_allowed_path(root, body.path, state_allowed_prefixes(st))
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
        full = assert_allowed_path(root, rel, state_allowed_prefixes(st))
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
        full = assert_allowed_path(root, rel, state_allowed_prefixes(st))
    except PathNotAllowedError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    if not full.is_file():
        raise HTTPException(status_code=404, detail="not a file")
    assert_reports_file_not_sensitive(full)
    if full.suffix.lower() not in (".html", ".htm"):
        raise HTTPException(status_code=400, detail="reports/view accepts .html only")
    text = full.read_text(encoding="utf-8", errors="replace")
    body = rewrite_report_html(
        text,
        root,
        state_allowed_prefixes(st),
        report_path=full,
    )
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


async def _gallery_dl_require_idle() -> None:
    mgr = _get_manager()
    if (await mgr.status()).get("phase") == "running":
        raise HTTPException(
            status_code=409,
            detail="A download job is running. Wait for it to finish before changing gallery-dl.conf.",
        )


def _gallery_dl_conf_path() -> Path:
    return Path(_get_state().archive_root).expanduser().resolve() / "gallery-dl.conf"


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
    cli_rejects = rejected_ytdlp_cli_options(out_text)
    if cli_rejects:
        raise HTTPException(
            status_code=400,
            detail="; ".join(cli_rejects[:6]),
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
    try:
        p.write_text(out_text, encoding="utf-8", newline="\n")
    except OSError as e:
        root = Path(st.archive_root).expanduser().resolve()
        rec = make_error_record(
            stage="yt-dlp",
            operation="api_ytdlp_save",
            message=f"Could not write yt-dlp.conf: {e}",
            technical={"exception_class": type(e).__name__},
            context={"file": "yt-dlp.conf"},
        )
        st2 = record_to_sidecar_or_global(
            archive_root=root,
            allowed_prefixes=list(state_allowed_prefixes(st)),
            log_folder_rel=None,
            record=rec,
            state=st,
        )
        _persist_state(st2)
        raise HTTPException(
            status_code=500,
            detail="Could not write yt-dlp.conf (disk full, permissions, or path error).",
        ) from e
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
        m = model_from_dict(ui.user_preferences_snapshot)
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


@app.get("/api/gallery-dl/setup")
def api_gallery_dl_setup_get() -> dict[str, Any]:
    st = _get_state()
    root = Path(st.archive_root).expanduser().resolve()
    p = root / "gallery-dl.conf"
    text = p.read_text(encoding="utf-8", errors="replace") if p.is_file() else ""
    state, warnings = parse_gallery_dl_conf_text(text)
    ui = load_gallery_dl_ui_state()
    ser = serialize_gallery_dl_conf(state)
    mtime = p.stat().st_mtime if p.is_file() else None
    return {
        "state": state,
        "presets": GDL_PRESET_META,
        "preset_bar_note": PRESET_BAR_NOTE,
        "active_preset_id": ui.active_preset_id,
        "tier_a_groups": GDL_TIER_A_GROUPS,
        "user_snapshot_present": ui.user_preferences_snapshot is not None,
        "archive_root": str(root),
        "conf_path": str(p),
        "conf_exists": p.is_file(),
        "mtime": mtime,
        "parse_warnings": warnings,
        "preview": gdl_preview_cli(archive_root=root, state=state),
        "serialized_preview": gdl_clip_text(ser, 24000),
    }


class GalleryDlStateBody(BaseModel):
    state: dict[str, Any]


@app.post("/api/gallery-dl/setup/preview")
def api_gallery_dl_setup_preview(body: GalleryDlStateBody) -> dict[str, Any]:
    st = _get_state()
    root = Path(st.archive_root).expanduser().resolve()
    state = model_from_client_dict(body.state)
    ser = serialize_gallery_dl_conf(state)
    return {
        "preview": gdl_preview_cli(archive_root=root, state=state),
        "serialized_preview": gdl_clip_text(ser, 24000),
    }


class GalleryDlSaveBody(BaseModel):
    state: dict[str, Any]
    active_preset_id: str = "balanced"
    conf_smoke: bool = True


@app.post("/api/gallery-dl/setup/save")
async def api_gallery_dl_setup_save(body: GalleryDlSaveBody) -> dict[str, Any]:
    await _gallery_dl_require_idle()
    st = _get_state()
    state = model_from_client_dict(body.state)
    out_text = serialize_gallery_dl_conf(state)
    warnings: list[str] = []
    if body.conf_smoke:
        warnings.extend(smoke_gallery_dl_conf(json_text=out_text))
    p = _gallery_dl_conf_path()
    if p.is_file():
        dest = write_backup_copy(p, "gallery-dl.conf", st.editor_backup_max)
        if dest is None:
            pass
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        p.write_text(out_text, encoding="utf-8", newline="\n")
    except OSError as e:
        root = Path(st.archive_root).expanduser().resolve()
        rec = make_error_record(
            stage="galleries-dl",
            operation="api_gallery_dl_setup_save",
            message=f"Could not write gallery-dl.conf: {e}",
            technical={"exception_class": type(e).__name__},
            context={"file": "gallery-dl.conf"},
        )
        st2 = record_to_sidecar_or_global(
            archive_root=root,
            allowed_prefixes=list(state_allowed_prefixes(st)),
            log_folder_rel=None,
            record=rec,
            state=st,
        )
        _persist_state(st2)
        raise HTTPException(
            status_code=500,
            detail="Could not write gallery-dl.conf (disk full, permissions, or path error).",
        ) from e
    ui = load_gallery_dl_ui_state()
    save_gallery_dl_ui_state(
        ui.model_copy(update={"active_preset_id": body.active_preset_id}),
    )
    mtime = p.stat().st_mtime
    return {"ok": True, "warnings": warnings, "mtime": mtime, "conf_exists": True}


class GalleryDlPresetBody(BaseModel):
    preset_id: str


@app.post("/api/gallery-dl/setup/apply-preset")
def api_gallery_dl_apply_preset(body: GalleryDlPresetBody) -> dict[str, Any]:
    p = _gallery_dl_conf_path()
    text = p.read_text(encoding="utf-8", errors="replace") if p.is_file() else ""
    base, _ = parse_gallery_dl_conf_text(text)
    ui = load_gallery_dl_ui_state()
    if body.preset_id == "user_preferences":
        if not ui.user_preferences_snapshot:
            raise HTTPException(
                status_code=400,
                detail="Capture User preferences from disk first.",
            )
        new_state = gdl_apply_user_snapshot(base, ui.user_preferences_snapshot)
    elif body.preset_id not in {x["id"] for x in GDL_PRESET_META}:
        raise HTTPException(status_code=404, detail="Unknown preset")
    else:
        new_state = gdl_apply_builtin_preset(base, body.preset_id)
    save_gallery_dl_ui_state(
        ui.model_copy(update={"active_preset_id": body.preset_id}),
    )
    st = _get_state()
    root = Path(st.archive_root).expanduser().resolve()
    ser = serialize_gallery_dl_conf(new_state)
    return {
        "state": new_state,
        "active_preset_id": body.preset_id,
        "preview": gdl_preview_cli(archive_root=root, state=new_state),
        "serialized_preview": gdl_clip_text(ser, 24000),
    }


@app.post("/api/gallery-dl/setup/capture-user")
def api_gallery_dl_capture_user() -> dict[str, Any]:
    p = _gallery_dl_conf_path()
    if not p.is_file():
        raise HTTPException(status_code=404, detail="gallery-dl.conf not found")
    text = p.read_text(encoding="utf-8", errors="replace")
    state, _ = parse_gallery_dl_conf_text(text)
    ui = load_gallery_dl_ui_state()
    snap = copy.deepcopy(state)
    save_gallery_dl_ui_state(
        ui.model_copy(
            update={
                "user_preferences_snapshot": snap,
                "active_preset_id": "user_preferences",
            },
        ),
    )
    st = _get_state()
    root = Path(st.archive_root).expanduser().resolve()
    ser = serialize_gallery_dl_conf(state)
    return {
        "state": state,
        "active_preset_id": "user_preferences",
        "preview": gdl_preview_cli(archive_root=root, state=state),
        "serialized_preview": gdl_clip_text(ser, 24000),
    }


def _gifsky_conf_path() -> Path:
    st = _get_state()
    root = Path(st.archive_root).expanduser().resolve()
    return gifsky_conf_path(root)


@app.get("/api/gifsky/scan")
def api_gifsky_scan() -> dict[str, Any]:
    st = _get_state()
    root = Path(st.archive_root).expanduser().resolve()
    try:
        conf_text = ""
        p = _gifsky_conf_path()
        if p.is_file():
            conf_text = p.read_text(encoding="utf-8", errors="replace")
        conf, _ = parse_gifsky_conf_text(conf_text)
        return scan_gallery_videos(
            archive_root=root,
            allowed_prefixes=state_allowed_prefixes(st),
            download_dirs=st.download_dirs,
            conf=conf,
        )
    except PathNotAllowedError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


class GifskyStartBody(BaseModel):
    delete_source_after_verify: bool = False
    dry_run: bool = False
    folder_rels: list[str] = Field(default_factory=list)


@app.post("/api/gifsky/start")
async def api_gifsky_start(body: GifskyStartBody) -> dict[str, Any]:
    mgr = _get_gifsky_manager()
    try:
        job_id = await mgr.start(
            delete_source_after_verify=body.delete_source_after_verify,
            dry_run=body.dry_run,
            folder_rels=body.folder_rels or None,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except PathNotAllowedError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"job_id": job_id, "status": mgr.status()}


@app.get("/api/gifsky/status")
def api_gifsky_status() -> dict[str, Any]:
    return _get_gifsky_manager().status()


@app.post("/api/gifsky/cancel")
async def api_gifsky_cancel() -> dict[str, Any]:
    ok = await _get_gifsky_manager().cancel()
    if not ok:
        raise HTTPException(status_code=409, detail="No running gifsky batch")
    return {"canceled": True, "status": _get_gifsky_manager().status()}


@app.get("/api/gifsky/setup")
def api_gifsky_setup_get() -> dict[str, Any]:
    st = _get_state()
    root = Path(st.archive_root).expanduser().resolve()
    p = _gifsky_conf_path()
    text = p.read_text(encoding="utf-8", errors="replace") if p.is_file() else ""
    state, warnings = parse_gifsky_conf_text(text)
    ui = load_gifsky_ui_state()
    ser = serialize_gifsky_conf(state)
    mtime = p.stat().st_mtime if p.is_file() else None
    return {
        "state": state,
        "presets": GIFSKY_PRESET_META,
        "active_preset_id": ui.active_preset_id,
        "tier_a_groups": GIFSKY_TIER_A_GROUPS,
        "user_snapshot_present": ui.user_preferences_snapshot is not None,
        "archive_root": str(root),
        "conf_path": str(p),
        "conf_exists": p.is_file(),
        "mtime": mtime,
        "parse_warnings": warnings,
        "preview": gifsky_preview_summary(state),
        "serialized_preview": ser[:24000],
    }


class GifskyStateBody(BaseModel):
    state: dict[str, Any]


@app.post("/api/gifsky/setup/preview")
def api_gifsky_setup_preview(body: GifskyStateBody) -> dict[str, Any]:
    state = gifsky_model_from_client_dict(body.state)
    ser = serialize_gifsky_conf(state)
    return {
        "preview": gifsky_preview_summary(state),
        "serialized_preview": ser[:24000],
    }


class GifskySaveBody(BaseModel):
    state: dict[str, Any]
    active_preset_id: str = "hq_reddit"


@app.post("/api/gifsky/setup/save")
def api_gifsky_setup_save(body: GifskySaveBody) -> dict[str, Any]:
    state = gifsky_model_from_client_dict(body.state)
    out_text = serialize_gifsky_conf(state)
    p = _gifsky_conf_path()
    if p.is_file():
        write_backup_copy(p, "gifsky.conf", _get_state().editor_backup_max)
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        p.write_text(out_text, encoding="utf-8", newline="\n")
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Could not write gifsky.conf: {e}") from e
    ui = load_gifsky_ui_state()
    save_gifsky_ui_state(ui.model_copy(update={"active_preset_id": body.active_preset_id}))
    return {
        "ok": True,
        "conf_path": str(p),
        "preview": gifsky_preview_summary(state),
        "serialized_preview": out_text[:24000],
        "active_preset_id": body.active_preset_id,
    }


class GifskyPresetBody(BaseModel):
    preset_id: str


@app.post("/api/gifsky/setup/apply-preset")
def api_gifsky_apply_preset(body: GifskyPresetBody) -> dict[str, Any]:
    p = _gifsky_conf_path()
    text = p.read_text(encoding="utf-8", errors="replace") if p.is_file() else ""
    base, _ = parse_gifsky_conf_text(text)
    ui = load_gifsky_ui_state()
    if body.preset_id == "user_preferences":
        if not ui.user_preferences_snapshot:
            raise HTTPException(
                status_code=400,
                detail="Capture User preferences from disk first.",
            )
        new_state = copy.deepcopy(ui.user_preferences_snapshot)
    elif body.preset_id not in {x["id"] for x in GIFSKY_PRESET_META}:
        raise HTTPException(status_code=404, detail="Unknown preset")
    else:
        new_state = gifsky_apply_builtin_preset(base, body.preset_id)
    save_gifsky_ui_state(
        ui.model_copy(update={"active_preset_id": body.preset_id}),
    )
    ser = serialize_gifsky_conf(new_state)
    return {
        "state": new_state,
        "active_preset_id": body.preset_id,
        "preview": gifsky_preview_summary(new_state),
        "serialized_preview": ser[:24000],
    }


@app.post("/api/gifsky/setup/capture-user")
def api_gifsky_capture_user() -> dict[str, Any]:
    p = _gifsky_conf_path()
    if not p.is_file():
        raise HTTPException(status_code=404, detail="gifsky.conf not found")
    text = p.read_text(encoding="utf-8", errors="replace")
    state, _ = parse_gifsky_conf_text(text)
    ui = load_gifsky_ui_state()
    snap = copy.deepcopy(state)
    save_gifsky_ui_state(
        ui.model_copy(
            update={
                "user_preferences_snapshot": snap,
                "active_preset_id": "user_preferences",
            },
        ),
    )
    ser = serialize_gifsky_conf(state)
    return {
        "state": state,
        "active_preset_id": "user_preferences",
        "preview": gifsky_preview_summary(state),
        "serialized_preview": ser[:24000],
    }


@app.get("/api/history")
def api_history() -> dict[str, Any]:
    st = _get_state()
    root = Path(st.archive_root).expanduser().resolve()
    prefixes = list(state_allowed_prefixes(st))
    items = [
        enrich_history_entry_for_api(root, dict(h), allowed_prefixes=prefixes)
        for h in st.run_history
    ]
    return {
        "items": items,
        "max": st.run_history_max,
        "global_errors": list(st.console_errors),
        "global_errors_max": st.console_errors_max,
    }
