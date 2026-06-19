"""archive_console_errors.json sidecar + report HTML injection."""

from __future__ import annotations

from pathlib import Path

from app.report_html_rewrite import rewrite_report_html
from app.run_error_record import (
    ERRORS_JSON_BASENAME,
    append_errors_to_log_folder,
    make_error_record,
    read_errors_for_log_folder,
)


def test_append_and_read_errors_roundtrip(tmp_path: Path) -> None:
    root = tmp_path / "ar"
    root.mkdir()
    log_rel = "logs/run_a"
    folder = root / log_rel
    folder.mkdir(parents=True)
    rec = make_error_record(
        stage="yt-dlp",
        operation="download_run_complete",
        message="test failure",
        run_id="abc123",
        technical={"exit_code": 1},
    )
    append_errors_to_log_folder(
        root,
        log_rel,
        ["logs"],
        [rec],
    )
    sidecar = folder / ERRORS_JSON_BASENAME
    assert sidecar.is_file()
    loaded = read_errors_for_log_folder(root, log_rel, ["logs"])
    assert len(loaded) == 1
    assert loaded[0]["stage"] == "yt-dlp"
    assert loaded[0]["run_id"] == "abc123"


def test_rewrite_report_injects_errors_section(tmp_path: Path) -> None:
    root = tmp_path / "ar"
    root.mkdir()
    report = root / "logs" / "r" / "report.html"
    report.parent.mkdir(parents=True)
    report.write_text(
        "<!DOCTYPE html><html><head></head><body><p>ok</p></body></html>",
        encoding="utf-8",
    )
    append_errors_to_log_folder(
        root,
        "logs/r",
        ["logs"],
        [
            make_error_record(
                stage="metadata",
                operation="files_mediainfo",
                message="timeout",
                severity="error",
            )
        ],
    )
    html_in = report.read_text(encoding="utf-8")
    out = rewrite_report_html(
        html_in,
        root,
        ["logs"],
        report_path=report,
    )
    assert "archive-console-errors" in out
    assert "Archive Console — Errors" in out
    assert "files_mediainfo" in out


def test_rewrite_report_empty_errors_still_has_section(tmp_path: Path) -> None:
    root = tmp_path / "ar"
    root.mkdir()
    report = root / "logs" / "r2" / "report.html"
    report.parent.mkdir(parents=True)
    report.write_text(
        "<html><body></body></html>",
        encoding="utf-8",
    )
    out = rewrite_report_html(
        report.read_text(encoding="utf-8"),
        root,
        ["logs"],
        report_path=report,
    )
    assert "No errors recorded for this run" in out
