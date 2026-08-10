"""Load and save archive_console/state.json (no DB)."""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


CONSOLE_DIR = Path(__file__).resolve().parent.parent

DeepLEndpointMode = Literal["auto", "free", "pro"]
DEFAULT_STATE_PATH = CONSOLE_DIR / "state.json"
EXAMPLE_STATE_PATH = CONSOLE_DIR / "state.example.json"

# Sidebar data-view ids allowed as operator default landing page (must match app UI).
DEFAULT_LANDING_VIEWS: frozenset[str] = frozenset(
    {
        "getting-started",
        "home",
        "run",
        "oneoff",
        "galleries",
        "history",
        "library",
        "czkawka",
        "rename",
        "inputs",
        "ytdlp",
        "gallerydl",
        "gifsky",
        "gifskyconf",
        "supportedsites",
        "settings",
    }
)


ScheduleFrequency = Literal["daily", "weekly", "monthly", "interval"]


class ScheduleEntry(BaseModel):
    """Repeating schedule: daily, weekly, monthly, or every N hours (interval)."""

    id: str = ""
    job: str = "watch_later"
    frequency: ScheduleFrequency = "monthly"
    day_of_month: int = Field(1, ge=1, le=31)
    day_of_week: int = Field(0, ge=0, le=6)  # Mon=0 … Sun=6 (datetime.weekday())
    hour: int = Field(3, ge=0, le=23)
    minute: int = Field(0, ge=0, le=59)
    # Used when frequency == "interval"; hour/minute are the phase anchor.
    interval_hours: int = Field(4, ge=1, le=168)
    enabled: bool = False

    @field_validator("frequency")
    @classmethod
    def _frequency_allowed(cls, v: str) -> str:
        s = (v or "monthly").strip().lower()
        if s not in ("daily", "weekly", "monthly", "interval"):
            raise ValueError("frequency must be daily, weekly, monthly, or interval")
        return s


class OperatorBackupConfig(BaseModel):
    """ZIP backup under archive_root; paths validated against allowlist."""

    destination_rel: str = "logs/archive_console_backups"
    include_state_json: bool = True
    include_logs_dir: bool = True
    include_extra_rel_prefixes: list[str] = Field(default_factory=list)
    retention_max_files: int = Field(20, ge=1, le=500)
    retention_days: int = Field(0, ge=0, le=3650)  # 0 = age rule disabled


class LastOperatorBackup(BaseModel):
    started_unix: float = 0.0
    finished_unix: float = 0.0
    success: bool = False
    summary: str = ""  # relative path under archive root, or short error token


class CookieHygieneSettings(BaseModel):
    """In-app reminder only; no browser automation."""

    remind_interval_days: int = Field(0, ge=0, le=14)  # 0 = off; optional nudge only
    last_acknowledged_unix: float = 0.0
    snooze_until_unix: float = 0.0


class PreRunReminderSettings(BaseModel):
    """Banner before the next upcoming enabled schedule (global minutes-before)."""

    minutes_before: int = Field(0, ge=0, le=1440)  # 0 = off
    snooze_until_unix: float = 0.0
    acknowledged_fire_key: str = ""


class DownloadDirsSettings(BaseModel):
    """Output roots relative to archive root (empty = use built-in defaults per job)."""

    watch_later: str = ""
    channels: str = ""
    videos: str = ""
    oneoff: str = ""
    galleries: str = ""


class Features(BaseModel):
    scheduler_enabled: bool = False
    notifications_stub: bool = False
    # Manual Run tab: server refuses start until client sends cookie_confirm (see /api/run/start).
    require_cookie_confirm_manual: bool = True
    # Windows tray can listen on localhost for /notify; console POSTs during pre-run window.
    tray_notify_before_schedule: bool = False


class YtdlpBatchRunSettings(BaseModel):
    """YouTube batch (watch_later / channels / videos): cookie pause env for manual + scheduled runs."""

    pause_on_cookie_error: bool = False
    # Poll cookies.txt mtime while paused (seconds); requires pause_on_cookie_error.
    cookie_auth_poll_sec: int = Field(15, ge=5, le=3600)
    # Before spawn: extension refreshes cookies.txt from an open YouTube tab (see cookie_preflight.py).
    preflight_via_extension: bool = True
    preflight_wait_sec: int = Field(120, ge=10, le=600)


