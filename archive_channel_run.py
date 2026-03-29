#!/usr/bin/env python3
"""
Full channel archive driver (batch entry: monthly_channels_archive.bat), aligned with
archive_playlist_run / monthly_watch_later_archive.bat:

- Same yt-dlp.conf, cookies, EJS (--js-runtimes from config), deferred --download-archive
  sync only after on-disk verification (channels_downloaded.txt).
- Per-run logs under logs/archive_run_<UTC>/ (manifest.csv, issues.csv, summary.txt,
  report.html, rerun_urls.txt, run.log).
- Separate pointer: logs/latest_run_channel.txt (does not overwrite latest_run.txt).

Bare channel home URLs (e.g. https://www.youtube.com/@name with no /videos tab) are
expanded to /videos and /shorts by default so long-form and Shorts are both queued;
set ARCHIVE_CHANNEL_EXPAND_TABS=0 to pass URLs through unchanged.

Input: channels_input.txt (one URL per line, # comments allowed).
Output template matches legacy channel bats: channels/<uploader>.100B/...
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from typing import Iterable
from urllib.parse import urlparse, urlunparse

import yt_dlp

from archive_playlist_run import (
    SCRIPT_DIR,
    ManifestYoutubeDL,
    RunReporter,
    _env_truthy,
    _info_from_hook,
    _resolve_video_id,
    channels_downloaded_path,
)
from archive_run_console import (
    emit_driver_start_banner,
    emit_final_summary,
    init_console,
    print_role,
)

_TAB_LAST = frozenset(
    {
        "videos",
        "shorts",
        "streams",
        "playlists",
        "featured",
        "community",
        "live",
        "about",
        "store",
        "channels",
    }
)

_ALLOWED_NETLOCS = frozenset(
    {"www.youtube.com", "youtube.com", "m.youtube.com"}
)


def _read_channels_input(path: str) -> list[str]:
    if not os.path.isfile(path):
        return []
    out: list[str] = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for ln in f:
            s = ln.strip()
            if not s or s.startswith("#"):
                continue
            out.append(s)
    return out


def _expand_one_channel_url(u: str) -> list[str]:
    u = u.strip()
    if not u:
        return []
    try:
        parsed = urlparse(u)
    except Exception:
        return [u]
    net = (parsed.netloc or "").lower()
    if net not in _ALLOWED_NETLOCS:
        return [u]
    parts = [p for p in (parsed.path or "").split("/") if p]
    if not parts:
        return [u]
    if parts[-1].lower() in _TAB_LAST:
        return [u]
    path_v = "/" + "/".join(parts) + "/videos"
    path_s = "/" + "/".join(parts) + "/shorts"
    q = parsed.query
    frag = parsed.fragment
    scheme = parsed.scheme or "https"
    v = urlunparse((scheme, parsed.netloc, path_v, "", q, frag))
    s = urlunparse((scheme, parsed.netloc, path_s, "", q, frag))
    return [v, s]


def expand_channel_input_urls(urls: Iterable[str], *, enabled: bool) -> list[str]:
    if not enabled:
        return list(urls)
    out: list[str] = []
    for u in urls:
        out.extend(_expand_one_channel_url(u))
    return out


def _channel_output_base(script_dir: str) -> str:
    """Dir containing uploader subfolders; set ARCHIVE_OUT_CHANNEL to override."""
    v = os.environ.get("ARCHIVE_OUT_CHANNEL", "").strip()
    if v:
        return os.path.normpath(os.path.abspath(v))
    return os.path.join(script_dir, "channels")


def _channel_expand_tabs_enabled() -> bool:
    v = os.environ.get("ARCHIVE_CHANNEL_EXPAND_TABS", "").strip().lower()
    if v in ("0", "false", "no", "off"):
        return False
    return True


def _build_argv_channel(script_dir: str) -> list[str]:
    return [
        "--config-locations",
        os.path.join(script_dir, "yt-dlp.conf"),
        "--download-archive",
        channels_downloaded_path(),
        "-o",
        os.path.join(
            _channel_output_base(script_dir),
            "%(uploader).100B",
            "%(upload_date)s - %(title).150B - %(id)s.%(ext)s",
        ),
    ]


def _write_latest_channel_pointer(log_dir: str) -> None:
    latest_path = os.path.join(SCRIPT_DIR, "logs", "latest_run_channel.txt")
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
        archive_path=channels_downloaded_path(),
        summary_heading="Archive channel run summary (UTC)",
        archive_sync_log_prefix="[archive_channel_run]",
    )
    emit_driver_start_banner(
        reporter,
        title="Archive channel run (channels_input.txt)",
        subtitle="Bare channel URLs expand to /videos + /shorts unless ARCHIVE_CHANNEL_EXPAND_TABS=0",
    )

    channels_file = os.path.join(SCRIPT_DIR, "channels_input.txt")
    raw_urls = _read_channels_input(channels_file)
    if not raw_urls:
        reporter.record_issue(
            "fatal",
            "",
            "",
            "",
            f"No URLs in {channels_file} (add non-empty lines; # starts comments).",
            "",
        )
        reporter.close()
        reporter.finalize()
        _write_latest_channel_pointer(log_dir)
        emit_final_summary(
            log_dir=log_dir,
            log_stamp=log_stamp,
            report_path=reporter.report_path,
            rc=1,
            driver_label="archive_channel_run",
            pointer_lines=["Channel pointer: logs\\latest_run_channel.txt"],
        )
        return 1

    expand_on = _channel_expand_tabs_enabled()
    urls = expand_channel_input_urls(raw_urls, enabled=expand_on)
    reporter.log_line(
        f"[archive_channel_run] channels_input.txt: {len(raw_urls)} line(s) -> "
        f"{len(urls)} URL(s) for yt-dlp "
        f"(ARCHIVE_CHANNEL_EXPAND_TABS={'on' if expand_on else 'off'})."
    )

    argv = list(_build_argv_channel(SCRIPT_DIR))
    if _env_truthy("ARCHIVE_DRY_RUN"):
        argv.append("--simulate")
        reporter.log_line(
            "[archive_channel_run] ARCHIVE_DRY_RUN=1: passing --simulate to yt-dlp."
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
        _write_latest_channel_pointer(log_dir)
        rc_pe = int(e.code) if isinstance(e.code, int) else 1
        emit_final_summary(
            log_dir=log_dir,
            log_stamp=log_stamp,
            report_path=reporter.report_path,
            rc=rc_pe,
            driver_label="archive_channel_run",
            pointer_lines=["Channel pointer: logs\\latest_run_channel.txt"],
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
        _write_latest_channel_pointer(log_dir)

    emit_final_summary(
        log_dir=log_dir,
        log_stamp=log_stamp,
        report_path=reporter.report_path,
        rc=rc,
        driver_label="archive_channel_run",
        pointer_lines=["Channel run pointer: logs\\latest_run_channel.txt"],
    )
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
