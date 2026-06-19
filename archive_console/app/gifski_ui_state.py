"""Persistent UI state for gifsky.conf setup (preset selection + user snapshot)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from .settings import CONSOLE_DIR

GIFSKY_UI_PATH = CONSOLE_DIR / "gifsky_ui_state.json"
GIFSKY_UI_EXAMPLE = CONSOLE_DIR / "gifsky_ui_state.example.json"


class GifskyUiState(BaseModel):
    active_preset_id: str = "hq_reddit"
    user_preferences_snapshot: dict[str, Any] | None = None


def load_gifsky_ui_state() -> GifskyUiState:
    if not GIFSKY_UI_PATH.is_file():
        if GIFSKY_UI_EXAMPLE.is_file():
            return GifskyUiState.model_validate_json(
                GIFSKY_UI_EXAMPLE.read_text(encoding="utf-8")
            )
        return GifskyUiState()
    return GifskyUiState.model_validate_json(
        GIFSKY_UI_PATH.read_text(encoding="utf-8")
    )


def save_gifsky_ui_state(state: GifskyUiState) -> None:
    GIFSKY_UI_PATH.parent.mkdir(parents=True, exist_ok=True)
    GIFSKY_UI_PATH.write_text(
        state.model_dump_json(indent=2),
        encoding="utf-8",
    )
