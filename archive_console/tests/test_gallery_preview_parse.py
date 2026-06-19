"""Parse gallery-dl -s -j stdout: JSON array (current) vs NDJSON (legacy)."""

from __future__ import annotations

import json
from pathlib import Path

from app.gallery_util import (
    parse_gallery_dl_json_lines,
    sanitize_gallery_dl_stderr,
)

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "gallery_dl_preview_reddit_like.json"


def test_parse_gallery_dl_json_array_message_url_only() -> None:
    """Message.Url (3) tuples become rows; tuple URL is merged into kwdict."""
    doc = [
        [3, "https://example.com/photo.jpg", {"title": "Test"}],
    ]
    text = json.dumps(doc, indent=2)
    rows, errs = parse_gallery_dl_json_lines(text, max_rows=50)
    assert not errs
    assert len(rows) == 1
    assert rows[0]["title"] == "Test"
    assert rows[0]["media_urls"] == ["https://example.com/photo.jpg"]


def test_parse_gallery_dl_skips_directory_not_url() -> None:
    """Message.Directory (2) is metadata; same post also has Message.Url (3) — one row."""
    post = {
        "title": "Same post",
        "url": "https://www.reddit.com/r/x/comments/zz/permalink/",
    }
    doc = [
        [2, post],
        [3, "https://i.redd.it/img.jpeg", {"title": "Same post", "filename": "img.jpeg"}],
    ]
    rows, errs = parse_gallery_dl_json_lines(json.dumps(doc), max_rows=50)
    assert not errs
    assert len(rows) == 1
    assert rows[0]["media_urls"] == ["https://i.redd.it/img.jpeg"]
    assert rows[0]["suggested_filename"] == "img.jpeg"


def test_parse_fixture_reddit_like_no_duplicate_rows() -> None:
    """Redacted fixture: directory + url messages must not double the table."""
    text = _FIXTURE.read_text(encoding="utf-8")
    rows, errs = parse_gallery_dl_json_lines(text, max_rows=500)
    assert not errs
    assert len(rows) == 1
    assert rows[0]["media_urls"] == ["https://i.redd.it/sample.jpeg"]
    all_urls = [u for r in rows for u in r.get("media_urls", [])]
    assert len(all_urls) == len(set(all_urls))


def test_parse_gallery_dl_ndjson_legacy() -> None:
    line = '{"title": "L", "url": "https://example.com/b.png"}'
    rows, errs = parse_gallery_dl_json_lines(line + "\n", max_rows=50)
    assert len(rows) == 1
    assert rows[0]["title"] == "L"


def test_parse_gallery_dl_error_tuple_surfaces_message() -> None:
    """Message.Error (-1) yields no rows but a readable warning (stderr may be empty)."""
    doc = [
        [
            -1,
            {
                "error": "NotFoundError",
                "message": "Requested resource (gallery/image) could not be found",
            },
        ],
    ]
    rows, errs = parse_gallery_dl_json_lines(json.dumps(doc), max_rows=50)
    assert rows == []
    assert errs
    assert "NotFoundError" in errs[0]
    assert "could not be found" in errs[0]


def test_parse_truncated_array_falls_back_with_error() -> None:
    """Invalid full JSON on array output should not spam NDJSON line errors."""
    text = "[\n  [2, {\"title\": \"x\""
    rows, errs = parse_gallery_dl_json_lines(text, max_rows=10)
    assert rows == []
    assert len(errs) == 1
    assert "incomplete" in errs[0].lower() or "preview" in errs[0].lower()


def test_sanitize_stderr_truncates() -> None:
    long = "e" * 2000
    out = sanitize_gallery_dl_stderr(long, max_len=100)
    assert len(out) <= 100
    assert out.endswith("…")


def test_parse_gallery_dl_error_reddit_wall_becomes_short_hint() -> None:
    """AbortExtraction must not paste megabytes of Reddit theme CSS into parse_warnings."""
    css = ".theme-light,:root{--rem360:22.5rem}" + ("--x:y;" * 120)
    tail = " You've been blocked by network security. File a ticket"
    doc = [
        [
            -1,
            {
                "error": "AbortExtraction",
                "message": css + tail,
            },
        ],
    ]
    rows, errs = parse_gallery_dl_json_lines(json.dumps(doc), max_rows=50)
    assert rows == []
    assert len(errs) == 1
    assert "bot block" in errs[0].lower() or "cookies" in errs[0].lower()
    assert ".theme-light" not in errs[0]
    assert len(errs[0]) < 600


def test_sanitize_stderr_reddit_wall_compact() -> None:
    blob = ".theme-light" + "x" * 900 + " you've been blocked by network security"
    out = sanitize_gallery_dl_stderr(blob, max_len=1200)
    assert len(out) < len(blob)
    assert "bot block" in out.lower() or "cookies" in out.lower()
    assert ".theme-light" not in out
