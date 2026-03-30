"""Inline-first file responses for /reports/file (allowlisted paths only)."""

from __future__ import annotations

import os
import stat
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse

from .editor_files import COOKIES_TXT
from .paths import PathNotAllowedError, assert_allowed_path

# Suffix (lower) -> Content-Type. Unknown -> application/octet-stream.
MEDIA_BY_SUFFIX: dict[str, str] = {
    ".html": "text/html; charset=utf-8",
    ".htm": "text/html; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
    ".log": "text/plain; charset=utf-8",
    ".csv": "text/csv; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".md": "text/markdown; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".ico": "image/x-icon",
    ".bmp": "image/bmp",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mkv": "video/x-matroska",
    ".avi": "video/x-msvideo",
    ".mov": "video/quicktime",
    ".m4v": "video/x-m4v",
    ".wmv": "video/x-ms-wmv",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".opus": "audio/opus",
    ".ogg": "audio/ogg",
    ".wav": "audio/wav",
    ".flac": "audio/flac",
    ".pdf": "application/pdf",
}


def media_type_for_path(path: Path) -> str:
    return MEDIA_BY_SUFFIX.get(path.suffix.lower(), "application/octet-stream")


PLAYABLE_MEDIA_SUFFIXES: frozenset[str] = frozenset(
    ext
    for ext, mt in MEDIA_BY_SUFFIX.items()
    if mt.startswith("video/") or mt.startswith("audio/")
)


def is_playable_media_path(path: Path) -> bool:
    return path.suffix.lower() in PLAYABLE_MEDIA_SUFFIXES


# Files player queue: video/audio plus common raster images (v1). Not used for Watch Now / clip export.
IMAGE_SLIDESHOW_SUFFIXES_V1: frozenset[str] = frozenset(
    {".jpg", ".jpeg", ".png", ".gif", ".webp"}
)
FILES_PLAYER_QUEUE_SUFFIXES: frozenset[str] = (
    PLAYABLE_MEDIA_SUFFIXES | IMAGE_SLIDESHOW_SUFFIXES_V1
)


def is_files_player_queue_media_path(path: Path) -> bool:
    return path.suffix.lower() in FILES_PLAYER_QUEUE_SUFFIXES


def _too_many_playable_detail(max_files: int) -> str:
    return (
        f"More than {max_files} playable media files in this folder. Narrow the folder "
        f"or pass a lower `max_files` (allowed up to 2000)."
    )


def collect_playable_rels_under_dir(
    archive_root: Path,
    dir_rel: str,
    allowed_prefixes: list[str],
    *,
    recursive: bool,
    max_files: int,
) -> list[str]:
    """
    List queueable media (video/audio + slideshow images v1) under an allowlisted directory.
    Re-validates each path. Returns sorted relative POSIX paths (case-insensitive sort).
    Raises HTTP 400 if more than max_files matches.
    """
    root = archive_root.resolve()
    dir_full = assert_allowed_path(root, dir_rel, allowed_prefixes)
    if not dir_full.is_dir():
        raise HTTPException(status_code=404, detail="not a directory")
    rels: list[str] = []

    def append_candidate(full: Path) -> None:
        nonlocal rels
        try:
            st = full.stat()
        except OSError:
            return
        if not stat.S_ISREG(st.st_mode):
            return
        rel = full.relative_to(root).as_posix()
        try:
            assert_allowed_path(root, rel, allowed_prefixes)
        except PathNotAllowedError:
            return
        try:
            assert_reports_file_not_sensitive(full)
        except HTTPException:
            return
        if not is_files_player_queue_media_path(full):
            return
        rels.append(rel)
        if len(rels) > max_files:
            raise HTTPException(
                status_code=400,
                detail=_too_many_playable_detail(max_files),
            )

    if recursive:
        for dirpath, dirnames, filenames in os.walk(
            dir_full,
            topdown=True,
            followlinks=False,
        ):
            dirnames.sort()
            filenames.sort()
            for fn in filenames:
                append_candidate(Path(dirpath) / fn)
    else:
        try:
            children = list(dir_full.iterdir())
        except OSError as e:
            raise HTTPException(status_code=500, detail=str(e)) from e
        for child in sorted(children, key=lambda p: p.name.lower()):
            append_candidate(child)

    rels.sort(key=lambda r: r.casefold())
    return rels


def allowlisted_file_response(path: Path, *, as_attachment: bool) -> FileResponse:
    """
    Inline: explicit Content-Disposition: inline; filename="..." so browsers render
    HTML/video/image in-tab instead of guessing attachment. Attachment when forced.
    """
    media = media_type_for_path(path)
    p = str(path)
    return FileResponse(
        p,
        media_type=media,
        filename=path.name,
        content_disposition_type="attachment" if as_attachment else "inline",
    )


def assert_reports_file_not_sensitive(path: Path) -> None:
    """Reject serving cookies via browse/report URL even if mis-configured allowlist."""
    if path.name.lower() == COOKIES_TXT.lower():
        raise HTTPException(
            status_code=403,
            detail="cookies.txt is not served through this route",
        )
