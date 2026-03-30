"""Download output roots: validation and env mapping."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.download_output import (
    DEFAULT_REL,
    GALLERIES_DEFAULT_REL,
    ONEOFF_DEFAULT_REL,
    abs_folder_to_rel,
    download_dirs_api_payload,
    extra_env_for_galleries,
    extra_env_for_job,
    extra_env_for_oneoff,
    validate_download_dirs,
)
from app.paths import PathNotAllowedError
from app.settings import DownloadDirsSettings

_STD_ALLOW = ["logs", "playlists", "channels", "videos", "custom"]


def test_defaults_no_extra_env(tmp_path: Path) -> None:
    root = tmp_path / "ar"
    root.mkdir()
    dd = DownloadDirsSettings()
    assert extra_env_for_job(root.resolve(), dd, "watch_later") == {}
    validate_download_dirs(root.resolve(), dd, _STD_ALLOW)
    p = download_dirs_api_payload(root.resolve(), dd)
    assert p["watch_later"]["effective_rel"] == DEFAULT_REL["watch_later"]
    assert p["watch_later"]["configured_rel"] is None


def test_custom_rel_extra_env(tmp_path: Path) -> None:
    root = tmp_path / "ar"
    root.mkdir()
    (root / "custom" / "wl").mkdir(parents=True)
    dd = DownloadDirsSettings(watch_later="custom/wl")
    validate_download_dirs(root.resolve(), dd, _STD_ALLOW)
    ex = extra_env_for_job(root.resolve(), dd, "watch_later")
    assert "ARCHIVE_OUT_PLAYLIST" in ex
    assert Path(ex["ARCHIVE_OUT_PLAYLIST"]).name == "wl"


def test_reject_traversal(tmp_path: Path) -> None:
    root = tmp_path / "ar"
    root.mkdir()
    dd = DownloadDirsSettings(channels="../escape")
    with pytest.raises(PathNotAllowedError):
        validate_download_dirs(root.resolve(), dd, _STD_ALLOW)


def test_allowlist_blocks(tmp_path: Path) -> None:
    root = tmp_path / "ar"
    root.mkdir()
    (root / "secret").mkdir()
    dd = DownloadDirsSettings(watch_later="secret")
    with pytest.raises(PathNotAllowedError):
        validate_download_dirs(
            root.resolve(),
            dd,
            ["playlists", "channels", "videos"],
        )


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


def test_abs_folder_rejects_root_itself(tmp_path: Path) -> None:
    root = tmp_path / "ar"
    root.mkdir()
    with pytest.raises(PathNotAllowedError):
        abs_folder_to_rel(root.resolve(), root.resolve(), _STD_ALLOW)


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


def test_oneoff_allowlist_blocks(tmp_path: Path) -> None:
    root = tmp_path / "ar"
    root.mkdir()
    dd = DownloadDirsSettings(oneoff="secret")
    with pytest.raises(PathNotAllowedError):
        validate_download_dirs(
            root.resolve(),
            dd,
            ["playlists", "channels", "videos", "oneoff"],
        )


def test_galleries_extra_env_default(tmp_path: Path) -> None:
    root = tmp_path / "ar"
    root.mkdir()
    dd = DownloadDirsSettings()
    ex = extra_env_for_galleries(root.resolve(), dd)
    assert "ARCHIVE_OUT_GALLERIES" in ex
    assert GALLERIES_DEFAULT_REL in ex["ARCHIVE_OUT_GALLERIES"].replace("\\", "/")


def test_galleries_allowlist_blocks(tmp_path: Path) -> None:
    root = tmp_path / "ar"
    root.mkdir()
    dd = DownloadDirsSettings(galleries="secret")
    with pytest.raises(PathNotAllowedError):
        validate_download_dirs(
            root.resolve(),
            dd,
            ["playlists", "channels", "videos", "galleries"],
        )


def test_browse_download_dir_body_accepts_oneoff_field() -> None:
    """Regression: One-off browse sends field=oneoff; API must not 422 on validation."""
    from app.main import BrowseDownloadDirBody

    assert BrowseDownloadDirBody(field="oneoff").field == "oneoff"
    for f in ("watch_later", "channels", "videos", "galleries"):
        assert BrowseDownloadDirBody(field=f).field == f
