"""Download output roots: validation and env mapping."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.download_output import (
    DEFAULT_REL,
    GALLERIES_DEFAULT_REL,
    ONEOFF_DEFAULT_REL,
    abs_file_to_rel,
    abs_folder_to_rel,
    download_dirs_api_payload,
    effective_allowlisted_prefixes,
    extra_env_for_galleries,
    extra_env_for_job,
    extra_env_for_oneoff,
    state_allowed_prefixes,
    validate_download_dirs,
    validate_galleries_output_dir,
    validate_oneoff_output_dir,
)
from app.paths import PathNotAllowedError, is_allowed
from app.settings import ConsoleState, DownloadDirsSettings


def test_defaults_no_extra_env(tmp_path: Path) -> None:
    root = tmp_path / "ar"
    root.mkdir()
    dd = DownloadDirsSettings()
    assert extra_env_for_job(root.resolve(), dd, "watch_later") == {}
    validate_download_dirs(root.resolve(), dd)
    p = download_dirs_api_payload(root.resolve(), dd)
    assert p["watch_later"]["effective_rel"] == DEFAULT_REL["watch_later"]
    assert p["watch_later"]["configured_rel"] is None


def test_custom_rel_extra_env(tmp_path: Path) -> None:
    root = tmp_path / "ar"
    root.mkdir()
    (root / "custom" / "wl").mkdir(parents=True)
    dd = DownloadDirsSettings(watch_later="custom/wl")
    validate_download_dirs(root.resolve(), dd)
    ex = extra_env_for_job(root.resolve(), dd, "watch_later")
    assert "ARCHIVE_OUT_PLAYLIST" in ex
    assert Path(ex["ARCHIVE_OUT_PLAYLIST"]).name == "wl"


def test_custom_download_dir_auto_allowlisted(tmp_path: Path) -> None:
    root = tmp_path / "ar"
    root.mkdir()
    nested = root / "custom" / "wl"
    nested.mkdir(parents=True)
    f = nested / "clip.mp4"
    f.write_bytes(b"x")
    dd = DownloadDirsSettings(watch_later="custom/wl")
    prefixes = effective_allowlisted_prefixes(root.resolve(), dd)
    assert "custom/wl" in prefixes
    assert is_allowed(root.resolve(), f, prefixes)


def test_effective_allowlisted_includes_defaults_and_system(tmp_path: Path) -> None:
    root = tmp_path / "ar"
    root.mkdir()
    st = ConsoleState(archive_root=str(root.resolve()))
    prefixes = state_allowed_prefixes(st)
    assert "logs" in prefixes
    assert "cookies" in prefixes
    assert "playlists" in prefixes
    assert "galleries" in prefixes


def test_nested_playlist_subfolder_allowed(tmp_path: Path) -> None:
    root = tmp_path / "ar"
    archived = root / "playlists" / "Watch Later Archived"
    archived.mkdir(parents=True)
    media = archived / "video.mp4"
    media.write_bytes(b"x")
    st = ConsoleState(archive_root=str(root.resolve()))
    prefixes = state_allowed_prefixes(st)
    assert is_allowed(root.resolve(), media, prefixes)


def test_reject_traversal(tmp_path: Path) -> None:
    root = tmp_path / "ar"
    root.mkdir()
    dd = DownloadDirsSettings(channels="../escape")
    with pytest.raises(PathNotAllowedError):
        validate_download_dirs(root.resolve(), dd)


def test_abs_folder_to_rel(tmp_path: Path) -> None:
    root = tmp_path / "ar"
    root.mkdir()
    (root / "playlists" / "nested").mkdir(parents=True)
    rel, resolved = abs_folder_to_rel(
        root.resolve(),
        root / "playlists" / "nested",
        ["playlists"],
    )
    assert rel == "playlists/nested"
    assert resolved.name == "nested"


def test_abs_file_to_rel(tmp_path: Path) -> None:
    root = tmp_path / "ar"
    root.mkdir()
    media = root / "galleries" / "pic.jpg"
    media.parent.mkdir(parents=True)
    media.write_bytes(b"x")
    rel, resolved = abs_file_to_rel(
        root.resolve(),
        media,
        ["galleries"],
    )
    assert rel == "galleries/pic.jpg"
    assert resolved.name == "pic.jpg"


def test_abs_file_rejects_directory(tmp_path: Path) -> None:
    root = tmp_path / "ar"
    root.mkdir()
    folder = root / "galleries"
    folder.mkdir()
    with pytest.raises(PathNotAllowedError):
        abs_file_to_rel(root.resolve(), folder, ["galleries"])


def test_abs_file_rejects_outside_root(tmp_path: Path) -> None:
    root = tmp_path / "ar"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("x")
    with pytest.raises(PathNotAllowedError):
        abs_file_to_rel(root.resolve(), outside, ["galleries"])


def test_abs_folder_rejects_root_itself(tmp_path: Path) -> None:
    root = tmp_path / "ar"
    root.mkdir()
    with pytest.raises(PathNotAllowedError):
        abs_folder_to_rel(root.resolve(), root.resolve(), ["playlists"])


def test_api_payload_invalid_shows_none_abs(tmp_path: Path) -> None:
    root = tmp_path / "ar"
    root.mkdir()
    dd = DownloadDirsSettings(videos="..")
    p = download_dirs_api_payload(root.resolve(), dd)
    assert p["videos"]["effective_abs"] is None


def test_oneoff_extra_env_default(tmp_path: Path) -> None:
    root = tmp_path / "ar"
    root.mkdir()
    dd = DownloadDirsSettings()
    ex = extra_env_for_oneoff(root.resolve(), dd)
    assert "ARCHIVE_OUT_ONEOFF" in ex
    assert ONEOFF_DEFAULT_REL in ex["ARCHIVE_OUT_ONEOFF"].replace("\\", "/")


def test_oneoff_extra_env_default(tmp_path: Path) -> None:
    root = tmp_path / "ar"
    root.mkdir()
    dd = DownloadDirsSettings()
    ex = extra_env_for_galleries(root.resolve(), dd)
    assert "ARCHIVE_OUT_GALLERIES" in ex
    assert GALLERIES_DEFAULT_REL in ex["ARCHIVE_OUT_GALLERIES"].replace("\\", "/")


def test_galleries_and_oneoff_resolve_under_root(tmp_path: Path) -> None:
    root = tmp_path / "ar"
    root.mkdir()
    dd = DownloadDirsSettings()
    validate_galleries_output_dir(root.resolve(), dd)
    validate_oneoff_output_dir(root.resolve(), dd)
    validate_download_dirs(root.resolve(), dd)


def test_browse_download_dir_body_accepts_oneoff_field() -> None:
    """Regression: One-off browse sends field=oneoff; API must not 422 on validation."""
    from app.main import BrowseDownloadDirBody

    assert BrowseDownloadDirBody(field="oneoff").field == "oneoff"
    for f in ("watch_later", "channels", "videos", "galleries"):
        assert BrowseDownloadDirBody(field=f).field == f
