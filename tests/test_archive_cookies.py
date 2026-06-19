"""Tests for archive_cookies staging (cookies.txt → cookies.run.txt)."""

from __future__ import annotations

from pathlib import Path

import pytest

_NETSCAPE_LINE = (
    "# Netscape HTTP Cookie File\n"
    "# https://curl.haxx.se/rfc/cookie_spec.html\n\n"
    ".youtube.com\tTRUE\t/\tTRUE\t0\tSID\tabc\n"
)

from archive_cookies import (
    COOKIES_RUN_NAME,
    COOKIES_SOURCE_NAME,
    _file_mtime,
    append_ytdlp_staged_cookies_argv,
    clear_cookie_refresh_request,
    cookie_refresh_request_payload,
    cookie_refresh_requested,
    is_staged_cookie_path,
    looks_like_netscape_cookies,
    request_cookie_refresh,
    run_cookies_path,
    stage_cookies_for_ytdlp,
    sync_staged_cookies_from_source_if_newer,
)


@pytest.fixture
def script_dir(tmp_path: Path) -> Path:
    src = tmp_path / COOKIES_SOURCE_NAME
    src.write_text(_NETSCAPE_LINE, encoding="utf-8")
    return tmp_path


def test_stage_copies_source_to_run(script_dir: Path) -> None:
    rel = stage_cookies_for_ytdlp(str(script_dir))
    assert rel == COOKIES_RUN_NAME
    run = script_dir / COOKIES_RUN_NAME
    assert run.is_file()
    assert run.read_text(encoding="utf-8") == (script_dir / COOKIES_SOURCE_NAME).read_text(
        encoding="utf-8"
    )


def test_stage_skipped_when_source_missing(tmp_path: Path) -> None:
    assert stage_cookies_for_ytdlp(str(tmp_path)) is None


def test_append_argv_adds_cookies_flag(script_dir: Path) -> None:
    argv = append_ytdlp_staged_cookies_argv(["--ignore-errors"], str(script_dir))
    assert argv == ["--ignore-errors", "--cookies", COOKIES_RUN_NAME]


def test_is_staged_cookie_path(script_dir: Path) -> None:
    run_abs = run_cookies_path(str(script_dir))
    assert is_staged_cookie_path(run_abs, str(script_dir))
    assert is_staged_cookie_path(COOKIES_RUN_NAME, str(script_dir))
    assert not is_staged_cookie_path(COOKIES_SOURCE_NAME, str(script_dir))


def test_sync_when_source_newer(tmp_path: Path) -> None:
    script_dir = str(tmp_path)
    src = tmp_path / COOKIES_SOURCE_NAME
    src.write_text(_NETSCAPE_LINE, encoding="utf-8")
    stage_cookies_for_ytdlp(script_dir)
    baseline = _file_mtime(str(src))
    assert baseline is not None

    class _FakeYdl:
        params: dict = {}
        cookiejar = None

    ydl = _FakeYdl()
    assert sync_staged_cookies_from_source_if_newer(
        ydl, script_dir, baseline_source_mtime=baseline
    ) is None

    src.write_text(
        _NETSCAPE_LINE.replace("abc", "def"),
        encoding="utf-8",
    )
    new_mtime = _file_mtime(str(src))
    assert new_mtime is not None
    assert new_mtime >= baseline

    synced = sync_staged_cookies_from_source_if_newer(
        ydl, script_dir, baseline_source_mtime=baseline
    )
    assert synced is not None
    assert ydl.cookiejar is not None
    assert (tmp_path / COOKIES_RUN_NAME).read_text(encoding="utf-8") == src.read_text(
        encoding="utf-8"
    )


def test_sentinel_roundtrip(tmp_path: Path) -> None:
    script_dir = str(tmp_path)
    assert not cookie_refresh_requested(script_dir)
    request_cookie_refresh(script_dir, reason="test")
    assert cookie_refresh_requested(script_dir)
    payload = cookie_refresh_request_payload(script_dir)
    assert payload is not None
    assert payload.get("reason") == "test"
    clear_cookie_refresh_request(script_dir)
    assert not cookie_refresh_requested(script_dir)


def test_looks_like_netscape() -> None:
    assert looks_like_netscape_cookies(_NETSCAPE_LINE)
    assert not looks_like_netscape_cookies("")
    assert not looks_like_netscape_cookies("hello world")


def test_no_stage_env(monkeypatch: pytest.MonkeyPatch, script_dir: Path) -> None:
    monkeypatch.setenv("ARCHIVE_COOKIES_NO_STAGE", "1")
    assert stage_cookies_for_ytdlp(str(script_dir)) is None
    assert not (script_dir / COOKIES_RUN_NAME).exists()
