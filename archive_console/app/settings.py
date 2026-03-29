"""Load and save archive_console/state.json (no DB)."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


CONSOLE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_STATE_PATH = CONSOLE_DIR / "state.json"
EXAMPLE_STATE_PATH = CONSOLE_DIR / "state.example.json"


class ScheduleEntry(BaseModel):
    """Monthly schedule; day-of-month clamped in short months (see UI help)."""

    id: str = ""
    job: str = "watch_later"
    day_of_month: int = Field(1, ge=1, le=31)
    hour: int = Field(3, ge=0, le=23)
    minute: int = Field(0, ge=0, le=59)
    enabled: bool = False


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

    remind_interval_days: int = Field(0, ge=0, le=365)  # 0 = off
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


class Features(BaseModel):
    scheduler_enabled: bool = False
    notifications_stub: bool = False


class StorageRetentionConfig(BaseModel):
    """Manual storage cleanup from Settings (no auto-delete on server start in v1)."""

    retention_days: int = Field(90, ge=1, le=3650)
    prune_archive_runs: bool = True
    prune_operator_backup_zips: bool = True


class ConsoleState(BaseModel):
    settings_schema_version: int = 1
    host: str = "127.0.0.1"
    port: int = 8756
    archive_root: str = ""
    allowlisted_rel_prefixes: list[str] = Field(
        default_factory=lambda: ["logs", "playlists", "channels", "videos"]
    )
    features: Features = Field(default_factory=Features)
    schedules: list[ScheduleEntry] = Field(default_factory=list)
    operator_backup: OperatorBackupConfig = Field(default_factory=OperatorBackupConfig)
    last_operator_backup: LastOperatorBackup | None = None
    cookie_hygiene: CookieHygieneSettings = Field(default_factory=CookieHygieneSettings)
    pre_run_reminder: PreRunReminderSettings = Field(default_factory=PreRunReminderSettings)
    download_dirs: DownloadDirsSettings = Field(default_factory=DownloadDirsSettings)
    run_history: list[dict[str, Any]] = Field(default_factory=list)
    run_history_max: int = 50
    editor_backup_max: int = Field(10, ge=1, le=100)
    storage_retention: StorageRetentionConfig = Field(
        default_factory=StorageRetentionConfig
    )


def default_archive_root() -> Path:
    env = os.environ.get("ARCHIVE_CONSOLE_ROOT", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return CONSOLE_DIR.parent.resolve()


def load_state(path: Path | None = None) -> ConsoleState:
    p = path or DEFAULT_STATE_PATH
    if not p.is_file():
        if EXAMPLE_STATE_PATH.is_file():
            data = json.loads(EXAMPLE_STATE_PATH.read_text(encoding="utf-8"))
        else:
            data = {}
        st = ConsoleState.model_validate(data)
    else:
        st = ConsoleState.model_validate_json(p.read_text(encoding="utf-8"))
    if not (st.archive_root or "").strip():
        st = st.model_copy(update={"archive_root": str(default_archive_root())})
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
    p = path or DEFAULT_STATE_PATH
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
