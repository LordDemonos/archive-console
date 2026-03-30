"""Unit tests for rename stem logic and collision handling."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.rename_pipeline import (
    prepare_deepl_input,
    sanitize_windows_basename,
    split_basename,
    unique_target_basename,
    unshield_brackets,
    shield_brackets,
)


def test_split_basename_nested_ext() -> None:
    assert split_basename("a.b.c") == ("a.b", ".c")


def test_split_basename_dotfile() -> None:
    assert split_basename(".hidden") == (".hidden", "")


def test_prepare_youtube_suffix() -> None:
    pr, mid, suf, _br = prepare_deepl_input(
        "한글제목-dQw4w9WgXcQ",
        whole_basename=False,
        preserve_youtube_id=True,
        preserve_brackets=False,
    )
    assert pr == ""
    assert mid == "한글제목"
    assert suf == "-dQw4w9WgXcQ"


def test_prepare_date_then_youtube() -> None:
    pr, mid, suf, _br = prepare_deepl_input(
        "20240330_한글-dQw4w9WgXcQ",
        whole_basename=False,
        preserve_youtube_id=True,
        preserve_brackets=False,
    )
    assert pr == "20240330"
    assert mid == "_한글"
    assert suf == "-dQw4w9WgXcQ"


def test_prepare_whole_basename_skips_heuristics() -> None:
    pr, mid, suf, _br = prepare_deepl_input(
        "20240330-dQw4w9WgXcQ",
        whole_basename=True,
        preserve_youtube_id=True,
        preserve_brackets=False,
    )
    assert pr == ""
    assert mid == "20240330-dQw4w9WgXcQ"
    assert suf == ""


def test_shield_brackets() -> None:
    s, parts = shield_brackets("前【保留】后")
    assert "<<BR0>>" in s
    assert parts == ["【保留】"]
    assert unshield_brackets("Before<<BR0>>After", parts) == "Before【保留】After"


def test_sanitize_windows_replaces_invalid() -> None:
    name, warns = sanitize_windows_basename('bad<>:"|?*.mp4')
    assert "<" not in name
    assert ">" not in name
    assert warns


def test_collision_suffix_before_ext(tmp_path: Path) -> None:
    root = tmp_path
    (root / "videos").mkdir(parents=True)
    (root / "videos" / "t.mp4").write_bytes(b"x")
    (root / "videos" / "other.mp4").write_bytes(b"y")
    allowed = ["videos"]
    u, _w = unique_target_basename(
        root,
        "videos",
        "t.mp4",
        allowed,
        exclude_source_rel="videos/other.mp4",
    )
    assert u == "t_2.mp4"


def test_collision_allows_same_inode_as_source(tmp_path: Path) -> None:
    root = tmp_path
    (root / "videos").mkdir(parents=True)
    (root / "videos" / "only.mp4").write_bytes(b"x")
    allowed = ["videos"]
    u, _w = unique_target_basename(
        root,
        "videos",
        "only.mp4",
        allowed,
        exclude_source_rel="videos/only.mp4",
    )
    assert u == "only.mp4"


def test_assert_allowed_rejected_outside_allowlist(tmp_path: Path) -> None:
    from app.paths import PathNotAllowedError, assert_allowed_path

    root = tmp_path
    d = root / "videos"
    d.mkdir(parents=True)
    (d / "a.mp4").write_bytes(b"x")
    with pytest.raises(PathNotAllowedError):
        assert_allowed_path(root, "videos/a.mp4", ["logs"])
