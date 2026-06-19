"""gallery-dl.conf JSON editor: presets, schema metadata, CLI preview, validation."""

from __future__ import annotations

import json
import copy
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .gallery_cli import resolve_gallery_dl_exe

DOC_CONF = "https://github.com/mikf/gallery-dl/blob/master/docs/configuration.rst"
DOC_OPTS = "https://github.com/mikf/gallery-dl/blob/master/docs/options.md"


def deep_merge(base: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
    """Recursive merge; values in ``over`` replace / extend ``base``."""
    out = copy.deepcopy(base)
    for k, v in over.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


PRESET_PATCHES: dict[str, dict[str, Any]] = {
    "balanced": {
        "extractor": {
            "timeout": 45.0,
            "retries": 5,
            "sleep-request": "1.0-2.5",
            "sleep-429": 120.0,
        },
        "downloader": {
            "retries": 5,
            "timeout": 60.0,
            "http": {"sleep-429": 120.0},
        },
    },
    "conservative": {
        "extractor": {
            "timeout": 60.0,
            "retries": 6,
            "sleep-request": "2.0-4.0",
            "sleep-429": 120.0,
            "sleep-extractor": 1.0,
        },
        "downloader": {
            "retries": 6,
            "timeout": 90.0,
            "http": {"sleep-429": 120.0},
        },
    },
    "fast_local": {
        "extractor": {
            "timeout": 30.0,
            "retries": 3,
            "sleep-request": "0-0.5",
            "sleep-429": 60.0,
        },
        "downloader": {
            "retries": 3,
            "timeout": 45.0,
            "http": {"sleep-429": 60.0},
        },
    },
    "slow_safe": {
        "extractor": {
            "timeout": 90.0,
            "retries": 8,
            "sleep-request": "3.0-6.0",
            "sleep-429": 300.0,
            "sleep-extractor": 2.0,
        },
        "downloader": {
            "retries": 8,
            "timeout": 120.0,
            "http": {"sleep-429": 300.0},
        },
    },
}

PRESET_BAR_NOTE = (
    "Request pacing only (sleeps, timeouts, retries). Does not change Reddit settings, "
    "cookies, folder names (merged at Galleries run), verbose logging, or Reddit video "
    "filters — set those in the sections below. Save gallery-dl.conf after applying."
)

PRESET_META: list[dict[str, str]] = [
    {
        "id": "balanced",
        "label": "Balanced",
        "description": "Moderate sleeps and 429 backoff — default for mixed gallery sites.",
    },
    {
        "id": "conservative",
        "label": "Conservative / rate-limited",
        "description": "Slower requests — use for Reddit-heavy runs or when you see 429 blocks.",
    },
    {
        "id": "fast_local",
        "label": "Fast (local / trusted)",
        "description": "Minimal delay — only when you trust the network and accept more risk.",
    },
    {
        "id": "user_preferences",
        "label": "User preferences",
        "description": "Restore a snapshot captured with “Capture current as User preferences”.",
    },
]

BUILTIN_PRESET_IDS: frozenset[str] = frozenset(PRESET_PATCHES.keys())

VALID_PRESET_IDS: frozenset[str] = BUILTIN_PRESET_IDS | frozenset({"user_preferences"})

TIER_A_GROUPS: list[dict[str, Any]] = [
    {
        "label": "Output & paths",
        "doc": "Layout under each gallery-dl run destination (`-o` from the Console). See extractor.directory / base-directory.",
        "doc_url": DOC_CONF + "#extractor-directory",
        "fields": [
            {
                "key": "extractor.base-directory",
                "label": "base-directory",
                "widget": "text",
                "placeholder": ".",
                "help": "Relative to each job’s output root; `.` keeps `-o …/gallery_<stamp>/` as the root.",
                "doc_url": DOC_CONF + "#extractor-base-directory",
            },
            {
                "key": "extractor.directory.0",
                "label": "directory[0] (first path segment)",
                "widget": "text",
                "placeholder": "{category}",
                "help": "Format string for the first folder under base-directory. Reddit, Instagram, and Twitter use per-extractor folders at run time (reddit_sub_*, instagram_{username}, twitter_{user[name]}); this applies to other sites.",
                "doc_url": DOC_CONF + "#extractor-directory",
            },
            {
                "key": "extractor.directory.1",
                "label": "directory[1] (second segment, optional)",
                "widget": "text",
                "placeholder": "{subcategory}",
                "help": "Leave empty to only use one segment (or use Directory tidy preset).",
                "doc_url": DOC_CONF + "#extractor-directory",
            },
            {
                "key": "extractor.path-restrict",
                "label": "path-restrict",
                "widget": "select",
                "choices": ["windows", "unix", "ascii"],
                "help": "Sanitize path characters for the target OS.",
                "doc_url": DOC_CONF + "#extractor-path-restrict",
            },
        ],
    },
    {
        "label": "Network & HTTP",
        "doc": "Extractor-level request behavior; align with downloader timeouts for large files.",
        "doc_url": DOC_CONF + "#extractor-timeout",
        "fields": [
            {
                "key": "extractor.timeout",
                "label": "extractor timeout (seconds)",
                "widget": "number",
                "placeholder": "45",
                "help": "HTTP connect/read timeout for extractor requests.",
                "doc_url": DOC_CONF + "#extractor-timeout",
            },
            {
                "key": "extractor.retries",
                "label": "extractor retries",
                "widget": "number",
                "placeholder": "5",
                "help": "Retries for failed extractor HTTP requests.",
                "doc_url": DOC_CONF + "#extractor-retries",
            },
            {
                "key": "extractor.sleep-request",
                "label": "sleep-request",
                "widget": "text",
                "placeholder": "1.0-2.0",
                "help": "Pause between requests (number or min-max range string).\n\nPacing Guide:\nBalanced: 1.0-2.5s | Conservative: 2.0-4.0s | Slow Safe: 3.0-6.0s\n\nHigher values significantly reduce the risk of hitting platform rate limits (HTTP 429).",
                "doc_url": DOC_CONF + "#extractor-sleep-request",
            },
            {
                "key": "extractor.sleep-extractor",
                "label": "sleep-extractor (seconds)",
                "widget": "number",
                "placeholder": "0",
                "help": "Pause before starting a new URL / extractor.",
                "doc_url": DOC_CONF + "#extractor-sleep-extractor",
            },
            {
                "key": "downloader.http.sleep-429",
                "label": "downloader.http sleep-429",
                "widget": "number",
                "placeholder": "90",
                "help": "429 backoff during file downloads.",
                "doc_url": DOC_CONF + "#downloader-http-sleep-429",
            },
        ],
    },
    {
        "label": "Downloader",
        "doc": "File download module defaults (parallel to extractor HTTP).",
        "doc_url": DOC_CONF + "#downloader-options",
        "fields": [
            {
                "key": "downloader.retries",
                "label": "downloader retries",
                "widget": "number",
                "placeholder": "5",
                "help": "Retries when a media download fails.",
                "doc_url": DOC_CONF + "#downloader-retries",
            },
            {
                "key": "downloader.timeout",
                "label": "downloader timeout (seconds)",
                "widget": "number",
                "placeholder": "60",
                "help": "Often inherits from extractor if unset upstream.",
                "doc_url": DOC_CONF + "#downloader-timeout",
            },
            {
                "key": "downloader.part",
                "label": "downloader part (resume .part files)",
                "widget": "toggle",
                "help": "Use partial files and resume (recommended).",
                "doc_url": DOC_CONF + "#downloader-part",
            },
        ],
    },
    {
        "label": "Output & verbosity",
        "doc": "Console logging; does not replace your Archive Console UI.",
        "doc_url": DOC_CONF + "#output-options",
        "fields": [
            {
                "key": "output.mode",
                "label": "output.mode",
                "widget": "select",
                "choices": ["", "terminal", "json"],
                "help": "Blank = default. terminal is typical; json for machine-readable logs.",
                "doc_url": DOC_CONF + "#output-mode",
            },
            {
                "key": "output.shorten",
                "label": "output.shorten paths in log",
                "widget": "toggle",
                "help": "Shorten logged paths (off for full paths when debugging).",
                "doc_url": DOC_CONF + "#output-shorten",
            },
            {
                "key": "verbose",
                "label": "verbose (top-level)",
                "widget": "toggle",
                "help": "More gallery-dl log detail — can be noisy.",
                "doc_url": DOC_OPTS,
            },
        ],
    },
    {
        "label": "Reddit",
        "doc": (
            "Public subreddits and user profiles use gallery-dl's built-in access token "
            "by default — leave OAuth fields empty unless you need private or NSFW feeds. "
            "Optional cookies/reddit.txt on disk is auto-wired when present."
        ),
        "doc_url": "https://github.com/mikf/gallery-dl/issues/8641",
        "fields": [],
    },
    {
        "label": "Reddit OAuth (advanced — optional)",
        "collapsible": True,
        "collapsed": True,
        "doc": (
            "Only if public access stops working or you need logged-in (NSFW/private) "
            "content. Register an installed app at reddit.com/prefs/apps, then run "
            "gallery-dl oauth:reddit -c <archive_root>/gallery-dl.conf. Mismatched "
            "client-id and refresh-token cause 401 errors — when in doubt, leave these "
            "blank and use the public token. Edit raw JSON below for other keys."
        ),
        "doc_url": "https://github.com/mikf/gallery-dl/issues/8641",
        "fields": [
            {
                "key": "extractor.reddit.api",
                "label": "reddit api mode",
                "widget": "select",
                "choices": ["", "oauth", "rest"],
                "help": "Leave blank or oauth for API mode. rest = legacy .json scraping (often blocked).",
                "doc_url": DOC_CONF + "#extractor-reddit-client-id-user-agent",
            },
            {
                "key": "extractor.reddit.client-id",
                "label": "OAuth client-id",
                "widget": "text",
                "placeholder": "leave blank for gallery-dl default public app",
                "help": "Only with your own Reddit app + refresh-token. Blank = built-in public client.",
                "doc_url": DOC_CONF + "#extractor-reddit-client-id-user-agent",
            },
            {
                "key": "extractor.reddit.user-agent",
                "label": "OAuth user-agent string",
                "widget": "text",
                "placeholder": "Python:ArchiveConsole:v1.0 (by /u/YourRedditName)",
                "help": "Only when using a custom client-id — include your Reddit username after /u/.",
                "doc_url": DOC_CONF + "#extractor-reddit-client-id-user-agent",
            },
            {
                "key": "extractor.reddit.headers.user-agent",
                "label": "Browser User-Agent (headers)",
                "widget": "text",
                "placeholder": "Mozilla/5.0 … (copy from browser DevTools)",
                "help": "Optional; copy from a logged-in reddit.com request in DevTools → Network.",
                "doc_url": "https://github.com/mikf/gallery-dl/issues/8641",
            },
            {
                "key": "extractor.reddit.refresh-token",
                "label": "OAuth refresh-token",
                "widget": "text",
                "placeholder": "leave blank for public access token",
                "help": "Private/NSFW only. From gallery-dl oauth:reddit with the same client-id and -c path.",
                "doc_url": DOC_CONF + "#extractor-reddit-refresh-token",
            },
        ],
    },
    {
        "label": "Reddit media filters",
        "doc": "Archive Console merges RipMe-style folder layout when running Galleries; these filters apply on top. Only Reddit-hosted v.redd.it clips are controlled here — redgifs/imgur embeds and Galleries → Video fallback are separate.",
        "doc_url": DOC_CONF + "#extractor-reddit-videos",
        "fields": [
            {
                "key": "extractor.reddit.videos",
                "label": "Download Reddit hosted video",
                "widget": "toggle",
                "help": "Off = gallery-dl skips native Reddit video (v.redd.it). On = dash manifest download. Does not block redgifs/imgur or Galleries → Video fallback (yt-dlp). Save gallery-dl.conf after changing.",
                "doc_url": DOC_CONF + "#extractor-reddit-videos",
            },
            {
                "key": "extractor.reddit.image-filter",
                "label": "reddit image-filter",
                "widget": "text",
                "placeholder": "extension in ('jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp')",
                "help": "Python expression; Reddit files download only when true. Leave blank to use the Archive default (still images + GIF).",
                "doc_url": DOC_CONF + "#extractor-image-filter",
            },
        ],
    },
]


def _ensure_structure(state: dict[str, Any]) -> None:
    if "extractor" not in state or not isinstance(state["extractor"], dict):
        state["extractor"] = {}
    ex = state["extractor"]
    if "directory" not in ex or not isinstance(ex["directory"], list):
        ex["directory"] = ["{category}", "{subcategory}"]
    while len(ex["directory"]) < 2:
        ex["directory"].append("")
    if "downloader" not in state or not isinstance(state["downloader"], dict):
        state["downloader"] = {}
    dl = state["downloader"]
    if "http" not in dl or not isinstance(dl["http"], dict):
        dl["http"] = {}


def parse_gallery_dl_conf_text(text: str) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    t = (text or "").strip()
    if not t:
        state = {}
        _ensure_structure(state)
        warnings.append(
            "No file on disk yet — empty object with minimal path defaults; pick a preset or Save.",
        )
        return state, warnings
    try:
        parsed = json.loads(t)
    except json.JSONDecodeError as e:
        warnings.append(f"JSON parse error: {e}")
        state = {}
        _ensure_structure(state)
        return state, warnings
    if not isinstance(parsed, dict):
        warnings.append("Root JSON value must be an object; recovered empty shell.")
        state = {}
        _ensure_structure(state)
        return state, warnings
    state = copy.deepcopy(parsed)
    _ensure_structure(state)
    return state, warnings


def _strip_ui_noise(state: dict[str, Any]) -> dict[str, Any]:
    """Drop keys that should never be written (none today)."""
    return {k: v for k, v in state.items() if not str(k).startswith("_console")}


def serialize_gallery_dl_conf(state: dict[str, Any]) -> str:
    clean = _strip_ui_noise(copy.deepcopy(state))
    _ensure_structure(clean)
    return json.dumps(clean, indent=2, ensure_ascii=False) + "\n"


def apply_builtin_preset(
    current: dict[str, Any],
    preset_id: str,
) -> dict[str, Any]:
    base = copy.deepcopy(current)
    if preset_id in PRESET_PATCHES:
        return deep_merge(base, PRESET_PATCHES[preset_id])
    return base


def apply_user_snapshot(
    current: dict[str, Any],
    snapshot: dict[str, Any] | None,
) -> dict[str, Any]:
    if not snapshot:
        return copy.deepcopy(current)
    out = copy.deepcopy(snapshot)
    _ensure_structure(out)
    return out


PREVIEW_URL_SAMPLE = "https://www.reddit.com/r/pics/"


def preview_cli(
    *,
    archive_root: Path,
    state: dict[str, Any],
    gallery_dl_exe: str | None = None,
) -> str:
    exe = resolve_gallery_dl_exe(gallery_dl_exe)
    conf = archive_root / "gallery-dl.conf"
    cookies = archive_root / "cookies.txt"
    parts = [exe]
    parts.append("--config-ignore")
    if conf.parent == archive_root.resolve():
        parts.extend(["-c", f"<archive_root>/{conf.name}"])
    else:
        parts.extend(["-c", str(conf)])
    if cookies.is_file():
        parts.extend(["--cookies", f"<archive_root>/{cookies.name}"])
    parts.extend(["-s", "-j", PREVIEW_URL_SAMPLE])
    return (
        "# Representative preview command (same flags as Galleries preview / run; "
        "URL is a safe public example)\n"
        + " ".join(parts)
    )


def smoke_gallery_dl_conf(
    *,
    json_text: str,
    gallery_dl_exe: str | None = None,
    timeout_sec: float = 20.0,
) -> list[str]:
    """Validate JSON, then run gallery-dl on a **temp** copy (same bytes as Save would write).

    Uses a tempfile so we never point gallery-dl at a half-written disk path; load/save still
    use ``<archive_root>/gallery-dl.conf`` (same file Galleries passes as ``-c`` when present).
    """
    hints: list[str] = []
    exe = resolve_gallery_dl_exe(gallery_dl_exe)
    try:
        json.loads(json_text)
    except json.JSONDecodeError as e:
        return [f"Invalid JSON: {e}"]
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".json",
            delete=False,
            encoding="utf-8",
            newline="\n",
        ) as tmp:
            tmp.write(json_text)
            tmp_path = tmp.name
        try:
            proc = subprocess.run(
                [exe, "--config-ignore", "-c", tmp_path, "--config-status"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_sec,
            )
            err = (proc.stderr or "").strip()
            out = (proc.stdout or "").strip()
            if proc.returncode != 0:
                if err:
                    hints.append(f"gallery-dl exited {proc.returncode}: {err[:800]}")
                else:
                    hints.append(f"gallery-dl --config-status exited {proc.returncode}")
            else:
                merged = "\n".join(x for x in (out, err) if x).strip()
                if merged:
                    snippet = merged[:500] + ("…" if len(merged) > 500 else "")
                    hints.append(f"config-status: {snippet}")
        finally:
            Path(tmp_path).unlink(missing_ok=True)
    except OSError as e:
        hints.append(f"Smoke subprocess failed: {e}")
    except subprocess.TimeoutExpired:
        hints.append("Smoke timed out (gallery-dl --config-status).")
    return hints


def model_from_client_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Validate client sent an object; normalize."""
    if not isinstance(data, dict):
        return {}
    return copy.deepcopy(data)


def clip_text(s: str, max_len: int) -> str:
    if len(s) <= max_len:
        return s
    return s[: max_len - 1] + "…"
