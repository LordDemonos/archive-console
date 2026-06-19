"""
Reddit-specific gallery-dl defaults for Archive Console (RipMe-style layout + archive).

RipMe historically placed Reddit downloads under single folder names such as
``reddit_sub_<subreddit>`` and ``reddit_user_<username>``, sanitizing characters
that are illegal or awkward on Windows (e.g. a leading hyphen in a username can
become a leading underscore after filesystem rules). We mirror that *shape* using
gallery-dl's per-extractor ``directory`` format strings (see installed
``gallery_dl/extractor/reddit.py`` for available keywords: ``subcategory``,
``subreddit``, ``user[name]``, etc.). gallery-dl applies ``path-restrict`` (e.g.
``windows``) to the final path segments, so edge usernames may differ slightly
from RipMe's exact string but remain stable and safe.

**Archive / de-dupe:** gallery-dl's ``extractor.*.archive`` stores download IDs in
SQLite (see upstream ``docs/configuration.rst`` — ``archive``, ``skip``). We set a
single DB under ``<galleries_output>/_gallery_dl_data/reddit_archive.sqlite3`` so
repeat Galleries runs against the same subreddit/user skip already-archived
media. **Tradeoff:** one DB per galleries output root (not per subfolder) keeps
path management simple; Reddit's default ``archive_fmt`` (``{filename}``) still
dedupes per file. To force a re-download, delete the matching row in the DB or
remove/rename the archive file (see ARCHIVE_CONSOLE.md).

**Media types:** ``videos: false`` skips Reddit-hosted video; ``image-filter`` limits
to common still-image/GIF extensions. Override in ``gallery-dl.conf`` (Reddit section).

**Embedded hosts (redgifs, imgur, …):** ``parent-directory: true`` puts child
extractor files under the active ``reddit_sub_*`` / ``reddit_user_*`` folder
(e.g. ``reddit_user_foo/redgifs/…``), not ``galleries/redgifs/`` at the root.

**Instagram / Twitter:** the global ``extractor.directory`` ``{category}/{subcategory}``
layout would flatten to generic ``instagram/posts``-style paths. We merge
per-extractor ``directory`` defaults (``instagram_{username}``, ``twitter_{user[name]}``)
into the effective config for Galleries runs unless overridden under
``extractor.instagram`` / ``extractor.twitter`` in ``gallery-dl.conf``.
"""

from __future__ import annotations

import copy
import json
import tempfile
from pathlib import Path
from typing import Any

from .cookies_paths import apply_site_cookies_from_disk
from .gallery_dl_setup import deep_merge

# Pipe/terminal skip lines use this prefix (gallery_dl/output.py CHAR_SKIP).
GALLERY_DL_SKIP_LINE_PREFIX = "# "

# Manifest: only files touched during this run (mtime newer than start − slack).
RUN_START_MTIME_SLACK_SEC = 30.0

_GALLERY_DL_DATA_DIR = "_gallery_dl_data"
_REDDIT_ARCHIVE_NAME = "reddit_archive.sqlite3"

# gallery-dl conditional directory: ``subcategory`` is ``subreddit`` for /r/…;
# user extractors use ``user``, ``user-submitted``, etc. (all start with ``user``).
# ``videos: false`` skips Reddit hosted video; ``image-filter`` limits file types.
DEFAULT_REDDIT_EXTRACTOR: dict[str, Any] = {
    "directory": {
        "subcategory.startswith('user')": ["reddit_user_{user[name]}"],
        "": ["reddit_sub_{subreddit}"],
    },
    "skip": True,
    "videos": False,
    "image-filter": "extension in ('jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp')",
    # Nest redgifs/imgur/etc. under the active reddit_* folder (not galleries/redgifs/).
    "parent-directory": True,
}

# Upstream defaults use ``{category}/{username}`` but global ``extractor.directory``
# in gallery-dl.conf overrides them — merge these for Galleries effective config.
DEFAULT_INSTAGRAM_EXTRACTOR: dict[str, Any] = {
    "directory": {
        "subcategory == 'tag'": ["instagram_tag_{tag}"],
        "": ["instagram_{username}"],
    },
    "parent-directory": True,
}

DEFAULT_TWITTER_EXTRACTOR: dict[str, Any] = {
    "directory": ["twitter_{user[name]}"],
    "parent-directory": True,
}

_SOCIAL_LAYOUT_EXTRACTORS: dict[str, dict[str, Any]] = {
    "instagram": DEFAULT_INSTAGRAM_EXTRACTOR,
    "twitter": DEFAULT_TWITTER_EXTRACTOR,
}


def reddit_archive_db_path(galleries_output_root: Path) -> Path:
    """Absolute path to the SQLite download archive for Reddit (under galleries root)."""
    root = galleries_output_root.expanduser().resolve()
    return root / _GALLERY_DL_DATA_DIR / _REDDIT_ARCHIVE_NAME


