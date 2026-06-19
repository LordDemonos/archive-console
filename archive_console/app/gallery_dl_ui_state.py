"""Persistent UI state for gallery-dl setup (preset selection + user snapshot)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from .gallery_dl_setup import VALID_PRESET_IDS
from .settings import CONSOLE_DIR

GALLERY_DL_UI_PATH = CONSOLE_DIR / "gallery_dl_ui_state.json"
GALLERY_DL_UI_EXAMPLE = CONSOLE_DIR / "gallery_dl_ui_state.example.json"


class GalleryDlUiState(BaseModel):
    active_preset_id: str = "balanced"
    user_preferences_snapshot: dict[str, Any] | None = None


def load_gallery_dl_ui_state() -> GalleryDlUiState:
    if not GALLERY_DL_UI_PATH.is_file():
        if GALLERY_DL_UI_EXAMPLE.is_file():
            ui = GalleryDlUiState.model_validate_json(
                GALLERY_DL_UI_EXAMPLE.read_text(encoding="utf-8")
            )
        else:
            ui = GalleryDlUiState()
    else:
        ui = GalleryDlUiState.model_validate_json(
            GALLERY_DL_UI_PATH.read_text(encoding="utf-8")
        )
    if ui.active_preset_id not in VALID_PRESET_IDS:
        ui.active_preset_id = "balanced"
    return ui


def save_gallery_dl_ui_state(state: GalleryDlUiState) -> None:
    GALLERY_DL_UI_PATH.parent.mkdir(parents=True, exist_ok=True)
    GALLERY_DL_UI_PATH.write_text(
        state.model_dump_json(indent=2),
        encoding="utf-8",
    )
