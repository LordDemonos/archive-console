"""Unit tests: preview suggested filenames (sanitizer, extensions, collisions, dedupe)."""

from __future__ import annotations

from app.gallery_preview_names import (
    apply_smart_suggested_filenames,
    dedupe_gallery_preview_rows_by_primary_url,
    default_extension_for_type,
    extension_from_media_url,
    pick_extension_for_row,
    sanitize_title_to_stem,
)


def test_sanitize_title_colon_and_emoji() -> None:
    # Windows-forbidden ':' → '_'; emoji (white heart) → '_' per single rule
    s = sanitize_title_to_stem(":3 🤍")
    assert ":" not in s
    assert "\u200d" not in s  # no ZWJ leftovers from emoji handling
    assert "3" in s
    assert s == "_3_"


def test_sanitize_title_hyphen_and_spaces() -> None:
    s = sanitize_title_to_stem("Sana - TWICE")
    assert s == "Sana_-_TWICE"


def test_sanitize_title_emoji_phrase() -> None:
    s = sanitize_title_to_stem("too cool for school 😎")
    assert s == "too_cool_for_school_"
    assert "😎" not in s


def test_sanitize_odd_punctuation() -> None:
    s = sanitize_title_to_stem('foo*bar?baz\\qux')
    assert "*" not in s
    assert "?" not in s
    assert "\\" not in s
    assert s == "foo_bar_baz_qux"


def test_sanitize_empty_fallback() -> None:
    assert sanitize_title_to_stem("") == "untitled"
    assert sanitize_title_to_stem("   🤍   ") == "untitled"


def test_sanitize_truncation_hash_suffix() -> None:
    long = "a" * 200
    s = sanitize_title_to_stem(long, max_keep=120)
    assert len(s) <= 120 + 1 + 8  # keep + '_' + 8 hex
    assert "_" in s
    assert s.endswith(s.split("_")[-1])
    assert len(s.split("_")[-1]) == 8


def test_extension_from_url_lowercase() -> None:
    assert extension_from_media_url("https://x.com/PATH/FILE.JPEG?x=1") == ".jpeg"
    assert extension_from_media_url("https://x.com/v.Mp4") == ".mp4"


def test_extension_jpe_maps_to_jpg() -> None:
    assert extension_from_media_url("https://x.com/a.jpe") == ".jpg"


def test_pick_extension_falls_back_to_type() -> None:
    assert pick_extension_for_row([], "video") == ".mp4"
    assert pick_extension_for_row(["https://x.com/noext"], "image") == ".jpg"
    assert pick_extension_for_row(["https://x.com/a.png"], "video") == ".png"


def test_apply_smart_collision_suffix() -> None:
    rows = [
        {
            "title": "Same",
            "media_urls": ["https://a.com/1.jpg"],
            "type": "image",
            "row_id": "1",
        },
        {
            "title": "Same",
            "media_urls": ["https://a.com/2.jpg"],
            "type": "image",
            "row_id": "2",
        },
    ]
    apply_smart_suggested_filenames(rows)
    assert rows[0]["suggested_filename"] == "Same.jpg"
    assert rows[1]["suggested_filename"] == "Same_2.jpg"


def test_dedupe_same_primary_url_keeps_first() -> None:
    rows = [
        {
            "title": "First",
            "media_urls": ["https://a.com/1.jpg"],
            "type": "image",
            "row_id": "a",
        },
        {
            "title": "Second",
            "media_urls": ["https://a.com/1.jpg"],
            "type": "image",
            "row_id": "b",
        },
    ]
    out = dedupe_gallery_preview_rows_by_primary_url(rows)
    assert len(out) == 1
    assert out[0]["title"] == "First"


def test_default_extension_for_type_unknown() -> None:
    assert default_extension_for_type("unknown") == ""
