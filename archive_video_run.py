#!/usr/bin/env python3
"""
Ad-hoc / batch video URLs driver (entry: monthly_videos_archive.bat), aligned with
archive_playlist_run and archive_channel_run:

- Same yt-dlp.conf, ManifestYoutubeDL, deferred --download-archive sync after verify
  (videos_downloaded.txt).
- Per-run logs under logs/archive_run_<UTC>/.
- Pointer: logs/latest_run_videos.txt (does not overwrite playlist or channel pointers).

Input: videos_input.txt
  - One entry per non-empty, non-# line.
  - Supported: full http(s) URL (any site yt-dlp understands), or `youtube VIDEO_ID`
    (11-char id) expanded to a watch URL.

Non-YouTube URLs download normally; **videos_downloaded.txt** sync currently persists
**youtube** archive lines the same way as playlist/channel drivers (other extractors
may not skip on rerun until archive format is extended).

Unsupported lines are logged to issues.csv and skipped.
"""

from __future__ import annotations

import os
import re
import sys
from datetime import datetime, timezone

import yt_dlp

from archive_playlist_run import (
    SCRIPT_DIR,
    ManifestYoutubeDL,
    RunReporter,
    _env_truthy,
    _info_from_hook,
    _resolve_video_id,
    _youtube_watch_url,
    videos_downloaded_path,
)
from archive_run_console import (
    emit_driver_start_banner,
    emit_final_summary,
    init_console,
    print_role,
)

_YOUTUBE_ARCHIVE_LINE = re.compile(
    r"^youtube\s+([A-Za-z0-9_-]{11})\s*$",
    re.I,
)
_URL_LINE = re.compile(r"^https?://", re.I)


def _normalize_video_line(line: str) -> str | None:
    s = line.strip()
    m = _YOUTUBE_ARCHIVE_LINE.match(s)
    if m:
        return _youtube_watch_url(m.group(1))
    if _URL_LINE.match(s):
        return s
    return None


def _video_output_base(script_dir: str) -> str:
    """Dir containing uploader subfolders; set ARCHIVE_OUT_VIDEOS to override."""
    v = os.environ.get("ARCHIVE_OUT_VIDEOS", "").strip()
    if v:
        return os.path.normpath(os.path.abspath(v))
    return os.path.join(script_dir, "videos")


def _build_argv_video(script_dir: str) -> list[str]:
    return [
        "--config-locations",
        os.path.join(script_dir, "yt-dlp.conf"),
        "--download-archive",
        videos_downloaded_path(),
        "-o",
        os.path.join(
            _video_output_base(script_dir),
            "%(uploader).100B",
            "%(title).150B - %(id)s.%(ext)s",
        ),
    ]


def _write_latest_videos_pointer(log_dir: str) -> None:
    latest_path = os.path.join(SCRIPT_DIR, "logs", "latest_run_videos.txt")
    try:
        with open(latest_path, "w", encoding="utf-8") as lf:
            lf.write(log_dir + "\n")
    except OSError:
        pass


def main() -> int:
    os.chdir(SCRIPT_DIR)
    init_console()
    log_stamp = sys.argv[1] if len(sys.argv) > 1 else None
    if not log_stamp:
        log_stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    log_dir = os.path.join(SCRIPT_DIR, "logs", f"archive_run_{log_stamp}")
    reporter = RunReporter(
        log_dir,
        archive_path=videos_downloaded_path(),
        summary_heading="Archive video run summary (UTC)",
        archive_sync_log_prefix="[archive_video_run]",
    )
    emit_driver_start_banner(
        reporter,
        title="Archive video run (videos_input.txt)",
        subtitle="Batch URLs or youtube VIDEO_ID lines; deferred archive sync after verification",
    )

    videos_file = os.path.join(SCRIPT_DIR, "videos_input.txt")
    urls: list[str] = []
    nonempty_lines = 0
    if os.path.isfile(videos_file):
        with open(videos_file, encoding="utf-8", errors="replace") as f:
            for line_no, ln in enumerate(f, start=1):
                s = ln.strip()
                if not s or s.startswith("#"):
                    continue
                nonempty_lines += 1
                norm = _normalize_video_line(s)
                if norm:
                    urls.append(norm)
                else:
                    reporter.record_issue(
                        "error",
                        "",
                        "",
                        "",
                        f"videos_input.txt line {line_no}: use http(s) URL or "
                        f"'youtube VIDEO_ID' (11 chars). Raw: {s!r}",
                        "",
                    )

    if nonempty_lines == 0:
        reporter.record_issue(
            "fatal",
            "",
            "",
            "",
            f"No URLs in {videos_file} (add non-empty lines; # starts comments).",
            "",
        )
        reporter.close()
        reporter.finalize()
        _write_latest_videos_pointer(log_dir)
        emit_final_summary(
            log_dir=log_dir,
            log_stamp=log_stamp,
            report_path=reporter.report_path,
            rc=1,
            driver_label="archive_video_run",
            pointer_lines=["Video list pointer: logs\\latest_run_videos.txt"],
        )
        return 1

    if not urls:
        reporter.record_issue(
            "fatal",
            "",
            "",
            "",
            f"No valid URLs after parsing {videos_file}; fix or remove bad lines.",
            "",
        )
        reporter.close()
        reporter.finalize()
        _write_latest_videos_pointer(log_dir)
        emit_final_summary(
            log_dir=log_dir,
            log_stamp=log_stamp,
            report_path=reporter.report_path,
            rc=1,
            driver_label="archive_video_run",
            pointer_lines=["Video list pointer: logs\\latest_run_videos.txt"],
        )
        return 1

    reporter.log_line(
        f"[archive_video_run] videos_input.txt: {nonempty_lines} non-comment line(s) -> "
        f"{len(urls)} URL(s) for yt-dlp."
    )

    argv = list(_build_argv_video(SCRIPT_DIR))
    if _env_truthy("ARCHIVE_DRY_RUN"):
        argv.append("--simulate")
        reporter.log_line(
            "[archive_video_run] ARCHIVE_DRY_RUN=1: passing --simulate to yt-dlp."
        )
        print_role(
            "[archive] ARCHIVE_DRY_RUN=1: yt-dlp --simulate (no writes to disk/archive)",
            "warn",
        )

    full_argv = argv + urls
    try:
        po = yt_dlp.parse_options(full_argv)
    except SystemExit as e:
        reporter.record_issue("fatal", "", "", "", f"parse_options failed: {e}", "")
        reporter.close()
        reporter.finalize()
        _write_latest_videos_pointer(log_dir)
        rc_pe = int(e.code) if isinstance(e.code, int) else 1
        emit_final_summary(
            log_dir=log_dir,
            log_stamp=log_stamp,
            report_path=reporter.report_path,
            rc=rc_pe,
            driver_label="archive_video_run",
            pointer_lines=["Video list pointer: logs\\latest_run_videos.txt"],
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
                    "",
                )
                rc = 1
            else:
                rc = ydl._download_retcode
    except KeyboardInterrupt:
        reporter.record_issue("interrupted", "", "", "", "KeyboardInterrupt", "")
        rc = 1
    except Exception as e:
        reporter.record_issue("exception", "", "", "", repr(e), "")
        rc = 1
    finally:
        reporter.close()
        reporter.finalize()
        _write_latest_videos_pointer(log_dir)

    emit_final_summary(
        log_dir=log_dir,
        log_stamp=log_stamp,
        report_path=reporter.report_path,
        rc=rc,
        driver_label="archive_video_run",
        pointer_lines=["Video list pointer: logs\\latest_run_videos.txt"],
    )
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
