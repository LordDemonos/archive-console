"""Persistent UI state for yt-dlp setup (presets selection + user snapshot)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel

from .settings import CONSOLE_DIR

UI_STATE_PATH = CONSOLE_DIR / "yt_dlp_ui_state.json"
UI_STATE_EXAMPLE = CONSOLE_DIR / "yt_dlp_ui_state.example.json"


class YtdlpUiState(BaseModel):
    active_preset_id: str = "balanced"
    user_preferences_snapshot: dict[str, Any] | None = None
    custom_preset_note: str = ""


def load_ui_state() -> YtdlpUiState:
    if not UI_STATE_PATH.is_file():
        if UI_STATE_EXAMPLE.is_file():
            return YtdlpUiState.model_validate_json(
                UI_STATE_EXAMPLE.read_text(encoding="utf-8")
            )
        return YtdlpUiState()
    return YtdlpUiState.model_validate_json(
        UI_STATE_PATH.read_text(encoding="utf-8")
    )


def save_ui_state(state: YtdlpUiState) -> None:
    UI_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    UI_STATE_PATH.write_text(
        state.model_dump_json(indent=2),
        encoding="utf-8",
    )
