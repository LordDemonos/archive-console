"""Persistent UI state for yt-dlp-oneoff.conf (single-download overlay presets)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel

from .settings import CONSOLE_DIR

UI_STATE_PATH = CONSOLE_DIR / "yt_dlp_oneoff_ui_state.json"
UI_STATE_EXAMPLE = CONSOLE_DIR / "yt_dlp_oneoff_ui_state.example.json"


class YtdlpOneoffUiState(BaseModel):
    active_preset_id: str = "balanced"
    user_preferences_snapshot: dict[str, Any] | None = None


def load_oneoff_ui_state() -> YtdlpOneoffUiState:
    if not UI_STATE_PATH.is_file():
        if UI_STATE_EXAMPLE.is_file():
            return YtdlpOneoffUiState.model_validate_json(
                UI_STATE_EXAMPLE.read_text(encoding="utf-8")
            )
        return YtdlpOneoffUiState()
    return YtdlpOneoffUiState.model_validate_json(
        UI_STATE_PATH.read_text(encoding="utf-8")
    )


def save_oneoff_ui_state(state: YtdlpOneoffUiState) -> None:
    UI_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    UI_STATE_PATH.write_text(
        state.model_dump_json(indent=2),
        encoding="utf-8",
    )
