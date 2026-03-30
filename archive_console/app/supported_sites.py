"""Read-only supported extractors/sites from yt-dlp and gallery-dl CLIs (subprocess, cached)."""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from typing import Any

from .gallery_cli import gallery_dl_exe_invocable, resolve_gallery_dl_exe

logger = logging.getLogger(__name__)

# Subprocess bounds (paranoid defaults)
LIST_TIMEOUT_SEC = 90.0
VERSION_TIMEOUT_SEC = 15.0
MAX_STDOUT_BYTES = 6 * 1024 * 1024  # 6 MiB

# In-memory cache (short TTL; manual refresh bypasses)
DEFAULT_CACHE_TTL_SEC = 300.0

YTDLP_DOC_HUB = "https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md"
GALLERY_DL_DOC_HUB = "https://github.com/mikf/gallery-dl/blob/master/docs/supportedsites.md"
GALLERY_DL_OPTIONS_DOC = "https://github.com/mikf/gallery-dl/blob/master/docs/options.md"

_cache_lock = threading.Lock()
_cached_payload: dict[str, Any] | None = None
_cached_until: float = 0.0
_cache_ttl_sec: float = DEFAULT_CACHE_TTL_SEC

_CATEGORY_LINE_RE = re.compile(
    r"^Category:\s*(\S+)\s*-\s*Subcategory:\s*(\S+)\s*$",
    re.IGNORECASE,
)
_EXAMPLE_LINE_RE = re.compile(r"^Example\s*:\s*(.+)\s*$", re.IGNORECASE)


def _safe_http_url(url: str | None) -> str | None:
    """Only allow http(s) URLs from CLI output (defense in depth for href injection)."""
    if not url:
        return None
    u = url.strip()
    if len(u) > 2000:
        u = u[:2000]
    if u.startswith("https://") or u.startswith("http://"):
        return u
    return None


@dataclass
class ExtractorRow:
    id: str
    label: str
    doc_url: str
    doc_generic: bool = True
    example_url: str | None = None


def _truncate_bytes(data: bytes, max_len: int) -> tuple[bytes, bool]:
    if len(data) <= max_len:
        return data, False
    return data[:max_len], True


def _run_cli(
    argv: list[str],
    *,
    timeout: float,
) -> tuple[int, str, str, bool]:
    """
    Run fixed argv (no shell). Returns (code, stdout, stderr, truncated).
    stdout is decoded utf-8 with replacement; truncated if over MAX_STDOUT_BYTES.
    """
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            timeout=timeout,
            shell=False,
        )
    except subprocess.TimeoutExpired as e:
        out_b = e.stdout or b""
        err_b = e.stderr or b""
        out_truncated = len(out_b) > MAX_STDOUT_BYTES
        out_b, t2 = _truncate_bytes(out_b, MAX_STDOUT_BYTES)
        if t2:
            out_truncated = True
        return (
            -124,
            out_b.decode("utf-8", errors="replace"),
            err_b.decode("utf-8", errors="replace")[:4000],
            out_truncated,
        )
    except OSError as e:
        logger.warning("supported_sites: failed to spawn %s: %s", argv[0], e)
        return -1, "", str(e), False

    out_truncated = len(proc.stdout) > MAX_STDOUT_BYTES
    out_b, t2 = _truncate_bytes(proc.stdout, MAX_STDOUT_BYTES)
    if t2:
        out_truncated = True
    text = out_b.decode("utf-8", errors="replace")
    err = (proc.stderr or b"").decode("utf-8", errors="replace")[:4000]
    return proc.returncode, text, err, out_truncated


def resolve_ytdlp_argv() -> list[str] | None:
    w = shutil.which("yt-dlp")
    if w:
        return [w, "--list-extractors"]
    return [sys.executable, "-m", "yt_dlp", "--list-extractors"]


def resolve_ytdlp_version_argv() -> list[str] | None:
    w = shutil.which("yt-dlp")
    if w:
        return [w, "--version"]
    return [sys.executable, "-m", "yt_dlp", "--version"]


def _unique_slug(base: str, seen: set[str]) -> str:
    b = (base or "unknown")[:180]
    if b not in seen:
        seen.add(b)
        return b
    n = 2
    while True:
        cand = f"{b[:160]}__{n}"
        if cand not in seen:
            seen.add(cand)
            return cand
        n += 1


