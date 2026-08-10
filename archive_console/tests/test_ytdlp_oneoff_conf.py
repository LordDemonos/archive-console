"""Tests for yt-dlp-oneoff.conf overlay helpers."""

from __future__ import annotations

from pathlib import Path

from app.yt_dlp_oneoff_conf import (
    ONEOFF_CONF_FILENAME,
    apply_oneoff_builtin_preset,
    ensure_oneoff_conf,
    parse_oneoff_conf,
    serialize_oneoff_conf,
)


def test_serialize_and_parse_roundtrip() -> None:
    model = {
        "format": "bestvideo+bestaudio/best",
        "merge_output_format": "mkv",
        "noplaylist": True,
    }
    text = serialize_oneoff_conf(model, preset_id="balanced")
    managed, tail = parse_oneoff_conf(text)
    assert managed["format"] == model["format"]
    assert managed["merge_output_format"] == "mkv"
    assert managed["noplaylist"] is True


def test_apply_oneoff_builtin_preset() -> None:
    out = apply_oneoff_builtin_preset({}, "audio_only")
    assert "bestaudio" in out["format"]


def test_ensure_oneoff_conf_creates_file(tmp_path: Path) -> None:
    p = ensure_oneoff_conf(tmp_path)
    assert p.name == ONEOFF_CONF_FILENAME
    assert p.is_file()
    managed, _ = parse_oneoff_conf(p.read_text(encoding="utf-8"))
    assert managed["format"].startswith("bestvideo*+bestaudio")
    assert managed["noplaylist"] is True
