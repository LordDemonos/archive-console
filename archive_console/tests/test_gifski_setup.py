"""Tests for gifsky.conf setup."""

from __future__ import annotations

import pytest

from app.gifski_setup import (
    DEFAULT_STATE,
    apply_builtin_preset,
    model_from_client_dict,
    parse_gifsky_conf_text,
    preview_summary,
    serialize_gifsky_conf,
)


def test_default_hq_reddit_preset() -> None:
    s = apply_builtin_preset({}, "hq_reddit")
    assert s["quality"] == 100
    assert s["fps"] == 30
    assert s["max_source_mb"] == 20


def test_serialize_round_trip() -> None:
    raw = serialize_gifsky_conf(DEFAULT_STATE)
    state, _ = parse_gifsky_conf_text(raw)
    assert state["quality"] == DEFAULT_STATE["quality"]
    assert "mp4" in state["extensions"]


def test_extensions_from_comma_string_in_model() -> None:
    s = model_from_client_dict({"extensions": "mp4, webm, MOV"})
    assert s["extensions"] == ["mp4", "webm", "mov"]


def test_preview_summary_mentions_fps() -> None:
    txt = preview_summary(DEFAULT_STATE)
    assert "fps=30" in txt