class GalleryBatchRunSettings(BaseModel):
    """Gallery saved-sources scheduled crawl: per-source wall clock (0 = unlimited)."""

    scheduled_max_run_sec: int = Field(7200, ge=0, le=86400)


class HomeBookmark(BaseModel):
    """Home dashboard bookmark, persisted server-side so it survives host/port changes.

    Stored in state.json (snake_case) but exposed over the API as ``createdAt`` to match
    the existing client shape; pass ``by_alias=True`` when dumping for the wire.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(min_length=1, max_length=64)
    url: str = Field(min_length=1, max_length=2048)
    created_at: float = Field(default=0.0, alias="createdAt")


class StorageRetentionConfig(BaseModel):
    """Manual storage cleanup from Settings (no auto-delete on server start in v1)."""

    retention_days: int = Field(90, ge=1, le=3650)
    prune_archive_runs: bool = True
    prune_operator_backup_zips: bool = True


class ConsoleState(BaseModel):
    settings_schema_version: int = 1
    host: str = "127.0.0.1"
    port: int = 8756
    # 0 = derive from port + 101 (clamped), see effective_tray_notify_port.
    tray_notify_port: int = Field(0, ge=0, le=65535)
    tray_notify_last_failure_unix: float = 0.0
    tray_notify_last_failure_message: str = ""
    archive_root: str = ""
    allowlisted_rel_prefixes: list[str] = Field(
        default_factory=lambda: ["logs", "playlists", "channels", "videos"]
    )
    features: Features = Field(default_factory=Features)
    ytdlp_batch_run: YtdlpBatchRunSettings = Field(default_factory=YtdlpBatchRunSettings)
    gallery_batch_run: GalleryBatchRunSettings = Field(default_factory=GalleryBatchRunSettings)
    schedules: list[ScheduleEntry] = Field(default_factory=list)
    operator_backup: OperatorBackupConfig = Field(default_factory=OperatorBackupConfig)
    last_operator_backup: LastOperatorBackup | None = None
    cookie_hygiene: CookieHygieneSettings = Field(default_factory=CookieHygieneSettings)
    pre_run_reminder: PreRunReminderSettings = Field(default_factory=PreRunReminderSettings)
    download_dirs: DownloadDirsSettings = Field(default_factory=DownloadDirsSettings)
    # Home dashboard bookmarks (server-persisted; previously browser localStorage only).
    home_bookmarks: list[HomeBookmark] = Field(default_factory=list)
    run_history: list[dict[str, Any]] = Field(default_factory=list)
    run_history_max: int = 50
    editor_backup_max: int = Field(10, ge=1, le=100)
    storage_retention: StorageRetentionConfig = Field(
        default_factory=StorageRetentionConfig
    )
    # Rolling one-off report under logs/oneoff_report/; rotate when older than N days.
    oneoff_report_retention_days: int = Field(90, ge=1, le=3650)
    # In-app cookie nudge on One-off page (POST ack updates this).
    oneoff_cookie_reminder_last_unix: float = 0.0
    # Empty = use "ffmpeg" on PATH (Library clip export).
    ffmpeg_exe: str = ""
    # Empty = use "gifski" on PATH (Gifsky batch converter).
    gifski_exe: str = ""
    # Empty = resolve czkawka_cli / czkawka on PATH (Czkawka tab).
    czkawka_exe: str = ""
    # Empty = use "mediainfo" on PATH (Library media details).
    mediainfo_exe: str = ""
    # Empty = use "exiftool" on PATH (Rename metadata templates).
    exiftool_exe: str = ""
    exiftool_timeout_sec: float = Field(45.0, ge=5.0, le=600.0)
    # Relative to archive root; must stay allowlisted when saved.
    duplicates_quarantine_rel: str = "logs/_duplicates_quarantine"
    duplicates_prefer_quarantine: bool = True
    # DeepL API (Rename view). Key is stored in state.json (plaintext); prefer
    # ARCHIVE_CONSOLE_DEEPL_API_KEY env to avoid persisting the key.
    deepl_api_key: str = ""
    deepl_endpoint_mode: DeepLEndpointMode = "auto"
    # Empty string = send "auto-detect" to DeepL.
    deepl_source_lang: str = ""
    deepl_target_lang: str = "EN-US"
    # Ledger for POST /api/rename/apply runs (no secrets).
    rename_runs: list[dict[str, Any]] = Field(default_factory=list)
    rename_runs_max: int = 50
    # Folder batch: skip files already renamed with the same pipeline fingerprint.
    rename_done_log: list[dict[str, Any]] = Field(default_factory=list)
    rename_done_log_max: int = Field(100_000, ge=1000, le=500_000)
    # Structured errors without a run log folder (duplicates scan, config IO, etc.).
    console_errors: list[dict[str, Any]] = Field(default_factory=list)
    console_errors_max: int = Field(150, ge=10, le=500)
    # Sidebar + Getting started visibility (recoverable in Settings).
    show_getting_started: bool = True
    # First console open: False until the operator leaves Getting started once (then saved True).
    getting_started_seen: bool = False
    # Used when opening / without ?view= and getting_started_seen is True.
    default_landing_view: str = "run"
    # Home → Weather: when both latitude and longitude are non-empty strings,
    # they override ARCHIVE_CONSOLE_WEATHER_* env. Empty = fall back to env.
    weather_latitude: str = ""
    weather_longitude: str = ""
    # When non-empty, overrides OPENWEATHER_API_KEY env for Home weather only.
    openweather_api_key: str = ""
    # Gotify push (LAN); app token stored in state.json (operator backups may include it).
    gotify_enabled: bool = False
    gotify_base_url: str = ""
    gotify_app_token: str = ""
    gotify_notify_on_start: bool = True
    gotify_notify_on_complete: bool = True
    gotify_notify_scheduled: bool = True
    gotify_notify_manual: bool = False
    gotify_priority: int = Field(5, ge=0, le=10)
    gotify_last_failure_unix: float = 0.0
    gotify_last_failure_message: str = ""

    @field_validator("default_landing_view")
    @classmethod
    def _validate_default_landing_view(cls, v: str) -> str:
        s = (v or "").strip()
        if s not in DEFAULT_LANDING_VIEWS:
            return "run"
        return s


def effective_tray_notify_port(st: ConsoleState) -> int:
    """Dedicated localhost port for tray POST /notify; 0 in state means port + 101."""
    p = int(st.tray_notify_port)
    if p > 0:
        return p
    base = int(st.port)
    cand = base + 101
    if cand > 65535:
        return 8860
    return cand


def normalize_gotify_base_url(raw: str | None) -> str:
    """Strip; require http(s) scheme; host:port only (no path/query/userinfo)."""
    from urllib.parse import urlparse

    s = (raw or "").strip().rstrip("/")
    if not s:
        raise ValueError("gotify_base_url cannot be empty when Gotify is enabled")
    if "@" in s.split("://", 1)[-1]:
        raise ValueError("gotify_base_url must not contain userinfo")
    parsed = urlparse(s)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("gotify_base_url must start with http:// or https://")
    if not parsed.netloc:
        raise ValueError("gotify_base_url must include host (and optional port)")
    if parsed.path not in ("", "/"):
        raise ValueError("gotify_base_url must not include a path")
    if parsed.query or parsed.fragment:
        raise ValueError("gotify_base_url must not include query or fragment")
    return f"{parsed.scheme}://{parsed.netloc}"


def effective_gotify_app_token(st: ConsoleState) -> str:
    return (st.gotify_app_token or "").replace("\r", "").replace("\n", "").strip()


def validate_gotify_app_token(raw: str | None) -> str:
    """Reject empty, URLs, and other values that are not Gotify app tokens."""
    s = (raw or "").replace("\r", "").replace("\n", "").strip()
    if not s:
        raise ValueError("gotify_app_token cannot be empty")
    low = s.lower()
    if low.startswith("http://") or low.startswith("https://"):
        raise ValueError(
            "gotify_app_token must be the application token from Gotify → Apps, "
            "not the server URL"
        )
    if "://" in s:
        raise ValueError(
            "gotify_app_token looks like a URL; copy the token from Gotify → Apps"
        )
    if len(s) < 8:
        raise ValueError("gotify_app_token is too short to be valid")
    return s


def gotify_is_configured(st: ConsoleState) -> bool:
    return bool(
        st.gotify_enabled
        and (st.gotify_base_url or "").strip()
        and effective_gotify_app_token(st)
    )


def default_archive_root() -> Path:
    env = os.environ.get("ARCHIVE_CONSOLE_ROOT", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return CONSOLE_DIR.parent.resolve()


def state_file_path() -> Path:
    """Path to ``state.json`` (override with ``ARCHIVE_CONSOLE_STATE_PATH`` for tests)."""
    env = os.environ.get("ARCHIVE_CONSOLE_STATE_PATH", "").strip()
    if env:
        return Path(env).expanduser()
    return DEFAULT_STATE_PATH


def _repair_archive_root(st: ConsoleState) -> tuple[ConsoleState, bool]:
    """Reset archive_root when the stored path is missing or not a directory."""
    raw = (st.archive_root or "").strip()
    if raw:
        try:
            if Path(raw).expanduser().resolve().is_dir():
                return st, False
        except OSError:
            pass
    fallback = default_archive_root()
    if fallback.is_dir():
        return st.model_copy(update={"archive_root": str(fallback)}), True
    return st, False


def validate_archive_root_setting(raw: str | None) -> str:
    s = (raw or "").strip().strip('"')
    if not s:
        raise ValueError("archive_root cannot be empty")
    if "\0" in s or ".." in s.replace("\\", "/"):
        raise ValueError("archive_root must be an absolute folder path")
    try:
        p = Path(s).expanduser().resolve()
    except OSError as e:
        raise ValueError(f"invalid archive_root: {e}") from e
    if not p.is_dir():
        raise ValueError(f"archive_root is not a directory: {p}")
    return str(p)


def _sanitize_state_dict(data: dict[str, Any]) -> None:
    """In-place fixes for legacy values before Pydantic validation."""
    if "getting_started_seen" not in data:
        # Legacy state (any non-empty payload) = already onboarded. Fresh {} = first launch.
        data["getting_started_seen"] = bool(data)
    if "default_landing_view" not in data:
        data["default_landing_view"] = "run"
    else:
        dl = data.get("default_landing_view")
        if (
            not isinstance(dl, str)
            or (dl or "").strip() not in DEFAULT_LANDING_VIEWS
        ):
            data["default_landing_view"] = "run"
    ch = data.get("cookie_hygiene")
    if isinstance(ch, dict):
        d = ch.get("remind_interval_days")
        if isinstance(d, (int, float)) and int(d) > 14:
            ch["remind_interval_days"] = 14


def load_state(path: Path | None = None) -> ConsoleState:
    p = path or state_file_path()
    if not p.is_file():
        if EXAMPLE_STATE_PATH.is_file():
            data = json.loads(EXAMPLE_STATE_PATH.read_text(encoding="utf-8"))
        else:
            data = {}
    else:
        data = json.loads(p.read_text(encoding="utf-8"))
    _sanitize_state_dict(data)
    st = ConsoleState.model_validate(data)
    if not (st.archive_root or "").strip():
        st = st.model_copy(update={"archive_root": str(default_archive_root())})
    st, repaired_root = _repair_archive_root(st)
    if repaired_root and p.is_file():
        save_state(st, p)
    ch = st.cookie_hygiene
    now = time.time()
    # Long multi-day snoozes removed from UX; clamp stale far-future snoozes once.
    if ch.snooze_until_unix > now + 48 * 3600:
        st = st.model_copy(
            update={
                "cookie_hygiene": ch.model_copy(
                    update={"snooze_until_unix": now + 3600},
                ),
            },
        )
        if p.is_file():
            save_state(st, p)
        ch = st.cookie_hygiene
    if ch.remind_interval_days > 0 and ch.last_acknowledged_unix <= 0:
        st = st.model_copy(
            update={
                "cookie_hygiene": ch.model_copy(
                    update={"last_acknowledged_unix": time.time()},
                ),
            },
        )
        if p.is_file():
            save_state(st, p)
    return st


def save_state(state: ConsoleState, path: Path | None = None) -> None:
    p = path or state_file_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        state.model_dump_json(indent=2),
        encoding="utf-8",
    )


def append_history(state: ConsoleState, entry: dict[str, Any]) -> ConsoleState:
    hist = list(state.run_history)
    hist.insert(0, entry)
    hist = hist[: state.run_history_max]
    return state.model_copy(update={"run_history": hist})


def append_rename_run(state: ConsoleState, entry: dict[str, Any]) -> ConsoleState:
    hist = list(state.rename_runs)
    hist.insert(0, entry)
    hist = hist[: state.rename_runs_max]
    return state.model_copy(update={"rename_runs": hist})


def append_rename_done_log(
    state: ConsoleState,
    *,
    folder_rel: str,
    pipeline_fp: str,
    run_id: str,
    items: list[dict[str, Any]],
) -> ConsoleState:
    """Record successful folder-batch renames so later crawls can skip them."""
    folder = (folder_rel or "").strip().replace("\\", "/").rstrip("/")
    fp = (pipeline_fp or "").strip()
    if not folder or not fp or not items:
        return state
    now = time.time()
    new_rows: list[dict[str, Any]] = []
    for it in items:
        status = str(it.get("status") or "")
        if status not in ("ok", "skip"):
            continue
        old_rel = str(it.get("rel") or "").replace("\\", "/")
        if not old_rel:
            continue
        new_rel = str(it.get("new_rel") or old_rel).replace("\\", "/")
        new_rows.append(
            {
                "folder_rel": folder,
                "pipeline_fp": fp,
                "old_rel": old_rel,
                "new_rel": new_rel,
                "status": status,
                "applied_unix": now,
                "run_id": run_id,
            }
        )
    if not new_rows:
        return state
    merged = list(new_rows) + list(state.rename_done_log)
    cap = int(state.rename_done_log_max)
    merged = merged[:cap]
    return state.model_copy(update={"rename_done_log": merged})


def append_global_console_errors(
    state: ConsoleState,
    records: list[dict[str, Any]],
) -> ConsoleState:
    if not records:
        return state
    merged = list(records) + list(state.console_errors)
    cap = int(state.console_errors_max)
    merged = merged[:cap]
    return state.model_copy(update={"console_errors": merged})


RenameLedgerFailureKind = Literal["rename_preview_failed", "rename_apply_failed"]


def _safe_int_rel_count(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def append_rename_failure_event(
    state: ConsoleState,
    *,
    ledger_kind: RenameLedgerFailureKind,
    operation: str,
    error_code: str,
    message: str,
    rel_count: int,
    diagnostic_ref: str,
    preview_id: str | None = None,
    error_records: list[dict[str, Any]] | None = None,
) -> ConsoleState:
    """Append a sanitized rename failure row (no secrets, no stack traces)."""
    now = time.time()
    entry: dict[str, Any] = {
        "run_id": str(uuid.uuid4()),
        "ledger_kind": ledger_kind,
        "status": "fail",
        "operation": (operation or "rename")[:200],
        "started_unix": now,
        "ended_unix": now,
        "ok": 0,
        "skip": 0,
        "fail": 0,
        "items": [],
        "error_code": (error_code or "unknown")[:120],
        "message": (message or "")[:800],
        "diagnostic_ref": (diagnostic_ref or "")[:32],
        "rel_count": max(0, _safe_int_rel_count(rel_count)),
    }
    if preview_id:
        entry["preview_id"] = preview_id[:128]
    if error_records:
        entry["errors"] = list(error_records)[:50]
    hist = list(state.rename_runs)
    hist.insert(0, entry)
    hist = hist[: state.rename_runs_max]
    return state.model_copy(update={"rename_runs": hist})
