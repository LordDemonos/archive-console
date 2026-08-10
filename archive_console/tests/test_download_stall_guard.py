"""Tests for archive_playlist_run subprocess stall watchdog."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from unittest import mock

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from archive_playlist_run import (  # noqa: E402
    ARCHIVE_DOWNLOAD_STALL_SEC_ENV,
    STALL_EXIT_CODE,
    SubprocessStallGuard,
    RunReporter,
    UrlRunResult,
    _ActiveDownloadTracker,
    _cleanup_stall_partials,
    _terminate_process_tree,
)


@pytest.fixture
def reporter() -> RunReporter:
    d = tempfile.mkdtemp()
    rep = RunReporter(d)
    yield rep
    rep.close()


def test_stall_guard_disabled_when_env_zero(
    reporter: RunReporter, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(ARCHIVE_DOWNLOAD_STALL_SEC_ENV, "0")
    guard = SubprocessStallGuard(reporter)
    assert guard._enabled is False


def test_active_download_tracker_destination_and_reset() -> None:
    tracker = _ActiveDownloadTracker()
    tracker.on_stdout_line(
        "[download] Destination: E:\\videos\\2020 - Example - AbCdEf12345.mp4"
    )
    assert tracker.is_active()
    assert tracker.current_video_id() == "AbCdEf12345"
    tracker.on_stdout_line("[download] Downloading item 16 of 100")
    assert not tracker.is_active()


def test_active_download_tracker_heartbeat(reporter: RunReporter) -> None:
    tracker = _ActiveDownloadTracker()
    tracker.on_stdout_line("[download] Destination: /tmp/foo - vid123456789.mp4")
    tracker._last_progress_mono = time.monotonic() - 45.0
    tracker.maybe_log_heartbeat(reporter, heartbeat_sec=30.0)
    text = open(reporter.run_log_path, encoding="utf-8").read()
    assert "still downloading" in text


def test_cleanup_stall_partials_removes_part_files(tmp_path) -> None:
    base = tmp_path / "sample - AbCdEf12345.mp4"
    part = base.with_suffix(base.suffix + ".part")
    ytdl = base.with_suffix(base.suffix + ".ytdl")
    part.write_bytes(b"partial")
    ytdl.write_text("{}", encoding="utf-8")
    _cleanup_stall_partials(str(base))
    assert not part.exists()
    assert not ytdl.exists()


def test_subprocess_stall_guard_kills_worker_on_stall(
    reporter: RunReporter, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(ARCHIVE_DOWNLOAD_STALL_SEC_ENV, "0.05")
    monkeypatch.setenv("ARCHIVE_DOWNLOAD_STALL_HEARTBEAT_SEC", "0.02")

    class FakeProc:
        pid = 99999
        returncode = 0

        def __init__(self) -> None:
            self.stdout = mock.Mock()

        def poll(self):
            return None

        def wait(self, timeout=None):
            return 0

    fake = FakeProc()
    lines = [
        "[download] Destination: E:\\out\\2020 - Clip - StallVid1234A.mp4\n",
    ]

    def fake_popen(*_a, **_k):
        return fake

    def fake_pump(_pipe, out_q):
        for line in lines:
            out_q.put(line)
        time.sleep(0.2)
        out_q.put(None)

    monkeypatch.setattr("archive_playlist_run.subprocess.Popen", fake_popen)
    monkeypatch.setattr("archive_playlist_run._pump_subprocess_stdout", fake_pump)
    terminate = mock.Mock()
    monkeypatch.setattr("archive_playlist_run._terminate_process_tree", terminate)

    guard = SubprocessStallGuard(reporter)
    result = guard.run_url("https://example.com/playlist", reporter.log_dir, dry_run=True)

    assert result.stalled is True
    assert result.exit_code == STALL_EXIT_CODE
    assert result.stalled_media_path is not None
    assert "StallVid1234A" in result.stalled_media_path
    terminate.assert_called()
    log = open(reporter.run_log_path, encoding="utf-8").read()
    assert "[WATCHDOG] Skipping item" in log
    assert "due to stall" in log


def test_merge_worker_snapshot(reporter: RunReporter, tmp_path) -> None:
    snap = tmp_path / "worker.json"
    snap.write_text(
        '{"manifest":[{"video_id":"abc12345678","title":"t","filepath":"x","file_size_bytes":"1","status":"downloaded","reason":"r","timestamp_utc":"u","playlist_id":"","webpage_url":""}],"issues":[],"rerun_urls":[]}',
        encoding="utf-8",
    )
    reporter.merge_worker_snapshot(str(snap))
    assert len(reporter._manifest_rows) == 1
    assert reporter._manifest_rows[0]["video_id"] == "abc12345678"
    assert not snap.exists()


def test_worker_stdout_unicode_arrow(reporter: RunReporter) -> None:
    import io

    rep = RunReporter(reporter.log_dir, worker_mode=True)
    buf = io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict")
    with mock.patch.object(sys, "stdout", buf):
        rep.log_line(
            "[archive] Staged cookies for yt-dlp: cookies.txt → cookies.run.txt"
        )
    rep.close()


def test_ytdlp_conf_includes_socket_timeout_and_skip_fragments() -> None:
    conf_path = os.path.join(ROOT, "yt-dlp.conf")
    text = open(conf_path, encoding="utf-8").read()
    assert "--socket-timeout 30" in text
    assert "--skip-unavailable-fragments" in text
