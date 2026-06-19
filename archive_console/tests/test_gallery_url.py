"""Gallery URL normalization and gallery-dl CLI wiring."""

from __future__ import annotations

from pathlib import Path

from app.gallery_util import normalize_gallery_url


def test_normalize_reddit_user_adds_submitted() -> None:
    u = normalize_gallery_url("https://old.reddit.com/user/miss_rachelann")
    assert u == "https://www.reddit.com/user/miss_rachelann/submitted/"


def test_normalize_reddit_user_keeps_submitted() -> None:
    u = normalize_gallery_url("https://www.reddit.com/user/foo/submitted/")
    assert u.rstrip("/") == "https://www.reddit.com/user/foo/submitted"


def test_normalize_reddit_subreddit() -> None:
    u = normalize_gallery_url("old.reddit.com/r/pics/")
    assert u.rstrip("/") == "https://www.reddit.com/r/pics"


def test_archive_gallery_run_uses_d_destination_flag() -> None:
    """gallery-dl -o is --option KEY=VALUE; destination must be -d."""
    src = (
        Path(__file__).resolve().parent.parent.parent / "archive_gallery_run.py"
    ).read_text(encoding="utf-8")
    assert 'cmd.extend(["-d", dest_dir])' in src
    assert 'cmd.extend(["-o", dest_dir])' not in src


def test_archive_gallery_run_tees_driver_log_to_stdout_when_unattended(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    import sys

    root = Path(__file__).resolve().parent.parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    from archive_gallery_run import _driver_log
    from archive_playlist_run import RunReporter

    log_dir = tmp_path / "log"
    log_dir.mkdir()
    reporter = RunReporter(log_dir, skip_download_archive_sync=True)

    monkeypatch.delenv("ARCHIVE_CONSOLE_UNATTENDED", raising=False)
    _driver_log(reporter, "line-a")
    assert capsys.readouterr().out == ""

    monkeypatch.setenv("ARCHIVE_CONSOLE_UNATTENDED", "1")
    _driver_log(reporter, "line-b")
    assert capsys.readouterr().out == "line-b\n"

    _driver_log(reporter, "arrow \u2192 test")
    captured = capsys.readouterr().out
    assert "\u2192" in captured or "->" in captured or "test" in captured

    assert "line-a" in (log_dir / "run.log").read_text(encoding="utf-8")
    assert "line-b" in (log_dir / "run.log").read_text(encoding="utf-8")


def test_archive_gallery_run_sanitize_reddit_error_wall() -> None:
    import sys

    root = Path(__file__).resolve().parent.parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    from archive_gallery_run import _sanitize_gallery_dl_line

    wall = ".theme-light,:root{--x:1}" + ("y" * 3000)
    wall += " You've been blocked by network security."
    out = _sanitize_gallery_dl_line(f"[reddit][error] {wall}")
    assert len(out) < 800
    assert "block" in out.lower()


def test_console_print_unicode_on_cp1252_stdout(monkeypatch) -> None:
    import io
    import sys

    root = Path(__file__).resolve().parent.parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    from archive_gallery_run import _console_print

    buf = io.BytesIO()

    class _FakeStdout:
        buffer = buf
        encoding = "cp1252"

    monkeypatch.setattr(sys, "stdout", _FakeStdout())
    _console_print("Reddit \u2192 reddit_user_test")
    out = buf.getvalue().decode("utf-8")
    assert "Reddit" in out
    assert "\u2192" in out
