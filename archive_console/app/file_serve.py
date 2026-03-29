"""Inline-first file responses for /reports/file (allowlisted paths only)."""

from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse

from .editor_files import COOKIES_TXT

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
