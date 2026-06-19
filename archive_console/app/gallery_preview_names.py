"""Human-meaningful suggested filenames for Galleries preview (advisory; not gallery-dl output)."""

from __future__ import annotations

import hashlib
import logging
import re
import unicodedata
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Windows-forbidden in filenames + control characters
_FORBIDDEN_CHARS = frozenset('<>:"/\\|?*')

_KNOWN_MEDIA_EXT = frozenset(
    {
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
        ".gif",
        ".bmp",
        ".mp4",
        ".webm",
        ".mkv",
        ".mov",
        ".m4v",
        ".gifv",
        ".avi",
        ".opus",
        ".m4a",
        ".mp3",
        ".wav",
    }
)

# Broad emoji / pictographic blocks → single rule: replace with underscore
_EMOJI_LIKE_RE = re.compile(
    "["
    "\U0001F1E0-\U0001F1FF"
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0000FE00-\U0000FE0F"
    "\U0000200D"
    "\U000020E3"
    "]+",
    flags=re.UNICODE,
)


def sanitize_title_to_stem(title: str, *, max_keep: int = 120) -> str:
    """
    Filesystem-safe stem from post title: NFKC, strip controls, remove emoji (replaced with `_`),
    replace forbidden Windows characters, collapse whitespace to `_`, trim spaces/tabs/dots at ends.
    If still over ``max_keep`` chars, truncate and append ``_`` + 8-char hash.
    """
    raw = unicodedata.normalize("NFKC", (title or "").strip())
    raw = _EMOJI_LIKE_RE.sub("_", raw)
    parts: list[str] = []
    for ch in raw:
        cat = unicodedata.category(ch)
        if cat[0] == "C" and ch not in "\t\n\r ":
            continue
        if ch in _FORBIDDEN_CHARS or ord(ch) < 32:
            parts.append("_")
        else:
            parts.append(ch)
    s = "".join(parts)
    s = re.sub(r"[\s_]+", "_", s).strip(" \t").strip(".")
    if not s or re.fullmatch(r"_+", s):
        s = "untitled"
    if len(s) > max_keep:
        h = hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:8]
        keep = max(16, max_keep - 9)
        s = s[:keep] + "_" + h
    return s


def extension_from_media_url(url: str) -> str | None:
    """Return lowercase extension (including dot) if URL path ends with a known media suffix."""
    if not url or not isinstance(url, str):
        return None
    path = urlparse(url.strip()).path.lower()
    if not path or "." not in path:
        return None
    base = path.rsplit("/", 1)[-1]
    dot = base.rfind(".")
    if dot < 0:
        return None
    ext = base[dot:].split("?", 1)[0]
    if len(ext) < 2 or len(ext) > 10:
        return None
    ext = ext.lower()
    if ext in _KNOWN_MEDIA_EXT:
        return ext
    if ext == ".jpe":
        return ".jpg"
    return None


def default_extension_for_type(mtype: str) -> str:
    if mtype == "video":
        return ".mp4"
    if mtype == "image":
        return ".jpg"
    return ""


def pick_extension_for_row(media_urls: list[str], mtype: str) -> str:
    for u in media_urls:
        ext = extension_from_media_url(u)
        if ext:
            return ext
    return default_extension_for_type(mtype)


def dedupe_gallery_preview_rows_by_primary_url(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Drop duplicate rows that share the same first media URL (stable order)."""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for r in rows:
        urls = r.get("media_urls") if isinstance(r.get("media_urls"), list) else []
        key = (urls[0] if urls else "") or str(r.get("row_id", ""))
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    dropped = len(rows) - len(out)
    if dropped:
        logger.debug("galleries preview: deduped %s duplicate primary-URL rows", dropped)
    return out


def apply_smart_suggested_filenames(rows: list[dict[str, Any]]) -> None:
    """
    Set ``suggested_filename`` on each row: sanitized **title** stem + extension from URL/type.
    Collisions in this preview batch get ``_2``, ``_3``, … before the extension.
    Actual gallery-dl filenames follow ``gallery-dl.conf`` — this column is **advisory** only.
    """
    counts: dict[str, int] = {}
    for r in rows:
        title = str(r.get("title") or "")
        stem = sanitize_title_to_stem(title)
        urls = r.get("media_urls") if isinstance(r.get("media_urls"), list) else []
        mtype = str(r.get("type") or "unknown")
        ext = pick_extension_for_row(urls, mtype)
        key = f"{stem.lower()}{ext.lower()}"
        n = counts.get(key, 0)
        counts[key] = n + 1
        if n == 0:
            final_stem = stem
        else:
            final_stem = f"{stem}_{n + 1}"
        r["suggested_filename"] = f"{final_stem}{ext}" if ext else final_stem
