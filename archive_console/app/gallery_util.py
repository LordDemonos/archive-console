"""Reddit / gallery-dl URL normalization and JSON line parsing for preview + driver."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Any
from urllib.parse import urlparse, urlunparse

logger = logging.getLogger(__name__)

# gallery_dl.extractor.message.Message — keep in sync for JSON array parsing only
_GDL_MSG_DIRECTORY = 2
_GDL_MSG_URL = 3
_GDL_MSG_QUEUE = 6
_GDL_MSG_ERROR = -1

_REDDIT_HOST = re.compile(
    r"^(?:www\.|old\.|new\.|np\.)?reddit\.com$",
    re.I,
)


def normalize_gallery_url(raw: str) -> str:
    """
    Strip whitespace; ensure scheme; normalize reddit hosts to www.reddit.com.
    Bare ``/user/<name>`` profiles become ``/user/<name>/submitted/`` (RipMe-style feed).
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
    path = parsed.path or "/"
    if _REDDIT_HOST.match(host):
        netloc = "www.reddit.com"
        path = path.rstrip("/") or "/"
        m_user = re.match(r"^/user/([^/]+)$", path, re.I)
        if m_user:
            path = f"/user/{m_user.group(1)}/submitted/"
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



def get_cookie_path_from_url(url: str) -> str | None:
    """
    Determine the cookie path for a given URL based on the domain.
    Returns the relative path (e.g. 'cookies/twitter.txt') or None.
    """
    if not url or not isinstance(url, str):
        return None
    
    try:
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        if not host:
            return None
    except Exception:
        return None

    # Mapping of domain parts to cookie stems
    mappings = {
        "twitter.com": "twitter",
        "x.com": "twitter",
        "instagram.com": "instagram",
        "tiktok.com": "tiktok",
        "reddit.com": "reddit",
        "pinterest.com": "pinterest",
        "flickr.com": "flickr",
    }

    # Check for direct match in mapping
    for domain, stem in mappings.items():
        if host == domain:
            return f"cookies/{stem}.txt"
    
    # Check if any mapping domain is in the host (e.g. subdomain.twitter.com)
    for domain, stem in mappings.items():
        if domain in host:
            return f"cookies/{stem}.txt"

    # Fallback: Check if the host itself (no extension) is a file in cookies/
    # e.g. if host is 'instagram.com', check for 'cookies/instagram.com.txt'
    return None


def is_twitter_gallery_url(url: str) -> bool:
    """True for x.com / twitter.com gallery sources."""
    try:
        host = urlparse((url or "").strip()).netloc.lower()
    except Exception:
        return False
    if not host:
        return False
    return host in ("x.com", "twitter.com") or host.endswith(".twitter.com")


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


def _rows_from_gallery_dl_json_array(
    data: list[Any], *, max_rows: int
) -> tuple[list[dict[str, Any]], list[str]]:
    """
    gallery-dl ``-j`` dumps ``DataJob.data``: a JSON array of **message tuples**.

    - ``[2, kwdict]`` — Message.Directory (post/folder metadata; not a download)
    - ``[3, url, kwdict]`` — Message.Url (actual media URL + keywords)
    - ``[6, url, kwdict]`` — Message.Queue (hand-off to another extractor; child
      emits Url rows)

    Taking the last dict from every tuple duplicates **Directory** with **Url** for
    the same Reddit post (one row from post JSON, one from the image line). Preview
    should list **download targets** only → emit rows for **Message.Url** (3).
    """
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    skipped = {"directory": 0, "queue": 0, "error": 0, "legacy": 0}

    for i, item in enumerate(data):
        if len(rows) >= max_rows:
            break
        if isinstance(item, dict):
            rows.append(_flatten_gallery_entry(item))
            continue
        if not isinstance(item, list) or len(item) < 2:
            errors.append(f"array item {i + 1}: expected object or non-empty tuple")
            continue

        head = item[0]
        if isinstance(head, int):
            if head == _GDL_MSG_DIRECTORY:
                skipped["directory"] += 1
                continue
            if head == _GDL_MSG_QUEUE:
                skipped["queue"] += 1
                continue
            if head == _GDL_MSG_ERROR:
                skipped["error"] += 1
                if len(item) >= 2 and isinstance(item[1], dict):
                    ed = item[1]
                    kind = str(ed.get("error") or ed.get("exception") or "").strip()
                    raw_msg = str(ed.get("message") or "").strip()
                    msg = summarize_gallery_dl_parse_error_detail(raw_msg)
                    if kind and msg:
                        errors.append(f"gallery-dl {kind}: {msg}")
                    elif msg:
                        errors.append(f"gallery-dl: {msg}")
                    elif kind:
                        errors.append(
                            f"gallery-dl {summarize_gallery_dl_parse_error_detail(kind)}"
                        )
                continue
            if head == _GDL_MSG_URL:
                url_part: str | None = None
                if len(item) >= 2 and isinstance(item[1], str):
                    u1 = item[1].strip()
                    if u1.startswith(("http://", "https://")):
                        url_part = u1
                payload: dict[str, Any] | None = None
                if len(item) >= 3 and isinstance(item[2], dict):
                    payload = dict(item[2])
                elif url_part:
                    payload = {"title": "", "url": url_part}
                if payload is None:
                    errors.append(f"array item {i + 1}: Message.Url missing kwdict")
                    continue
                if url_part and (
                    not isinstance(payload.get("url"), str)
                    or not str(payload.get("url", "")).startswith("http")
                ):
                    payload["url"] = url_part
                rows.append(_flatten_gallery_entry(payload))
                continue

        skipped["legacy"] += 1
        payload = None
        for part in reversed(item):
            if isinstance(part, dict):
                payload = part
                break
        if payload is None:
            errors.append(
                f"array item {i + 1}: expected object or […, {{…}}] tuple (legacy)"
            )
            continue
        rows.append(_flatten_gallery_entry(payload))

    if any(skipped.values()):
        logger.debug(
            "galleries preview JSON array: rows=%s skipped=%s parse_errors=%s",
            len(rows),
            skipped,
            len(errors),
        )
    return rows, errors


