"""Tests for gifsky scan and convert helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.gifski_convert import scan_gallery_videos, validate_gifski_exe_setting
from app.gifski_setup import DEFAULT_STATE
from app.settings import DownloadDirsSettings


def test_validate_gifski_exe_rejects_shell() -> None:
    with pytest.raises(ValueError):
        validate_gifski_exe_setting("gifski;rm -rf /")


def test_scan_empty_galleries(tmp_path: Path) -> None:
    gal = tmp_path / "galleries"
    gal.mkdir()
    out = scan_gallery_videos(
        archive_root=tmp_path,
        allowed_prefixes=["galleries"],
        download_dirs=DownloadDirsSettings(),
        conf=DEFAULT_STATE,
    )
    assert out["galleries_root_rel"] == "galleries"
    assert out["totals"]["videos"] == 0


def test_scan_finds_m4v_in_redgifs_subfolder(tmp_path: Path) -> None:
    gal = tmp_path / "galleries" / "reddit_user_x" / "redgifs" / "image"
    gal.mkdir(parents=True)
    (gal / "clip.m4v").write_bytes(b"x" * 100)
    out = scan_gallery_videos(
        archive_root=tmp_path,
        allowed_prefixes=["galleries"],
        download_dirs=DownloadDirsSettings(),
        conf=DEFAULT_STATE,
    )
    assert out["totals"]["videos"] == 1
    assert len(out["folders"]) == 1
    assert out["folders"][0]["rel"] == "galleries/reddit_user_x"


def test_scan_rollup_groups_nested_paths(tmp_path: Path) -> None:
    base = tmp_path / "galleries" / "reddit_user_y" / "redgifs" / "image"
    base.mkdir(parents=True)
    (base / "a.m4v").write_bytes(b"a")
    (base / "b.m4v").write_bytes(b"b")
    out = scan_gallery_videos(
        archive_root=tmp_path,
        allowed_prefixes=["galleries"],
        download_dirs=DownloadDirsSettings(),
        conf=DEFAULT_STATE,
    )
    assert out["folders"][0]["video_count"] == 2
    assert out["folders"][0]["rel"] == "galleries/reddit_user_y"


def test_cleanup_legacy_frame_files(tmp_path: Path) -> None:
    from app.gifski_convert import _cleanup_legacy_frame_files, _remove_gifsky_work_dir
    from app.gifski_convert import _make_gifsky_frames_dir

    parent = tmp_path / "galleries" / "reddit_user_x"
    parent.mkdir(parents=True)
    (parent / "clip_frame0001.png").write_bytes(b"p")
    (parent / "clip_frame0002.jpg").write_bytes(b"j")
    assert _cleanup_legacy_frame_files(parent, "clip") == 2
    work = _make_gifsky_frames_dir(parent, "clip")
    (work / "frame0001.png").write_bytes(b"x")
    _remove_gifsky_work_dir(work)
    assert not work.exists()

    from app.gifski_convert import build_size_comparison

    c = build_size_comparison(1_000_000, 400_000)
    assert c["delta_pct"] == -60.0
    assert "smaller" not in c["label"]  # negative pct shown as -60.0%


def test_scan_includes_size_comparison_when_gif_exists(tmp_path: Path) -> None:
    gal = tmp_path / "galleries" / "reddit_user_x"
    gal.mkdir(parents=True)
    (gal / "clip.m4v").write_bytes(b"x" * 1000)
    (gal / "clip.gif").write_bytes(b"g" * 2500)
    out = scan_gallery_videos(
        archive_root=tmp_path,
        allowed_prefixes=["galleries"],
        download_dirs=DownloadDirsSettings(),
        conf=DEFAULT_STATE,
    )
    vid = out["folders"][0]["videos"][0]
    assert vid["gif_bytes"] == 2500
    assert vid["size_comparison"]["delta_pct"] == 150.0
    assert out["size_comparison"]["paired_count"] == 1


def test_scan_skips_existing_gif(tmp_path: Path) -> None:
    gal = tmp_path / "galleries" / "reddit_user_x"
    gal.mkdir(parents=True)
    mp4 = gal / "clip.mp4"
    mp4.write_bytes(b"x" * 100)
    (gal / "clip.gif").write_bytes(b"g" * 2000)
    out = scan_gallery_videos(
        archive_root=tmp_path,
        allowed_prefixes=["galleries"],
        download_dirs=DownloadDirsSettings(),
        conf=DEFAULT_STATE,
    )
    assert out["totals"]["videos"] == 1
    assert out["totals"]["pending"] == 0
    assert out["totals"]["skipped"] == 1
