"""gifsky.conf JSON editor: presets and validation for gallery video → GIF batch."""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

GIFSKY_CONF_NAME = "gifsky.conf"

DEFAULT_STATE: dict[str, Any] = {
    "quality": 100,
    "fps": 30,
    "max_source_mb": 20,
    "extensions": ["mp4", "webm", "m4v"],
    "skip_if_gif_exists": True,
    "verify_min_bytes": 512,
    "ffmpeg_scale_max_width": 0,
}

PRESET_PATCHES: dict[str, dict[str, Any]] = {
    "hq_reddit": {
        "quality": 100,
        "fps": 30,
        "max_source_mb": 20,
        "extensions": ["mp4", "webm", "m4v"],
        "skip_if_gif_exists": True,
        "verify_min_bytes": 512,
        "ffmpeg_scale_max_width": 0,
    },
    "balanced": {
        "quality": 90,
        "fps": 24,
        "max_source_mb": 40,
        "extensions": ["mp4", "webm", "m4v"],
        "skip_if_gif_exists": True,
        "verify_min_bytes": 512,
        "ffmpeg_scale_max_width": 720,
    },
    "compact_xnview": {
        "quality": 85,
        "fps": 20,
        "max_source_mb": 15,
        "extensions": ["mp4", "m4v"],
        "skip_if_gif_exists": True,
        "verify_min_bytes": 1024,
        "ffmpeg_scale_max_width": 480,
    },
}

PRESET_META: list[dict[str, str]] = [
    {
        "id": "hq_reddit",
        "label": "HQ Reddit (Mp4ToGif)",
        "description": "Matches ConvertMp4ToHQGif.bat — gifski quality 100, 30 fps, ≤20 MB sources, native resolution.",
    },
    {
        "id": "balanced",
        "label": "Balanced",
        "description": "720px max width, 24 fps, quality 90 — smaller files, still sharp for short clips.",
    },
    {
        "id": "compact_xnview",
        "label": "Compact (XnView queue)",
        "description": "480px, 20 fps, quality 85 — best for XnView folder queues and smaller files.",
    },
    {
        "id": "user_preferences",
        "label": "User preferences",
        "description": "Snapshot from disk — use Capture from disk first.",
    },
]

TIER_A_GROUPS: list[dict[str, Any]] = [
    {
        "label": "Gifski output",
        "fields": [
            {
                "key": "quality",
                "label": "gifski quality (1–100)",
                "widget": "number",
                "placeholder": "100",
                "help": "Higher = sharper GIF, larger files. Mp4ToGif default is 100.",
            },
            {
                "key": "fps",
                "label": "gifski fps",
                "widget": "number",
                "placeholder": "30",
                "help": "Output frame rate passed to gifski.",
            },
        ],
    },
    {
        "label": "Source filter",
        "fields": [
            {
                "key": "max_source_mb",
                "label": "Max source size (MB)",
                "widget": "number",
                "placeholder": "20",
                "help": "Skip videos larger than this (0 = no limit). Short Reddit clips usually fit under 20.",
            },
            {
                "key": "extensions",
                "label": "extensions (comma-separated)",
                "widget": "text",
                "placeholder": "mp4, webm, m4v",
                "help": "Video extensions under the galleries tree. Reddit / RedGifs often use .m4v (not .mp4).",
            },
            {
                "key": "skip_if_gif_exists",
                "label": "Skip when GIF already exists",
                "widget": "toggle",
                "help": "Do not re-convert if same-basename .gif is beside the video.",
            },
        ],
    },
    {
        "label": "ffmpeg pre-process",
        "fields": [
            {
                "key": "ffmpeg_scale_max_width",
                "label": "Scale max width (px, 0 = native)",
                "widget": "number",
                "placeholder": "0",
                "help": "Downscale before gifski to save space; 0 keeps source dimensions.",
            },
        ],
    },
    {
        "label": "Verification",
        "fields": [
            {
                "key": "verify_min_bytes",
                "label": "Min GIF size (bytes)",
                "widget": "number",
                "placeholder": "512",
                "help": "Treat GIFs smaller than this as failed conversions.",
            },
        ],
    },
]


