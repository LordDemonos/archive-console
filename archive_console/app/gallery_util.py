"""Reddit / gallery-dl URL normalization and JSON line parsing for preview + driver."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any
from urllib.parse import urlparse, urlunparse

_REDDIT_HOST = re.compile(
    r"^(?:www\.|old\.|new\.|np\.)?reddit\.com$",
    re.I,
)


def normalize_gallery_url(raw: str) -> str:
    """
    Strip whitespace; ensure scheme; normalize reddit hosts to www.reddit.com.
    Does not force /user/.../submitted/ — UI documents that for full user feeds.
    """
    u = (raw or "").strip()
    if not u:
        raise ValueError("URL is empty")
    if not re.match(r"^https?://", u, re.I):
        u = "https://" + u
    parsed = urlparse(u)
    if not parsed.netloc:
        raise ValueError("Invalid URL")
    host = parsed.netloc.lower()
    if _REDDIT_HOST.match(host):
        netloc = "www.reddit.com"
        path = parsed.path or "/"
        u = urlunparse(
            ("https", netloc, path, parsed.params, parsed.query, parsed.fragment)
        )
    return u


def stable_row_id(*parts: str) -> str:
    h = hashlib.sha256("|".join(parts).encode("utf-8", errors="replace")).hexdigest()
    return h[:16]


_VIDEO_EXT = frozenset(
    {".mp4", ".webm", ".mkv", ".mov", ".m4v", ".gifv", ".avi"}
)
_IMAGE_EXT = frozenset({".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"})


def _media_type_from_url(url: str) -> str:
    lu = (url or "").lower().split("?", 1)[0]
    for ext in _VIDEO_EXT:
        if lu.endswith(ext):
            return "video"
    if "v.redd.it" in lu or "reddit.com/video" in lu:
        return "video"
    for ext in _IMAGE_EXT:
        if lu.endswith(ext):
            return "image"
    return "unknown"


def _extract_urls_from_obj(obj: Any) -> list[str]:
    out: list[str] = []
    if isinstance(obj, str) and obj.startswith(("http://", "https://")):
        out.append(obj)
    elif isinstance(obj, list):
        for x in obj:
            out.extend(_extract_urls_from_obj(x))
    elif isinstance(obj, dict):
        for k in ("url", "_fallback", "file_url", "image"):
            v = obj.get(k)
            if isinstance(v, str) and v.startswith(("http://", "https://")):
                out.append(v)
            elif isinstance(v, list):
                for x in v:
                    out.extend(_extract_urls_from_obj(x))
            elif isinstance(v, dict):
                out.extend(_extract_urls_from_obj(v))
    return out


def _flatten_gallery_entry(obj: dict[str, Any]) -> dict[str, Any]:
    """One gallery-dl JSON object → preview row fields."""
    title = str(obj.get("title") or obj.get("filename") or "")[:500]
    post_hint = str(obj.get("post_url") or obj.get("_url") or "").strip()
    u0 = obj.get("url")

    urls: list[str] = []
    if isinstance(u0, str) and u0.startswith(("http://", "https://")):
        urls.append(u0)
    elif isinstance(u0, list):
        urls.extend(_extract_urls_from_obj(u0))
    urls.extend(_extract_urls_from_obj(obj.get("_fallback")))

    seen: set[str] = set()
    media_urls: list[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            media_urls.append(u)

    primary = media_urls[0] if media_urls else ""
    source_url = post_hint if post_hint.startswith("http") else ""
    if not source_url and isinstance(u0, str) and "/comments/" in u0:
        source_url = u0
    if not source_url:
        source_url = primary

    suggested = str(obj.get("filename") or "")
    if not suggested and primary:
        suggested = primary.rsplit("/", 1)[-1].split("?", 1)[0][:200]

    mtype = _media_type_from_url(primary) if primary else "unknown"
    if mtype == "unknown" and media_urls:
        mtype = _media_type_from_url(media_urls[0])

    warnings: list[str] = []
    if not media_urls:
        warnings.append("no_media_url_in_json")

    rid = stable_row_id(source_url or title, primary or json.dumps(obj, sort_keys=True)[:200])
    return {
        "row_id": rid,
        "title": title,
        "source_url": source_url[:800] if source_url.startswith("http") else "",
        "media_urls": media_urls,
        "suggested_filename": suggested,
        "type": mtype,
        "warnings": warnings,
    }


def parse_gallery_dl_json_lines(
    text: str, *, max_rows: int = 500
) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Parse stdout from `gallery-dl -s -j` (one JSON object per line).
    Returns (rows, parse_errors).
    """
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    for line_num, line in enumerate(text.splitlines(), 1):
        if len(rows) >= max_rows:
            break
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        try:
            obj = json.loads(s)
        except json.JSONDecodeError as e:
            errors.append(f"line {line_num}: {e}")
            continue
        if not isinstance(obj, dict):
            continue
        rows.append(_flatten_gallery_entry(obj))
    return rows, errors


def cookie_likely_needed(stderr_stdout: str) -> bool:
    t = (stderr_stdout or "").lower()
    needles = (
        "login",
        "cookie",
        "403",
        "401",
        "forbidden",
        "nsfw",
        "private",
        "sign in",
        "unavailable",
    )
    return any(n in t for n in needles)
