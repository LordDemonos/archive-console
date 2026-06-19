"""Site cookie files under ``cookies/`` (Netscape format, gallery-dl per-extractor)."""

from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any

from .paths import PathNotAllowedError, normalize_rel, resolve_under_root

COOKIES_DIR_REL = "cookies"
COOKIES_TXT = "cookies.txt"

_SITE_COOKIE_NAME = re.compile(
    r"^[a-z0-9][a-z0-9_-]{0,62}\.txt$",
    re.I,
)
_SIMPLE_COOKIE_STEM = re.compile(
    r"^[a-z0-9][a-z0-9_-]{0,62}$",
    re.I,
)


def is_site_cookies_rel(rel: str) -> bool:
    """True for ``cookies/<name>.txt`` (single directory level)."""
    rel_n = normalize_rel(rel)
    if not rel_n.lower().startswith(COOKIES_DIR_REL + "/"):
        return False
    rest = rel_n[len(COOKIES_DIR_REL) + 1 :]
    if "/" in rest or "\\" in rest:
        return False
    return bool(_SITE_COOKIE_NAME.match(rest))


def is_sensitive_cookie_rel(rel: str) -> bool:
    """Root ``cookies.txt`` or any allowlisted site file under ``cookies/``."""
    rel_n = normalize_rel(rel)
    if rel_n == COOKIES_TXT:
        return True
    return is_site_cookies_rel(rel_n)


def parse_site_cookie_basename(raw: str) -> str:
    """Validate site slug; returns filename like ``instagram.txt``."""
    name = (raw or "").strip().replace("\\", "/")
    if "/" in name:
        raise PathNotAllowedError("invalid site cookie name")
    if not name.lower().endswith(".txt"):
        name = f"{name}.txt"
    if not _SITE_COOKIE_NAME.match(name):
        raise PathNotAllowedError("invalid site cookie name")
    return name


def site_cookie_rel_from_basename(basename: str) -> str:
    bn = parse_site_cookie_basename(basename)
    return f"{COOKIES_DIR_REL}/{bn}"


def resolve_site_cookie_file(archive_root: Path, raw_name: str) -> Path:
    rel = site_cookie_rel_from_basename(raw_name)
    return resolve_under_root(archive_root, rel)


def list_site_cookie_files(archive_root: Path) -> list[dict[str, object]]:
    root = archive_root.resolve()
    d = root / COOKIES_DIR_REL
    if not d.is_dir():
        return []
    out: list[dict[str, object]] = []
    for p in sorted(d.iterdir(), key=lambda x: x.name.lower()):
        if not p.is_file():
            continue
        if not _SITE_COOKIE_NAME.match(p.name):
            continue
        rel = p.relative_to(root).as_posix()
        try:
            st = p.stat()
        except OSError:
            continue
        out.append(
            {
                "rel": rel,
                "name": p.name,
                "basename": p.stem,
                "size": st.st_size,
                "mtime": st.st_mtime,
            }
        )
    return out


def ensure_cookies_dir(archive_root: Path) -> Path:
    d = archive_root.resolve() / COOKIES_DIR_REL
    d.mkdir(parents=True, exist_ok=True)
    return d


def is_simple_cookie_stem(stem: str) -> bool:
    """True when ``stem`` is a valid gallery-dl cookie filename stem (no ``.txt``)."""
    return bool(_SIMPLE_COOKIE_STEM.match((stem or "").strip()))


def site_cookie_rel_for_stem(stem: str) -> str:
    """Relative path ``cookies/<stem>.txt`` for a validated stem."""
    return site_cookie_rel_from_basename(f"{stem.strip()}.txt")


def cookie_stem_for_extractor_id(extractor_id: str) -> str | None:
    """
    Map a gallery-dl extractor id to a cookie file stem.

    Uses the category segment before ``:`` (e.g. ``instagram:tag`` → ``instagram``).
    Returns lowercase stem or None when not a simple filesystem slug.
    """
    raw = (extractor_id or "").strip()
    if not raw:
        return None
    base = raw.split(":", 1)[0].strip()
    if not is_simple_cookie_stem(base):
        return None
    return base.lower()


def site_cookie_stems_on_disk(archive_root: Path) -> dict[str, str]:
    """Lowercase stem → relative path for each ``cookies/<stem>.txt`` on disk."""
    return {
        str(row["basename"]).lower(): str(row["rel"])
        for row in list_site_cookie_files(archive_root)
    }


def apply_site_cookies_from_disk(
    conf: dict[str, Any],
    archive_root: Path,
) -> dict[str, Any]:
    """
    Wire ``extractor.<stem>.cookies`` from ``cookies/<stem>.txt`` when the file exists.

    Operator ``gallery-dl.conf`` wins: non-empty ``cookies`` path is kept; ``cookies: \"\"``
    disables auto-wire for that extractor.
    """
    on_disk = site_cookie_stems_on_disk(archive_root)
    if not on_disk:
        return conf
    out = copy.deepcopy(conf)
    ex = out.setdefault("extractor", {})
    if not isinstance(ex, dict):
        return out
    for stem, rel in on_disk.items():
        block = ex.get(stem)
        if isinstance(block, dict) and "cookies" in block:
            val = block.get("cookies")
            if isinstance(val, str) and not val.strip():
                continue
            continue
        slot = copy.deepcopy(block) if isinstance(block, dict) else {}
        slot["cookies"] = rel
        ex[stem] = slot
    return out