def deep_merge(base: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for k, v in over.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def apply_builtin_preset(state: dict[str, Any], preset_id: str) -> dict[str, Any]:
    if preset_id == "user_preferences":
        raise ValueError("user_preferences requires a captured snapshot")
    patch = PRESET_PATCHES.get(preset_id)
    if patch is None:
        raise ValueError(f"unknown preset: {preset_id}")
    return deep_merge(deep_merge(DEFAULT_STATE, state), patch)


def _normalize_extensions(raw: Any) -> list[str]:
    if isinstance(raw, list):
        parts = [str(x).strip().lower().lstrip(".") for x in raw if str(x).strip()]
    elif isinstance(raw, str):
        parts = [p.strip().lower().lstrip(".") for p in raw.split(",") if p.strip()]
    else:
        parts = list(DEFAULT_STATE["extensions"])
    out = [p for p in parts if re.fullmatch(r"[a-z0-9]{1,8}", p)]
    return out or list(DEFAULT_STATE["extensions"])


def model_from_client_dict(raw: dict[str, Any]) -> dict[str, Any]:
    out = deep_merge(DEFAULT_STATE, raw or {})
    q = out.get("quality")
    if not isinstance(q, (int, float)) or int(q) < 1 or int(q) > 100:
        raise ValueError("quality must be 1–100")
    out["quality"] = int(q)
    fps = out.get("fps")
    if not isinstance(fps, (int, float)) or float(fps) <= 0 or float(fps) > 120:
        raise ValueError("fps must be > 0 and ≤ 120")
    out["fps"] = float(fps)
    mb = out.get("max_source_mb")
    if not isinstance(mb, (int, float)) or float(mb) < 0 or float(mb) > 10_000:
        raise ValueError("max_source_mb must be 0–10000")
    out["max_source_mb"] = float(mb)
    out["extensions"] = _normalize_extensions(out.get("extensions"))
    out["skip_if_gif_exists"] = bool(out.get("skip_if_gif_exists", True))
    vb = out.get("verify_min_bytes")
    if not isinstance(vb, (int, float)) or int(vb) < 0:
        raise ValueError("verify_min_bytes must be >= 0")
    out["verify_min_bytes"] = int(vb)
    sw = out.get("ffmpeg_scale_max_width")
    if not isinstance(sw, (int, float)) or int(sw) < 0 or int(sw) > 8192:
        raise ValueError("ffmpeg_scale_max_width must be 0–8192")
    out["ffmpeg_scale_max_width"] = int(sw)
    return out


def parse_gifsky_conf_text(text: str) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    t = (text or "").strip()
    if not t:
        return deep_merge({}, DEFAULT_STATE), warnings
    try:
        raw = json.loads(t)
    except json.JSONDecodeError as e:
        raise ValueError(f"invalid JSON: {e}") from e
    if not isinstance(raw, dict):
        raise ValueError("gifsky.conf must be a JSON object")
    try:
        return model_from_client_dict(raw), warnings
    except ValueError as e:
        warnings.append(str(e))
        return deep_merge(DEFAULT_STATE, raw if isinstance(raw, dict) else {}), warnings


def serialize_gifsky_conf(state: dict[str, Any]) -> str:
    normalized = model_from_client_dict(state)
    return json.dumps(normalized, indent=2, ensure_ascii=False) + "\n"


def gifsky_conf_path(archive_root: Path) -> Path:
    return archive_root.expanduser().resolve() / GIFSKY_CONF_NAME


def preview_summary(state: dict[str, Any]) -> str:
    s = model_from_client_dict(state)
    ext = ", ".join(s["extensions"])
    scale = s["ffmpeg_scale_max_width"]
    scale_note = f", scale≤{scale}px" if scale else ", native resolution"
    mb = s["max_source_mb"]
    mb_note = f"≤{int(mb)} MB" if mb else "any size"
    return (
        f"gifski q={s['quality']} fps={s['fps']} | sources: .{ext.replace(', ', '/.')} "
        f"({mb_note}){scale_note} | skip existing gif: {s['skip_if_gif_exists']}"
    )
