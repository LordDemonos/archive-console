"""Built-in preset overlays + metadata (no cookie secrets)."""

from __future__ import annotations

from typing import Any

FMT_MERGE = (
    "bestvideo*+bestaudio/bestvideo+bestaudio/bestvideo*/best/worst"
)
FMT_BEST = "bv*+ba/bestvideo+bestaudio/bestvideo*+bestaudio/best/worst"
FMT_LOW = "best[height<=720]/bestvideo*[height<=720]+bestaudio/best/worst"
FMT_AUDIO = "bestaudio/best"

ARCHIVE_BASELINE: dict[str, Any] = {
    "format": FMT_MERGE,
    "merge_output_format": "mkv",
    "sleep_requests": 8.0,
    "sleep_interval": 2.0,
    "retries": 10,
    "fragment_retries": 10,
    "file_access_retries": 10,
    "force_ipv4": True,
    "ignore_errors": True,
    "no_check_formats": True,
    "external_downloader": "aria2c",
    "match_filter": "!is_live",
    "verbose": False,
    "js_runtimes": "node",
    "extractor_args": "youtube:player_client=tv,web_safari,mweb",
}

PRESET_OVERLAYS: dict[str, dict[str, Any]] = {
    "balanced": {},
    "best_quality": {
        "format": FMT_BEST,
        "sleep_requests": 10.0,
        "sleep_interval": 3.0,
        "verbose": False,
    },
    "fast_low_bw": {
        "format": FMT_LOW,
        "sleep_requests": 3.0,
        "sleep_interval": 1.0,
        "external_downloader": "ffmpeg",
    },
    "audio_only": {
        "format": FMT_AUDIO,
        "merge_output_format": "mkv",
        "extract_audio": False,
    },
    "merge_friendly": {
        "format": FMT_MERGE,
        "merge_output_format": "mkv",
        "no_check_formats": True,
    },
    "debug_verbose": {
        "verbose": True,
        "ignore_errors": True,
        "no_warnings": False,
    },
}

PRESET_META: list[dict[str, str]] = [
    {
        "id": "balanced",
        "label": "Balanced",
        "description": "Matches typical archive defaults (merge-first, mkv, sleeps, aria2c).",
    },
    {
        "id": "best_quality",
        "label": "Best quality",
        "description": "Stronger format chain, slightly longer sleeps.",
    },
    {
        "id": "fast_low_bw",
        "label": "Fast / low bandwidth",
        "description": "720p-cap, shorter sleeps, ffmpeg external downloader.",
    },
    {
        "id": "audio_only",
        "label": "Audio only",
        "description": "bestaudio chain (no separate extract-audio step).",
    },
    {
        "id": "merge_friendly",
        "label": "Merge-friendly",
        "description": "Emphasizes DASH merge + no format probes.",
    },
    {
        "id": "debug_verbose",
        "label": "Debug verbose",
        "description": "Verbose yt-dlp logging for troubleshooting.",
    },
    {
        "id": "user_preferences",
        "label": "User preferences",
        "description": "Snapshot captured from disk (use Recapture to refresh).",
    },
]


def merged_preset_data(preset_id: str) -> dict[str, Any]:
    """Baseline + overlay for built-ins; user_preferences must be supplied by caller."""
    if preset_id == "user_preferences":
        raise ValueError("use snapshot")
    base = dict(ARCHIVE_BASELINE)
    ov = PRESET_OVERLAYS.get(preset_id, {})
    base.update(ov)
    return base


def apply_builtin_preset(current: dict[str, Any], preset_id: str) -> dict[str, Any]:
    if preset_id == "user_preferences":
        raise ValueError("user_preferences requires snapshot")
    merged = merged_preset_data(preset_id)
    out = dict(current)
    for k, v in merged.items():
        if k in ("extra_kv", "preserved_tail"):
            continue
        out[k] = v
    return out
