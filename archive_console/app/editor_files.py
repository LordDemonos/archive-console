"""Allowlisted repo-root config/input files for the editor API."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote

from .cookies_paths import COOKIES_TXT, is_site_cookies_rel
from .paths import PathNotAllowedError, resolve_under_root

EDITABLE_FILENAMES: frozenset[str] = frozenset(
    {
        "playlists_input.txt",
        "channels_input.txt",
        "videos_input.txt",
        "yt-dlp.conf",
        "gallery-dl.conf",
        COOKIES_TXT,
    }
)


def parse_editor_filename(raw: str) -> str:
    name = unquote(raw).strip().replace("\\", "/")
    if not name or name in (".", ".."):
        raise PathNotAllowedError("invalid editor path")
    if name in EDITABLE_FILENAMES:
        return name
    if is_site_cookies_rel(name):
        return name
    if "/" in name:
        raise PathNotAllowedError("unknown_editable_file")
    raise PathNotAllowedError("unknown_editable_file")


def resolve_editor_file(archive_root: Path, raw_name: str) -> Path:
    name = parse_editor_filename(raw_name)
    return resolve_under_root(archive_root, name)


def strip_blank_lines(text: str) -> str:
    lines = [ln for ln in text.splitlines() if ln.strip() != ""]
    return "\n".join(lines) + ("\n" if lines else "")
