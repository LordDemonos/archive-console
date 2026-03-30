#!/usr/bin/env python3
"""
Single-URL one-off driver (Archive Console). Same stack as archive_video_run:
RunReporter, ManifestYoutubeDL, deferred archive sync, per-run logs under
logs/archive_run_<UTC>/.

Input: URL from env ARCHIVE_ONEOFF_URL (YouTube watch / shorts / youtu.be or
youtube VIDEO_ID). Output root: ARCHIVE_OUT_ONEOFF (set by console).

Rolling summary: logs/oneoff_report/ (see archive_oneoff_rolling.py).
Archive file: oneoff_downloaded.txt (isolated from monthly list archives).
"""

from __future__ import annotations

import csv
import os
import re
import sys
from datetime import datetime, timezone

import yt_dlp

import archive_oneoff_rolling as rolling
from archive_playlist_run import (
    SCRIPT_DIR,
    ManifestYoutubeDL,
    RunReporter,
    _env_truthy,
    _info_from_hook,
    _resolve_video_id,
)
from archive_run_console import (
    emit_driver_start_banner,
    emit_final_summary,
    init_console,
    print_role,
)
from archive_video_run import _build_argv_video, _normalize_video_line

_YT_LINE = re.compile(
    r"^https?://(www\.)?(youtube\.com|youtu\.be)/",
    re.I,
)


def oneoff_downloaded_path() -> str:
    return os.path.join(SCRIPT_DIR, "oneoff_downloaded.txt")


def _youtube_only_url(raw: str) -> str | None:
    """Normalize to a single URL; reject non-YouTube http URLs."""
    s = raw.strip()
    if not s:
        return None
    norm = _normalize_video_line(s)
    if not norm:
        return None
    if _YT_LINE.match(norm) or norm.startswith("https://youtu.be/"):
        return norm
    return None


def _oneoff_output_base(script_dir: str) -> str:
    v = os.environ.get("ARCHIVE_OUT_ONEOFF", "").strip()
    if v:
        return os.path.normpath(os.path.abspath(v))
    return os.path.join(script_dir, "oneoff")


def _build_argv_oneoff(script_dir: str) -> list[str]:
    """Same argv shape as video batch but archive + output for one-off."""
    return [
        "--config-locations",
        os.path.join(script_dir, "yt-dlp.conf"),
        "--download-archive",
        oneoff_downloaded_path(),
        "-o",
        os.path.join(
            _oneoff_output_base(script_dir),
            "%(uploader).100B",
            "%(title).150B - %(id)s.%(ext)s",
        ),
    ]


def _write_latest_oneoff_pointer(log_dir: str) -> None:
    latest_path = os.path.join(SCRIPT_DIR, "logs", "latest_run_oneoff.txt")
    try:
        with open(latest_path, "w", encoding="utf-8") as lf:
            lf.write(log_dir + "\n")
    except OSError:
        pass


def _read_manifest_after_run(manifest_path: str) -> tuple[dict[str, str] | None, list[dict[str, str]]]:
    if not os.path.isfile(manifest_path):
        return None, []
    rows: list[dict[str, str]] = []
    try:
        with open(manifest_path, encoding="utf-8", errors="replace") as f:
            r = csv.DictReader(f)
            for row in r:
                rows.append(dict(row))
    except OSError:
        return None, []
    ok_rows = [
        x
        for x in rows
        if (x.get("status") or "").startswith("downloaded")
        and (x.get("file_verified_ok") or "") == "yes"
    ]
    best = ok_rows[-1] if ok_rows else (rows[-1] if rows else None)
    return best, rows


def _first_issue_reason(issues_path: str) -> str:
    if not os.path.isfile(issues_path):
        return ""
    try:
        with open(issues_path, encoding="utf-8", errors="replace") as f:
            r = csv.DictReader(f)
            for row in r:
                return (row.get("reason") or "").strip()
    except OSError:
        pass
    return ""