def parse_ytdlp_list_extractors(stdout: str, *, doc_hub: str = YTDLP_DOC_HUB) -> list[ExtractorRow]:
    rows: list[ExtractorRow] = []
    seen: set[str] = set()
    for raw in stdout.splitlines():
        line = raw.strip()
        if not line:
            continue
        # Strip simple ANSI (yt-dlp may colorize in some TTY contexts; usually not for pipe)
        line = re.sub(r"\x1b\[[0-9;]*m", "", line)
        slug = line.lower().replace(" ", "_")
        slug = re.sub(r"[^a-z0-9_:.\-]+", "_", slug).strip("_") or "unknown"
        eid = _unique_slug(slug, seen)
        rows.append(
            ExtractorRow(
                id=eid[:200],
                label=line[:500],
                doc_url=doc_hub,
                doc_generic=True,
            )
        )
    rows.sort(key=lambda r: r.label.lower())
    return rows


def parse_gallery_dl_list_extractors(
    stdout: str,
    *,
    doc_hub: str = GALLERY_DL_DOC_HUB,
) -> list[ExtractorRow]:
    rows: list[ExtractorRow] = []
    seen: set[str] = set()
    blocks = re.split(r"\n\s*\n", stdout.strip())
    for block in blocks:
        lines = [ln.rstrip() for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue
        class_name = lines[0].strip()
        category = ""
        subcategory = ""
        example_url: str | None = None
        description = ""
        for ln in lines[1:]:
            m = _CATEGORY_LINE_RE.match(ln.strip())
            if m:
                category, subcategory = m.group(1), m.group(2)
                continue
            em = _EXAMPLE_LINE_RE.match(ln.strip())
            if em:
                example_url = _safe_http_url(em.group(1).strip())
                continue
            if ln.strip() and not description and not ln.lower().startswith("category"):
                description = ln.strip()[:500]

        if category and subcategory:
            raw_id = f"{category}:{subcategory}"
        else:
            raw_id = re.sub(r"[^a-zA-Z0-9_:.\-]+", "_", class_name)[:200] or "unknown"
        eid = _unique_slug(raw_id, seen)

        label_parts = [class_name]
        if description:
            label_parts.append(description)
        label = " — ".join(label_parts)[:600]

        rows.append(
            ExtractorRow(
                id=eid[:220],
                label=label,
                doc_url=doc_hub,
                doc_generic=True,
                example_url=example_url,
            )
        )
    rows.sort(key=lambda r: r.label.lower())
    return rows


def _row_to_api(r: ExtractorRow) -> dict[str, Any]:
    d: dict[str, Any] = {
        "id": r.id,
        "label": r.label,
        "doc_url": r.doc_url,
        "doc_generic": r.doc_generic,
    }
    if r.example_url:
        d["example_url"] = r.example_url
    return d


def _tool_ytdlp() -> dict[str, Any]:
    argv = resolve_ytdlp_argv()
    if not argv:
        return {
            "id": "yt-dlp",
            "label": "yt-dlp",
            "available": False,
            "version": None,
            "error": "Could not resolve yt-dlp executable.",
            "truncated": False,
            "doc_hub_url": YTDLP_DOC_HUB,
            "doc_note": (
                "Official supported sites list (search in page for an extractor name). "
                "Archive Console is not affiliated with yt-dlp."
            ),
            "extractors": [],
        }

    vargv = resolve_ytdlp_version_argv()
    version: str | None = None
    if vargv:
        vc, vout, verr, _ = _run_cli(vargv, timeout=VERSION_TIMEOUT_SEC)
        if vc == 0 and vout.strip():
            version = vout.strip().splitlines()[0][:200]
        elif verr:
            logger.debug("yt-dlp --version stderr: %s", verr[:200])

    code, out, err, truncated = _run_cli(argv, timeout=LIST_TIMEOUT_SEC)
    if code != 0:
        msg = f"exit {code}"
        if err.strip():
            msg += f": {err.strip()[:400]}"
        logger.warning(
            "supported_sites: yt-dlp list failed (%s); stdout_len=%s",
            msg,
            len(out),
        )
        return {
            "id": "yt-dlp",
            "label": "yt-dlp",
            "available": False,
            "version": version,
            "error": msg,
            "truncated": truncated,
            "doc_hub_url": YTDLP_DOC_HUB,
            "doc_note": (
                "Official supported sites list. Install yt-dlp on PATH or in the "
                "same Python environment as Archive Console (`python -m yt_dlp`). "
                "Not affiliated with yt-dlp."
            ),
            "extractors": [],
        }

    extractors = parse_ytdlp_list_extractors(out)
    if truncated:
        logger.warning(
            "supported_sites: yt-dlp extractor list truncated at %s bytes",
            MAX_STDOUT_BYTES,
        )
    return {
        "id": "yt-dlp",
        "label": "yt-dlp",
        "available": True,
        "version": version,
        "error": None,
        "truncated": truncated,
        "doc_hub_url": YTDLP_DOC_HUB,
        "doc_note": (
            "Each row links to the project supported sites document — use in-page search "
            "for the extractor name. Versions and lists come from your local install only. "
            "Not affiliated with yt-dlp."
        ),
        "extractors": [_row_to_api(x) for x in extractors],
    }


def _tool_gallery_dl(exe: str) -> dict[str, Any]:
    argv = [exe, "--list-extractors"]
    vargv = [exe, "--version"]

    version: str | None = None
    vc, vout, verr, _ = _run_cli(vargv, timeout=VERSION_TIMEOUT_SEC)
    if vc == 0 and vout.strip():
        version = vout.strip().splitlines()[0][:200]

    code, out, err, truncated = _run_cli(argv, timeout=LIST_TIMEOUT_SEC)
    if code != 0:
        msg = f"exit {code}"
        if err.strip():
            msg += f": {err.strip()[:400]}"
        logger.warning(
            "supported_sites: gallery-dl list failed (%s); stdout_len=%s",
            msg,
            len(out),
        )
        return {
            "id": "gallery-dl",
            "label": "gallery-dl",
            "available": False,
            "version": version,
            "error": msg,
            "truncated": truncated,
            "doc_hub_url": GALLERY_DL_DOC_HUB,
            "options_doc_url": GALLERY_DL_OPTIONS_DOC,
            "doc_note": (
                "Binary was found but `--list-extractors` failed; check the console venv install "
                "(`requirements.txt`) or Galleries tab / `gallery_dl_exe`. "
                "Official docs: supported sites and CLI options. Not affiliated with gallery-dl."
            ),
            "extractors": [],
        }

    extractors = parse_gallery_dl_list_extractors(out)
    if truncated:
        logger.warning(
            "supported_sites: gallery-dl extractor list truncated at %s bytes",
            MAX_STDOUT_BYTES,
        )
    return {
        "id": "gallery-dl",
        "label": "gallery-dl",
        "available": True,
        "version": version,
        "error": None,
        "truncated": truncated,
        "doc_hub_url": GALLERY_DL_DOC_HUB,
        "options_doc_url": GALLERY_DL_OPTIONS_DOC,
        "doc_note": (
            "Each row links to the official supported sites document; example URLs come from "
            "`gallery-dl --list-extractors` on your machine. Not affiliated with gallery-dl."
        ),
        "extractors": [_row_to_api(x) for x in extractors],
    }


def _tool_gallery_dl_missing() -> dict[str, Any]:
    return {
        "id": "gallery-dl",
        "label": "gallery-dl",
        "available": False,
        "version": None,
        "error": (
            "gallery-dl not found next to the Archive Console Python or on PATH "
            "(install with the console venv: pip install -r archive_console/requirements.txt)."
        ),
        "truncated": False,
        "doc_hub_url": GALLERY_DL_DOC_HUB,
        "options_doc_url": GALLERY_DL_OPTIONS_DOC,
        "doc_note": (
            "Install into the Archive Console `.venv` via `requirements.txt` (run "
            "`start_archive_console.bat` so pip installs deps), add gallery-dl to PATH, "
            "or pass `gallery_dl_exe` per Galleries API run. "
            "Lists use `gallery-dl --list-extractors`. Not affiliated with gallery-dl."
        ),
        "extractors": [],
    }


def _build_fresh_tools_payload(ttl: float) -> dict[str, Any]:
    gexe = resolve_gallery_dl_exe(None)
    gtool = _tool_gallery_dl(gexe) if gallery_dl_exe_invocable(gexe) else _tool_gallery_dl_missing()
    ytool = _tool_ytdlp()
    return {
        "cache_ttl_sec": int(ttl),
        "generated_unix": time.time(),
        "disclaimer": (
            "Site and extractor names come from third-party tools on this PC. "
            "Archive Console is not affiliated with yt-dlp or gallery-dl."
        ),
        "tools": [ytool, gtool],
    }


def build_supported_sites_payload(
    *,
    force_refresh: bool = False,
    ttl_sec: float | None = None,
) -> dict[str, Any]:
    """Build full JSON-serializable payload (for API). Uses cache unless force_refresh."""
    global _cached_payload, _cached_until
    ttl = float(ttl_sec if ttl_sec is not None else _cache_ttl_sec)
    now = time.monotonic()
    with _cache_lock:
        if (
            not force_refresh
            and _cached_payload is not None
            and now < _cached_until
        ):
            out = dict(_cached_payload)
            out["cached"] = True
            out["stale"] = False
            return out

    payload = _build_fresh_tools_payload(ttl)
    payload["cached"] = False
    payload["stale"] = False
    with _cache_lock:
        _cached_payload = dict(payload)
        _cached_until = time.monotonic() + ttl
    return payload


def invalidate_supported_sites_cache() -> None:
    global _cached_until
    with _cache_lock:
        _cached_until = 0.0