def _parse_gallery_dl_ndjson_lines(
    text: str, *, max_rows: int
) -> tuple[list[dict[str, Any]], list[str]]:
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


def compact_gallery_dl_wall_message(text: str) -> str | None:
    """
    If ``text`` looks like Reddit’s bot-wall HTML/CSS stuffed into gallery-dl’s error
    ``message`` field, return a short replacement; otherwise ``None``.
    """
    t = (text or "").strip()
    if not t:
        return None
    tl = t.lower()
    if "blocked by network security" in tl or "you've been blocked" in tl:
        return (
            "Reddit returned a network-security / bot block page (HTML/CSS), not API data - "
            "try fresh logged-in cookies.txt, another network/VPN, or a newer gallery-dl."
        )
    if len(t) > 800 and (
        ".theme-light" in t
        or ".theme-dark" in t
        or "--color-tone-1:" in t
        or "--rem360:" in t
    ):
        if (
            "file a ticket" in tl
            or "network security" in tl
            or t.count("--") > 40
        ):
            return (
                "Site returned Reddit/theme HTML (embedded CSS) instead of extractor JSON - "
                "typical when Reddit blocks unauthenticated/bot traffic; use cookies.txt and/or check gallery-dl Reddit extractor notes."
            )
    return None


def summarize_gallery_dl_parse_error_detail(text: str, *, max_len: int = 420) -> str:
    """Parse-line / job error fragment: collapse walls, then cap length for UI."""
    t = (text or "").strip()
    hit = compact_gallery_dl_wall_message(t)
    if hit is not None:
        return hit
    if len(t) > max_len:
        return t[: max_len - 1] + "…"
    return t


def sanitize_gallery_dl_stderr(text: str, *, max_len: int = 1200) -> str:
    """Truncate stderr for API/UI; collapse Reddit wall pages to a short hint."""
    s = (text or "").replace("\r\n", "\n").strip()
    hit = compact_gallery_dl_wall_message(s)
    if hit is not None:
        return hit
    if len(s) <= max_len:
        return s
    return s[: max_len - 1] + "…"


def parse_gallery_dl_json_lines(
    text: str, *, max_rows: int = 500
) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Parse stdout from ``gallery-dl -s -j``.

    Modern gallery-dl writes a **single pretty-printed JSON array** of job tuples.
    Older/alternate builds may emit **NDJSON** (one JSON object per line).
    """
    raw = text or ""
    stripped = raw.strip()
    errors: list[str] = []

    if stripped.startswith("["):
        try:
            data = json.loads(stripped)
            if isinstance(data, list):
                rows, arr_errs = _rows_from_gallery_dl_json_array(
                    data, max_rows=max_rows
                )
                errors.extend(arr_errs)
                return rows, errors
        except json.JSONDecodeError as e:
            if stripped.startswith("["):
                errors.append(
                    "Preview output incomplete or too large to parse as one JSON document "
                    f"({e}). Run galleries without preview — downloads do not need preview."
                )
                return [], errors
            errors.append(f"full-document json: {e}")

    rows, line_errs = _parse_gallery_dl_ndjson_lines(raw, max_rows=max_rows)
    errors.extend(line_errs)
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
        "blocked by network",
        "you've been blocked",
        "abortextraction",
    )
    return any(n in t for n in needles)