def load_gallery_dl_conf_dict(conf_path: Path) -> dict[str, Any]:
    if not conf_path.is_file():
        return {}
    try:
        raw = json.loads(conf_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _normalize_user_reddit_overrides(user: dict[str, Any]) -> dict[str, Any]:
    """Blank ``image-filter`` in saved conf means “use Archive default”, not “allow all types”."""
    out = copy.deepcopy(user)
    if out.get("image-filter") == "":
        out.pop("image-filter", None)
    return out


def merge_reddit_ripme_into_conf(disk_conf: dict[str, Any]) -> dict[str, Any]:
    """
    Return a copy of ``disk_conf`` with ``extractor.reddit`` deep-merged from
    DEFAULT_REDDIT_EXTRACTOR (operator keys win). Ensures ``extractor`` shell and
    sensible global defaults when missing.
    """
    out = copy.deepcopy(disk_conf) if isinstance(disk_conf, dict) else {}
    ex = out.setdefault("extractor", {})
    if not isinstance(ex, dict):
        ex = {}
        out["extractor"] = ex
    ex.setdefault("base-directory", ".")
    ex.setdefault("path-restrict", "windows")
    user_reddit = ex.get("reddit")
    if not isinstance(user_reddit, dict):
        user_reddit = {}
    user_reddit = _normalize_user_reddit_overrides(user_reddit)
    ex["reddit"] = deep_merge(copy.deepcopy(DEFAULT_REDDIT_EXTRACTOR), user_reddit)
    outp = out.setdefault("output", {})
    if isinstance(outp, dict) and "skip" not in outp:
        outp["skip"] = True
    return out


def merge_social_layout_into_conf(disk_conf: dict[str, Any]) -> dict[str, Any]:
    """
    Merge Instagram/Twitter per-extractor ``directory`` defaults (operator keys win).

    Without this, global ``extractor.directory`` ``{category}/{subcategory}`` yields
    generic ``instagram/posts`` paths instead of per-account folders.
    """
    out = copy.deepcopy(disk_conf) if isinstance(disk_conf, dict) else {}
    ex = out.setdefault("extractor", {})
    if not isinstance(ex, dict):
        ex = {}
        out["extractor"] = ex
    for name, defaults in _SOCIAL_LAYOUT_EXTRACTORS.items():
        user_block = ex.get(name)
        if not isinstance(user_block, dict):
            user_block = {}
        ex[name] = deep_merge(copy.deepcopy(defaults), user_block)
    return out


def apply_reddit_archive_path_if_unset(
    conf: dict[str, Any],
    galleries_output_root: Path,
) -> dict[str, Any]:
    """Set ``extractor.reddit.archive`` to the canonical DB path when not set on disk."""
    out = copy.deepcopy(conf)
    ex = out.setdefault("extractor", {})
    r = ex.setdefault("reddit", {})
    if not isinstance(r, dict):
        r = {}
        ex["reddit"] = r
    arch = r.get("archive")
    if arch is None or (isinstance(arch, str) and not arch.strip()):
        r["archive"] = str(reddit_archive_db_path(galleries_output_root))
    return out


def build_effective_gallery_conf_for_galleries(
    archive_root: Path,
    galleries_output_root: Path,
) -> dict[str, Any]:
    """Load ``<archive_root>/gallery-dl.conf``, merge RipMe Reddit defaults + archive path."""
    disk = load_gallery_dl_conf_dict(archive_root / "gallery-dl.conf")
    merged = merge_reddit_ripme_into_conf(disk)
    merged = merge_social_layout_into_conf(merged)
    merged = apply_reddit_archive_path_if_unset(merged, galleries_output_root)
    return apply_site_cookies_from_disk(merged, archive_root)


def write_effective_gallery_conf_for_run(
    effective: dict[str, Any],
    log_dir: Path,
) -> Path:
    """Write JSON for this run's ``-c`` (next to run logs for inspection)."""
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / "gallery-dl.effective.json"
    path.write_text(
        json.dumps(effective, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def write_merged_conf_temp(
    effective: dict[str, Any],
    *,
    prefix: str = "gallery-dl-preview-",
) -> Path:
    """Write merged config to a temp file; caller must unlink when done."""
    with tempfile.NamedTemporaryFile(
        mode="w",
        prefix=prefix,
        suffix=".json",
        delete=False,
        encoding="utf-8",
        newline="\n",
    ) as tmp:
        tmp.write(json.dumps(effective, ensure_ascii=False) + "\n")
        return Path(tmp.name)


def count_gallery_dl_skip_lines(stdout_text: str) -> int:
    """Count gallery-dl skip notifications (``# <path>`` in pipe/terminal output)."""
    n = 0
    for line in (stdout_text or "").splitlines():
        s = line.strip("\r")
        if s.startswith(GALLERY_DL_SKIP_LINE_PREFIX):
            n += 1
    return n