def main() -> int:
    os.chdir(SCRIPT_DIR)
    init_console()
    url_env = (os.environ.get("ARCHIVE_ONEOFF_URL") or "").strip()
    retention = int(os.environ.get("ARCHIVE_ONEOFF_RETENTION_DAYS") or "90")

    rolling.rotate_if_needed(SCRIPT_DIR, retention)

    log_stamp = sys.argv[1] if len(sys.argv) > 1 else None
    if not log_stamp:
        log_stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    log_dir = os.path.join(SCRIPT_DIR, "logs", f"archive_run_{log_stamp}")
    reporter = RunReporter(
        log_dir,
        archive_path=oneoff_downloaded_path(),
        summary_heading="Archive one-off run summary (UTC)",
        archive_sync_log_prefix="[archive_oneoff_run]",
    )
    emit_driver_start_banner(
        reporter,
        title="Archive one-off (single URL)",
        subtitle="Console-driven; rolling report under logs/oneoff_report/",
    )

    url = _youtube_only_url(url_env)
    if not url:
        reporter.record_issue(
            "fatal",
            "",
            "",
            "",
            "ARCHIVE_ONEOFF_URL must be a non-empty YouTube URL (watch, shorts, youtu.be) "
            "or 'youtube VIDEO_ID' (11 chars).",
            "",
        )
        reporter.close()
        reporter.finalize()
        _write_latest_oneoff_pointer(log_dir)
        emit_final_summary(
            log_dir=log_dir,
            log_stamp=log_stamp,
            report_path=reporter.report_path,
            rc=1,
            driver_label="archive_oneoff_run",
            pointer_lines=["One-off pointer: logs\\latest_run_oneoff.txt"],
        )
        return 1

    reporter.log_line(f"[archive_oneoff_run] URL: {url}")

    argv = list(_build_argv_oneoff(SCRIPT_DIR))
    if _env_truthy("ARCHIVE_DRY_RUN"):
        argv.append("--simulate")
        reporter.log_line("[archive_oneoff_run] ARCHIVE_DRY_RUN=1: passing --simulate to yt-dlp.")
        print_role(
            "[archive] ARCHIVE_DRY_RUN=1: yt-dlp --simulate (no writes to disk/archive)",
            "warn",
        )

    full_argv = argv + [url]
    try:
        po = yt_dlp.parse_options(full_argv)
    except SystemExit as e:
        reporter.record_issue("fatal", "", "", "", f"parse_options failed: {e}", url)
        reporter.close()
        reporter.finalize()
        _write_latest_oneoff_pointer(log_dir)
        rc_pe = int(e.code) if isinstance(e.code, int) else 1
        emit_final_summary(
            log_dir=log_dir,
            log_stamp=log_stamp,
            report_path=reporter.report_path,
            rc=rc_pe,
            driver_label="archive_oneoff_run",
            pointer_lines=["One-off pointer: logs\\latest_run_oneoff.txt"],
        )
        return rc_pe

    ydl_opts = dict(po.ydl_opts)

    def progress_hook(d: dict):
        if d.get("status") != "finished":
            return
        info, path = _info_from_hook(d)
        vid = _resolve_video_id(info, path)
        if not path or not vid:
            return
        title = str(info.get("title") or "")
        playlist_id = str(info.get("playlist_id") or "")
        webpage = str(info.get("webpage_url") or info.get("original_url") or "")
        extractor = str(info.get("extractor") or info.get("ie_key") or "")
        size = d.get("total_bytes") or d.get("downloaded_bytes")
        if size is None:
            size = info.get("filesize") or info.get("filesize_approx")
        try:
            sz = int(size) if size is not None else -1
        except (TypeError, ValueError):
            sz = -1
        reporter.record_manifest_row(
            vid, title, path, sz, playlist_id, webpage, extractor
        )

    def postprocessor_hook(d: dict):
        if d.get("status") != "finished":
            return
        info = d.get("info_dict") or {}
        path = info.get("filepath") or info.get("_filename")
        vid = _resolve_video_id(info, path)
        if not path or not vid:
            return
        title = str(info.get("title") or "")
        playlist_id = str(info.get("playlist_id") or "")
        webpage = str(info.get("webpage_url") or "")
        extractor = str(info.get("extractor") or info.get("ie_key") or "")
        reporter.record_manifest_row(
            vid, title, path, -1, playlist_id, webpage, extractor
        )

    ydl_opts["progress_hooks"] = list(ydl_opts.get("progress_hooks") or []) + [
        progress_hook
    ]
    ydl_opts["postprocessor_hooks"] = list(
        ydl_opts.get("postprocessor_hooks") or []
    ) + [postprocessor_hook]

    rc = 0
    try:
        with ManifestYoutubeDL(ydl_opts, reporter) as ydl:
            try:
                ydl.download(po.urls)
            except yt_dlp.utils.DownloadCancelled as e:
                reporter.record_issue(
                    "cancelled",
                    "",
                    "",
                    "",
                    type(e).__name__ + ": " + str(e),
                    url,
                )
                rc = 1
            else:
                rc = ydl._download_retcode
    except KeyboardInterrupt:
        reporter.record_issue("interrupted", "", "", "", "KeyboardInterrupt", url)
        rc = 1
    except Exception as e:
        reporter.record_issue("exception", "", "", "", repr(e), url)
        rc = 1
    finally:
        reporter.close()
        reporter.finalize()
        _write_latest_oneoff_pointer(log_dir)

    emit_final_summary(
        log_dir=log_dir,
        log_stamp=log_stamp,
        report_path=reporter.report_path,
        rc=rc,
        driver_label="archive_oneoff_run",
        pointer_lines=["One-off pointer: logs\\latest_run_oneoff.txt"],
    )

    completed_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    log_rel = os.path.relpath(log_dir, SCRIPT_DIR).replace("\\", "/")
    best, _allm = _read_manifest_after_run(
        os.path.join(log_dir, "manifest.csv"),
    )
    err = _first_issue_reason(os.path.join(log_dir, "issues.csv"))
    outcome = "fail"
    if rc == 0 and best and (best.get("file_verified_ok") or "") == "yes":
        outcome = "ok"
    elif rc == 0 and best:
        outcome = "ok"
    entry = {
        "completed_utc": completed_utc,
        "url": url,
        "outcome": outcome,
        "exit_code": rc,
        "bytes": best.get("file_size_bytes", "") if best else "",
        "media_path": best.get("filepath", "") if best else "",
        "error_snippet": (err[:500] if err else ""),
        "log_folder": log_rel,
        "video_id": (best or {}).get("video_id", ""),
    }
    try:
        rolling.append_entry(SCRIPT_DIR, entry)
    except OSError as e:
        print_role(f"[archive_oneoff_run] rolling report append failed: {e}", "warn")

    return rc


if __name__ == "__main__":
    raise SystemExit(main())
