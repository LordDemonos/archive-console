"""Validate normalize YouTube URLs for the one-off driver."""

from __future__ import annotations

import re

_YT_HTTP = re.compile(
    r"^https?://(www\.)?(youtube\.com|youtu\.be)/",
    re.I,
)
_YOUTUBE_ID_LINE = re.compile(
    r"^youtube\s+([A-Za-z0-9_-]{11})\s*$",
    re.I,
)


def normalize_oneoff_youtube_url(url: str) -> str:
    """
    Accept YouTube watch/shorts/embed/ youtu.be URLs or 'youtube VIDEO_ID'.
    Raises ValueError on empty or non-YouTube inputs.
    """
    s = (url or "").strip()
    if not s:
        raise ValueError("URL is empty")
    m = _YOUTUBE_ID_LINE.match(s)
    if m:
        vid = m.group(1)
        return f"https://www.youtube.com/watch?v={vid}"
    if _YT_HTTP.match(s) or s.lower().startswith("https://youtu.be/"):
        return s
    raise ValueError("Enter a YouTube URL (youtube.com or youtu.be) or youtube VIDEO_ID")
