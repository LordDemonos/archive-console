#!/usr/bin/env python3
"""
Run yt-dlp for monthly_watch_later_archive.bat (playlist batch) with per-run manifest, issues, summary, and HTML report.

Uses the same argv/config as the batch file, adds hooks and a YoutubeDL subclass
to record downloads and skips/failures. Writes manifest.csv + issues.csv + summary.txt + report.html.
"""

from __future__ import annotations

import csv
import html
import json
import os
import pathlib
import re
import sys
import time
from datetime import datetime, timezone
from typing import Any

import yt_dlp
from yt_dlp import YoutubeDL

from archive_run_console import (
    augment_ytdlp_console_message,
    color_enabled,
    emit_driver_start_banner,
    emit_final_summary,
    init_console,
    print_role,
)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _playlist_output_base(script_dir: str) -> str:
    """Dir containing playlist-id subfolders; set ARCHIVE_OUT_PLAYLIST to override (e.g. Archive Console)."""
    v = os.environ.get("ARCHIVE_OUT_PLAYLIST", "").strip()
    if v:
        return os.path.normpath(os.path.abspath(v))
    return os.path.join(script_dir, "playlists")

ARCHIVE_SKIP_RE = re.compile(
    r"^\[download\]\s+([^:\s]+):\s*(.+?)\s+has already been recorded in the archive\s*$"
)

ID_FROM_FILENAME_RE = re.compile(r" - ([A-Za-z0-9_-]{11})\.[^.\\/]+$")

PRIVATE_UNAVAILABLE_RE = re.compile(
    r"private|unavailable|removed|no longer available|copyright|blocked|not found",
    re.I,
)

_REMEDIATION_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"playlist does not exist|WL:", re.I),
        "Watch Later / auth: refresh cookies.txt or use --cookies-from-browser in yt-dlp.conf; "
        "or put a normal private playlist URL in playlists_input.txt.",
    ),
    (
        re.compile(
            r"Requested format is not available|Only images are available|format is not available",
            re.I,
        ),
        "Formats/EJS: yt-dlp.conf needs --js-runtimes node + pip install -U \"yt-dlp[default]\" "
        "(yt-dlp-ejs); keep player_client=tv,web_safari,mweb. See EJS wiki + ARCHIVE_PLAYLIST_RUN_LOGS.txt.",
    ),
    (
        re.compile(r"challenge solving failed|\bn challenge\b|EJS|SABR", re.I),
        "YouTube n challenge: Node 20+ on PATH, --js-runtimes node in yt-dlp.conf, "
        "pip \"yt-dlp[default]\" for yt-dlp-ejs — https://github.com/yt-dlp/yt-dlp/wiki/EJS",
    ),
    (
        re.compile(r"429|Too Many Requests|rate[- ]?limit", re.I),
        "Rate limit: increase sleeps in yt-dlp.conf; wait and rerun (archive skips completed IDs).",
    ),
    (
        re.compile(
            r"removed by the uploader|account has been terminated|Video unavailable|"
            r"no longer available because",
            re.I,
        ),
        "Expected: video or channel gone; no config fix—remove from playlist or ignore.",
    ),
    (
        re.compile(r"merge|ffmpeg|Post-?process|mux", re.I),
        "Mux: ensure ffmpeg is on PATH; see --merge-output-format mkv in yt-dlp.conf.",
    ),
    (
        re.compile(r"Sign in to confirm|not a bot|cookies", re.I),
        "Auth: refresh cookies or --cookies-from-browser; confirm account can play the video in a browser.",
    ),
)


def suggest_remediation(reason: str) -> str:
    r = reason or ""
    for pat, hint in _REMEDIATION_RULES:
        if pat.search(r):
            return hint
    return (
        "See ARCHIVE_PLAYLIST_RUN_LOGS.txt (monthly checklist + failure notes) and comments in "
        "yt-dlp.conf; full lines in run.log."
    )


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


# Pause when yt-dlp stderr/error lines match these (narrow; see ARCHIVE_PLAYLIST_RUN_LOGS.txt).
ARCHIVE_PAUSE_ON_COOKIE_ERROR_ENV = "ARCHIVE_PAUSE_ON_COOKIE_ERROR"

# Optional: poll this file's mtime every N seconds until it increases (non-interactive / Task Scheduler).
ARCHIVE_COOKIE_AUTH_POLL_SEC_ENV = "ARCHIVE_COOKIE_AUTH_POLL_SEC"
ARCHIVE_COOKIE_AUTH_POLL_MAX_SEC_ENV = "ARCHIVE_COOKIE_AUTH_POLL_MAX_SEC"

# yt-dlp / YouTube strings that strongly suggest cookies or login session — not bare HTTP 403.
COOKIE_AUTH_LINE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"sign\s+in\s+to\s+confirm", re.I),
    re.compile(r"not\s+a\s+bot", re.I),
    re.compile(r"cookie\s*load\s*error", re.I),
    re.compile(r"could\s+not\s+copy\s+.{0,80}cookie", re.I),
    re.compile(
        r"cookies?\s+(?:file|database).{0,80}(?:invalid|missing|not\s+found|could\s+not)",
        re.I,
    ),
    re.compile(r"authentication\s+(?:failed|required|error)", re.I),
    re.compile(r"login\s+required", re.I),
    re.compile(r"(?:unable\s+to\s+)?log\s+in", re.I),
    re.compile(r"account\s+.{0,40}(?:needed|required)\s+to\s+view", re.I),
    re.compile(r"refresh\s+your\s+cookies", re.I),
    # 403 only when auth-related tokens appear nearby on the same line
    re.compile(r"403(?:\s|$).{0,120}(?:cookie|login|sign\s*in|consent|bot|challenge)", re.I),
    re.compile(r"(?:cookie|login|sign\s*in|consent|bot|challenge).{0,120}403", re.I),
)


def looks_like_likely_cookie_auth_error(text: str) -> bool:
    """
    Heuristic: True if this log line likely indicates cookie/session/login, not format/geo alone.

    False-positive risks: member-only / age-gate wording that mentions login; rare 403 lines that
    mention \"bot\" for non-auth reasons. We intentionally do *not* treat generic \"403 Forbidden\".
    """
    if not (text or "").strip():
        return False
    return any(p.search(text) for p in COOKIE_AUTH_LINE_PATTERNS)


def _cookie_auth_selftest() -> int:
    """CLI: ARCHIVE_SELFTEST_COOKIE_AUTH=1 python archive_playlist_run.py"""
    cases: tuple[tuple[str, bool], ...] = (
        ("ERROR: Sign in to confirm you're not a bot", True),
        ("Sign in to confirm your age", True),
        ("Could not copy Chrome cookie database: locked", True),
        ("CookieLoadError: invalid", True),
        ("HTTP Error 403: Forbidden", False),
        ("HTTP Error 403", False),
        ("Requested format is not available", False),
        ("ERROR: 403 Forbidden — bot detection failed", True),
        ("Login required to view this video", True),
    )
    bad = [c for c in cases if looks_like_likely_cookie_auth_error(c[0]) != c[1]]
    if bad:
        for text, want in bad:
            got = looks_like_likely_cookie_auth_error(text)
            print(f"FAIL expected {want} got {got}: {text!r}", file=sys.stderr)
        return 1
    print(f"ARCHIVE_SELFTEST_COOKIE_AUTH: ok ({len(cases)} cases)")

    if _env_truthy("ARCHIVE_SELFTEST_COOKIE_PAUSE"):
        import tempfile
        import threading

        d = tempfile.mkdtemp()
        ck = os.path.join(d, "cookies.txt")
        with open(ck, "w", encoding="utf-8") as f:
            f.write("# stale\n")
        rep = RunReporter(os.path.join(d, "_log"))
        os.environ[ARCHIVE_PAUSE_ON_COOKIE_ERROR_ENV] = "1"
        os.environ[ARCHIVE_COOKIE_AUTH_POLL_SEC_ENV] = "0.15"
        os.environ[ARCHIVE_COOKIE_AUTH_POLL_MAX_SEC_ENV] = "5"

        def _touch_later() -> None:
            time.sleep(0.35)
            with open(ck, "a", encoding="utf-8") as f:
                f.write("\n# refreshed\n")

        threading.Thread(target=_touch_later, daemon=True).start()
        _run_cookie_auth_blocking_wait(ck, rep)
        rep.close()
        with open(rep.run_log_path, encoding="utf-8") as f:
            slog = f.read()
        if "Cookie file mtime increased" not in slog:
            print("FAIL ARCHIVE_SELFTEST_COOKIE_PAUSE: expected mtime resume log line", file=sys.stderr)
            return 1
        print("ARCHIVE_SELFTEST_COOKIE_PAUSE: ok (poll path)")

    return 0


def _emit_cookie_auth_pause_banner(cookie_path: str, reporter: RunReporter) -> None:
    poll = os.environ.get(ARCHIVE_COOKIE_AUTH_POLL_SEC_ENV, "").strip()
    bar = "=" * 76
    lines = [
        "",
        bar,
        " ARCHIVE PAUSE - likely YouTube cookie / session / auth issue (heuristic match)",
        bar,
        " Fix: re-export cookies.txt, or adjust --cookies / --cookies-from-browser in yt-dlp.conf.",
        "      On Windows, close extra browser profiles; the browser must allow yt-dlp to read DB.",
        f" Cookie file for mtime poll (hint): {cookie_path}",
        (
            f" Polling every {poll}s until that file's modification time changes "
            f"(max {os.environ.get(ARCHIVE_COOKIE_AUTH_POLL_MAX_SEC_ENV, '7200')}s)."
            if poll
            else " Interactive: press Enter here when cookies are updated (stdin must be a TTY)."
        ),
        " This pause does not mark videos complete; archive + verify rules are unchanged.",
        bar,
        "",
    ]
    init_console()
    for ln in lines:
        reporter.log_line(ln)
        if not color_enabled():
            print(ln, file=sys.stdout)
            continue
        if ln == "":
            print(file=sys.stdout)
        elif ln == bar:
            print_role(ln, "header")
        elif "ARCHIVE PAUSE" in ln:
            print_role(ln.strip(), "warn")
        elif ln.startswith(" Fix:"):
            print_role(ln.strip(), "info")
        elif ln.startswith("      ") or ln.startswith(" Cookie file"):
            print_role(ln.strip(), "dim")
        elif ln.startswith(" Polling every") or ln.startswith(" Interactive:"):
            print_role(ln.strip(), "dim")
        elif ln.startswith(" This pause"):
            print_role(ln.strip(), "dim")
        else:
            print(ln, file=sys.stdout)


def _run_cookie_auth_blocking_wait(cookie_path: str, reporter: RunReporter) -> None:
    poll_raw = os.environ.get(ARCHIVE_COOKIE_AUTH_POLL_SEC_ENV, "").strip()
    try:
        poll_sec = float(poll_raw) if poll_raw else 0.0
    except ValueError:
        poll_sec = 0.0
    try:
        max_wait = float(os.environ.get(ARCHIVE_COOKIE_AUTH_POLL_MAX_SEC_ENV, "7200"))
    except ValueError:
        max_wait = 7200.0

    def _mtime(p: str) -> float | None:
        try:
            return os.path.getmtime(p) if os.path.isfile(p) else None
        except OSError:
            return None

    baseline = _mtime(cookie_path)
    deadline = time.monotonic() + max_wait

    if poll_sec > 0:
        reporter.log_line(
            f"[archive] Cookie-auth poll: every {poll_sec}s on {cookie_path!r} "
            f"(max {max_wait:.0f}s wall)."
        )
        while time.monotonic() < deadline:
            time.sleep(min(poll_sec, max(0.1, deadline - time.monotonic())))
            cur = _mtime(cookie_path)
            if cur is not None and (baseline is None or cur > baseline):
                reporter.log_line("[archive] Cookie file mtime increased - resuming yt-dlp queue.")
                msg = "\n[archive] cookies file updated - continuing run.\n"
                if color_enabled():
                    init_console()
                    print(file=sys.stdout)
                    print_role("[archive] cookies file updated - continuing run.", "ok")
                    print(file=sys.stdout)
                else:
                    print(msg, file=sys.stdout)
                return
        reporter.log_line("[archive] Cookie-auth poll: max wait elapsed - continuing anyway.")
        msg = (
            "\n[archive] Poll max wait elapsed - continuing "
            "(refresh cookies and rerun if needed).\n"
        )
        if color_enabled():
            init_console()
            print(file=sys.stdout)
            print_role(msg.strip(), "warn")
            print(file=sys.stdout)
        else:
            print(msg, file=sys.stdout)
        return

    if sys.stdin.isatty():
        reporter.log_line("[archive] Cookie-auth pause: waiting for Enter on stdin.")
        try:
            input("[archive] Press Enter after updating cookies (or Ctrl+C to abort)... ")
        except EOFError:
            pass
        reporter.log_line("[archive] Cookie-auth pause: stdin acknowledged - resuming.")
    else:
        msg = (
            "[archive] Non-interactive session: cannot wait for Enter. "
            f"Set {ARCHIVE_COOKIE_AUTH_POLL_SEC_ENV}=30 (or similar) to poll cookies.txt mtime, "
            "or rerun from a console with pause mode enabled."
        )
        reporter.log_line(msg)
        if color_enabled():
            init_console()
            print_role(msg, "warn")
        else:
            print(msg, file=sys.stdout)


CSV_COLUMNS = [
    "video_id",
    "title",
    "filepath",
    "file_size_bytes",
    "status",
    "reason",
    "timestamp_utc",
]

ISSUE_DISPLAY_COLUMNS = list(CSV_COLUMNS) + ["remediation"]

MANIFEST_EXTRA = ["file_verified_ok", "playlist_id", "webpage_url"]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _strip_ansi(s: str) -> str:
    return ANSI_RE.sub("", s).strip()


def _youtube_watch_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def playlists_downloaded_path() -> str:
    """Path to yt-dlp --download-archive file (playlist batch only)."""
    return os.path.join(SCRIPT_DIR, "playlists_downloaded.txt")


def channels_downloaded_path() -> str:
    """Path to yt-dlp --download-archive file (channel batch; archive_channel_run.py)."""
    return os.path.join(SCRIPT_DIR, "channels_downloaded.txt")


def videos_downloaded_path() -> str:
    """Path to yt-dlp --download-archive file (video list batch; archive_video_run.py)."""
    return os.path.join(SCRIPT_DIR, "videos_downloaded.txt")


# Manifest rows that count as a verified successful download (archive + summary).
MANIFEST_VERIFIED_DOWNLOAD_STATUSES = frozenset({"downloaded", "downloaded_merged"})


def _is_dash_stream_fragment_name(filename: str, video_id: str) -> bool:
    """True if basename looks like <id>.fNNN.<ext> (pre-merge DASH stream, not merged %(id)s.mkv)."""
    vid = (video_id or "").strip()
    if not vid:
        return False
    return bool(re.search(rf"{re.escape(vid)}\.f\d+\.", filename, re.I))


def _collect_final_media_artifacts(directory: str, video_id: str) -> list[str]:
    """
    List full paths to plausible *final* outputs for video_id in directory.

    Excludes names containing ``<id>.fNNN.`` so lone DASH fragments are not treated as
    the merged artifact. Extensions: mkv, mp4, webm, mov.
    """
    vid = (video_id or "").strip()
    if not vid or not directory or not os.path.isdir(directory):
        return []
    suffix = re.compile(rf"{re.escape(vid)}\.(mkv|mp4|webm|mov)$", re.I)
    out: list[str] = []
    try:
        names = os.listdir(directory)
    except OSError:
        return []
    for name in names:
        if not suffix.search(name):
            continue
        if _is_dash_stream_fragment_name(name, vid):
            continue
        full = os.path.join(directory, name)
        try:
            if os.path.isfile(full) and os.path.getsize(full) > 0:
                out.append(full)
        except OSError:
            continue
    return out


def _pick_best_final_artifact(paths: list[str]) -> str | None:
    """Prefer mkv over mp4/webm/mov, then larger file (typical merged output)."""
    if not paths:
        return None
    ext_rank = {".mkv": 0, ".mp4": 1, ".webm": 2, ".mov": 3}

    def key(p: str) -> tuple[int, int, int]:
        ext = os.path.splitext(p)[1].lower()
        try:
            sz = os.path.getsize(p)
        except OSError:
            sz = 0
        return (ext_rank.get(ext, 9), -sz, len(p))

    return min(paths, key=key)


def _pick_verified_media_path(declared_path: str, video_id: str) -> tuple[str | None, str]:
    """
    Resolve the file to verify after yt-dlp + ffmpeg merge.

    Hooks often record a pre-merge path (e.g. ``*.f313.webm``) that is removed when
    ``--merge-output-format mkv`` produces ``… - <id>.mkv`` beside it. We accept:

    - The declared path if it exists, is non-empty, and is *not* only a disposable fragment
      when a merged ``<id>.mkv`` (etc.) exists in the same folder (prefer the merged file).
    - Otherwise any ``<id>.mkv|mp4|webm|mov`` in the same directory without ``.fNNN.`` in
      the name, when the declared path is missing.

    If the only on-disk file is a ``.fNNN.*`` stream and nothing else qualifies, we still
    accept that path when it exists (no-merge / single-stream downloads).

    Returns ``(absolute_path, note)``; ``note`` is empty when no merge-path correction was needed.
    """
    vid = (video_id or "").strip()
    declared_path = os.path.normpath((declared_path or "").strip())
    directory = os.path.dirname(declared_path) if declared_path else ""
    finals = _collect_final_media_artifacts(directory, vid) if directory else []
    best_final = _pick_best_final_artifact(finals)

    if declared_path and os.path.isfile(declared_path) and os.path.getsize(declared_path) > 0:
        base = os.path.basename(declared_path)
        if not _is_dash_stream_fragment_name(base, vid):
            return os.path.abspath(declared_path), ""
        if best_final and os.path.abspath(best_final) != os.path.abspath(declared_path):
            return os.path.abspath(best_final), (
                f"Verified merged output {os.path.basename(best_final)} "
                f"(hook listed fragment {base})"
            )
        return os.path.abspath(declared_path), ""

    if not directory or not os.path.isdir(directory) or not vid:
        return None, ""
    if best_final:
        bn = os.path.basename(declared_path) if declared_path else ""
        return os.path.abspath(best_final), (
            f"Verified final output after merge: {os.path.basename(best_final)} "
            f"(hook path missing: {bn or 'none'})"
        )
    return None, ""


def sync_playlist_download_archive(
    manifest_rows: list[dict[str, str]],
    archive_path: str,
) -> None:
    """
    Make a yt-dlp --download-archive file (e.g. playlists_downloaded.txt or
    channels_downloaded.txt) match post-verify success only.

    - Removes youtube <id> lines for manifest rows with file_verified_ok=no (retry next run).
    - Appends youtube <id> for verified rows (status downloaded or downloaded_merged).
    - Preserves non-youtube lines and comments; dedupes youtube IDs on rewrite.
    """
    failed_ids = {
        r["video_id"].strip()
        for r in manifest_rows
        if (r.get("video_id") or "").strip() and r.get("file_verified_ok") == "no"
    }
    verified_ids = {
        r["video_id"].strip()
        for r in manifest_rows
        if r.get("file_verified_ok") == "yes"
        and r.get("status") in MANIFEST_VERIFIED_DOWNLOAD_STATUSES
        and (r.get("video_id") or "").strip()
    }
    lines: list[str] = []
    if os.path.isfile(archive_path):
        with open(archive_path, encoding="utf-8", errors="replace") as f:
            lines = [ln.rstrip("\n\r") for ln in f]

    kept: list[str] = []
    seen_youtube: set[str] = set()
    for ln in lines:
        s = ln.strip()
        if not s or s.startswith("#"):
            kept.append(ln)
            continue
        parts = s.split(None, 1)
        if len(parts) == 2 and parts[0].lower() == "youtube":
            vid = parts[1].strip()
            if vid in failed_ids:
                continue
            if vid in seen_youtube:
                continue
            seen_youtube.add(vid)
        kept.append(ln)

    for vid in sorted(verified_ids):
        if vid in seen_youtube:
            continue
        kept.append(f"youtube {vid}")
        seen_youtube.add(vid)

    try:
        with open(archive_path, "w", newline="\n", encoding="utf-8") as out:
            for ln in kept:
                out.write(ln + "\n")
    except OSError as e:
        print(f"WARNING: could not write {archive_path}: {e}", file=sys.stderr)


def _video_id_from_filename(path: str) -> str | None:
    m = ID_FROM_FILENAME_RE.search(path.replace("/", "\\"))
    return m.group(1) if m else None


def _json_embed_in_html(obj: Any) -> str:
    """JSON for embedding in HTML; escape < so </script> in strings cannot break the page."""
    return json.dumps(obj, ensure_ascii=False).replace("<", "\\u003c")


def _report_navigation(log_dir: str) -> list[dict[str, str | bool]]:
    """Links to sibling archive_run_* report.html (relative URLs, file:// friendly)."""
    parent = os.path.dirname(os.path.abspath(log_dir))
    current = os.path.basename(log_dir)
    out: list[dict[str, str | bool]] = []
    try:
        names = sorted(
            (n for n in os.listdir(parent) if n.startswith("archive_run_")),
            reverse=True,
        )
        for n in names:
            out.append(
                {
                    "href": f"../{n}/report.html",
                    "label": n,
                    "current": n == current,
                }
            )
    except OSError:
        pass
    return out


def _classify_issue_status(status: str, reason: str) -> str:
    """Return bucket: skipped | private_unavailable | failed"""
    if status in ("skipped_archive", "skipped_file_exists", "match_filter"):
        return "skipped"
    if status == "unavailable_or_private":
        return "private_unavailable"
    if status in ("error", "warning", "exception", "fatal", "cancelled", "interrupted"):
        if PRIVATE_UNAVAILABLE_RE.search(reason):
            return "private_unavailable"
        return "failed"
    if status in ("file_missing_after_hook", "file_missing_on_verify"):
        return "failed"
    return "failed"


def partition_issue_rows(
    issues_rows: list[dict[str, str]],
) -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]]:
    """Split issues into tables that align with summary.txt counters."""
    skipped_statuses = frozenset(
        {"skipped_archive", "skipped_file_exists", "match_filter"}
    )
    skipped: list[dict[str, str]] = []
    private: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    failed: list[dict[str, str]] = []
    for r in issues_rows:
        st = r.get("status", "")
        reason = r.get("reason", "")
        if st in skipped_statuses:
            skipped.append(r)
            continue
        bucket = _classify_issue_status(st, reason)
        if bucket == "private_unavailable":
            private.append(r)
        elif st == "warning":
            warnings.append(r)
        else:
            failed.append(r)
    return skipped, private, failed, warnings


def verify_summary_against_rows(
    counts: dict[str, int],
    manifest_rows: list[dict[str, str]],
    issues_rows: list[dict[str, str]],
    part: tuple[list, list, list, list],
) -> list[str]:
    """Return human-readable inconsistencies (empty if OK)."""
    skipped, private, failed, warnings = part
    errs: list[str] = []
    ver_down = sum(
        1
        for r in manifest_rows
        if r.get("file_verified_ok") == "yes"
        and r.get("status") in MANIFEST_VERIFIED_DOWNLOAD_STATUSES
    )
    if ver_down != counts["downloaded"]:
        errs.append(
            f"summary downloaded={counts['downloaded']} but manifest verified rows={ver_down}"
        )
    if len(skipped) != counts["skipped"]:
        errs.append(
            f"summary skipped={counts['skipped']} but skipped issue rows={len(skipped)}"
        )
    if len(private) != counts["private_unavailable"]:
        errs.append(
            f"summary private_unavailable={counts['private_unavailable']} "
            f"but private issue rows={len(private)}"
        )
    if len(failed) + len(warnings) != counts["failed"]:
        errs.append(
            f"summary failed={counts['failed']} but failed_strict+warning rows="
            f"{len(failed)}+{len(warnings)}"
        )
    recomputed = ver_down + len(skipped) + len(failed) + len(warnings) + len(private)
    if recomputed != counts["attempted"]:
        errs.append(
            f"summary attempted={counts['attempted']} but recomputed sum={recomputed}"
        )
    return errs


def _read_delimited_dict_rows(path: str, delimiter: str) -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        return [
            {k: (v or "").strip() for k, v in row.items()} for row in csv.DictReader(f, delimiter=delimiter)
        ]


def _is_legacy_manifest_tsv_row(keys: set[str]) -> bool:
    """Older runs wrote manifest.tsv with download_timestamp_utc / extractor (no status)."""
    return "download_timestamp_utc" in keys and "status" not in keys


def _is_legacy_issues_tsv_row(keys: set[str]) -> bool:
    """Older runs wrote issues.tsv with issue_type (not status)."""
    return "issue_type" in keys and "status" not in keys


def _prune_stale_file_missing_issues(
    manifest_rows: list[dict[str, str]], issues_rows: list[dict[str, str]]
) -> None:
    """
    Drop file_missing_on_verify issues when the manifest now verifies that video_id on disk.

    After _repair_manifest_file_verification, merged outputs can verify while issues.csv
    still contains the old false-negative row; removing it keeps summary/COUNT_CHECK aligned.
    """
    verified = {
        r["video_id"].strip()
        for r in manifest_rows
        if r.get("file_verified_ok") == "yes" and (r.get("video_id") or "").strip()
    }
    issues_rows[:] = [
        r
        for r in issues_rows
        if not (
            r.get("status") == "file_missing_on_verify"
            and (r.get("video_id") or "").strip() in verified
        )
    ]


def _repair_manifest_file_verification(rows: list[dict[str, str]]) -> None:
    """Set file_verified_ok and size from disk when possible (helps regenerate / legacy import)."""
    for r in rows:
        fp = (r.get("filepath") or "").strip()
        vid = (r.get("video_id") or "").strip()
        resolved, merge_note = _pick_verified_media_path(fp, vid)
        if resolved:
            r["filepath"] = resolved
            r["file_verified_ok"] = "yes"
            try:
                r["file_size_bytes"] = str(os.path.getsize(resolved))
            except OSError:
                pass
            stale = "Post-run verification failed (file missing)"
            reason_base = r.get("reason", "").rstrip()
            if merge_note:
                r["status"] = "downloaded_merged"
                if merge_note not in reason_base:
                    reason_base = (reason_base + " | " + merge_note).strip(" |")
            elif r.get("status") == "downloaded_file_missing_on_verify":
                r["status"] = "downloaded"
            r["reason"] = (
                reason_base.replace(f" | {stale}", "")
                .replace(f"{stale} | ", "")
                .strip(" |")
            )
        elif not (r.get("file_verified_ok") or "").strip():
            r["file_verified_ok"] = "no"


def read_manifest_issues_from_disk(
    log_dir: str,
) -> tuple[list[dict[str, str]], list[dict[str, str]], dict[str, str | bool]]:
    """
    Load manifest + issues from a run folder.

    Per file: uses manifest.csv if present, else manifest.tsv; same for issues.
    You can mix formats (e.g. manifest.csv + issues.tsv).

    Legacy .tsv uses old headers (download_timestamp_utc, issue_type); current-schema
    .tsv (same columns as .csv) is also accepted.

    Returns (manifest_rows, issue_rows, meta) where meta includes:
      manifest_source, issues_source: "csv" | "tsv" | ""
      upgraded_from_tsv: True if any side was read from .tsv (caller may write .csv)
    """
    manifest_fields = list(CSV_COLUMNS + MANIFEST_EXTRA)
    meta: dict[str, str | bool] = {
        "manifest_source": "",
        "issues_source": "",
        "upgraded_from_tsv": False,
    }
    out_m: list[dict[str, str]] = []
    mp_csv = os.path.join(log_dir, "manifest.csv")
    mp_tsv = os.path.join(log_dir, "manifest.tsv")

    if os.path.isfile(mp_csv):
        meta["manifest_source"] = "csv"
        for row in _read_delimited_dict_rows(mp_csv, ","):
            out_m.append({k: row.get(k, "").strip() for k in manifest_fields})
    elif os.path.isfile(mp_tsv):
        meta["manifest_source"] = "tsv"
        meta["upgraded_from_tsv"] = True
        raw = _read_delimited_dict_rows(mp_tsv, "\t")
        if not raw:
            pass
        elif _is_legacy_manifest_tsv_row(set(raw[0].keys())):
            for row in raw:
                fp = row.get("filepath", "").strip()
                out_m.append(
                    {
                        "video_id": row.get("video_id", ""),
                        "title": row.get("title", ""),
                        "filepath": fp,
                        "file_size_bytes": row.get("file_size_bytes", ""),
                        "status": "downloaded",
                        "reason": row.get("reason", "")
                        or "Imported from legacy manifest.tsv",
                        "timestamp_utc": row.get("download_timestamp_utc", "")
                        or row.get("timestamp_utc", ""),
                        "file_verified_ok": "",
                        "playlist_id": row.get("playlist_id", ""),
                        "webpage_url": row.get("webpage_url", ""),
                    }
                )
        else:
            for row in raw:
                out_m.append({k: row.get(k, "").strip() for k in manifest_fields})

    out_i: list[dict[str, str]] = []
    ip_csv = os.path.join(log_dir, "issues.csv")
    ip_tsv = os.path.join(log_dir, "issues.tsv")

    if os.path.isfile(ip_csv):
        meta["issues_source"] = "csv"
        for row in _read_delimited_dict_rows(ip_csv, ","):
            out_i.append({k: row.get(k, "").strip() for k in CSV_COLUMNS})
    elif os.path.isfile(ip_tsv):
        meta["issues_source"] = "tsv"
        meta["upgraded_from_tsv"] = True
        raw = _read_delimited_dict_rows(ip_tsv, "\t")
        for row in raw:
            keys = set(row.keys())
            if _is_legacy_issues_tsv_row(keys):
                st = (row.get("issue_type") or "").strip()
                out_i.append(
                    {
                        "video_id": row.get("video_id", ""),
                        "title": row.get("title", ""),
                        "filepath": row.get("filepath", ""),
                        "file_size_bytes": row.get("file_size_bytes", ""),
                        "status": st,
                        "reason": row.get("reason", ""),
                        "timestamp_utc": row.get("timestamp_utc", ""),
                    }
                )
            else:
                out_i.append({k: row.get(k, "").strip() for k in CSV_COLUMNS})

    _repair_manifest_file_verification(out_m)
    _prune_stale_file_missing_issues(out_m, out_i)
    return out_m, out_i, meta


def write_manifest_issues_csv_files(
    log_dir: str,
    manifest_rows: list[dict[str, str]],
    issues_rows: list[dict[str, str]],
) -> None:
    """Write canonical manifest.csv + issues.csv (same schema as a fresh run)."""
    manifest_fields = list(CSV_COLUMNS + MANIFEST_EXTRA)
    os.makedirs(log_dir, exist_ok=True)
    mp = os.path.join(log_dir, "manifest.csv")
    with open(mp, "w", newline="", encoding="utf-8") as mf:
        w = csv.DictWriter(mf, fieldnames=manifest_fields, extrasaction="ignore")
        w.writeheader()
        for row in manifest_rows:
            w.writerow({k: row.get(k, "") for k in manifest_fields})
    ip = os.path.join(log_dir, "issues.csv")
    with open(ip, "w", newline="", encoding="utf-8") as inf:
        w = csv.DictWriter(inf, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        w.writeheader()
        for row in issues_rows:
            w.writerow({k: row.get(k, "") for k in CSV_COLUMNS})


def write_summary_text(
    log_dir: str,
    counts: dict[str, int],
    *,
    heading: str = "Archive playlist run summary (UTC)",
) -> None:
    lines = [
        heading,
        "================================",
        "",
        f"Attempted (approx.):     {counts['attempted']}",
        f"Downloaded (verified):   {counts['downloaded']}",
        f"Skipped:                 {counts['skipped']}",
        f"Failed:                  {counts['failed']}",
        f"Private / unavailable:   {counts['private_unavailable']}",
        "",
        "Notes:",
        "- 'Attempted' = verified downloaded + skipped + private/unavailable + failed.",
        "  'Failed' in this file includes yt-dlp warnings; report.html splits Failed vs Warnings.",
        "- 'Downloaded' counts manifest rows where post-run verification succeeded "
        "(status downloaded or downloaded_merged).",
        "- See manifest.csv, issues.csv, and report.html (remediation column) for details.",
        "",
    ]
    with open(os.path.join(log_dir, "summary.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def compute_summary_counts(
    manifest_rows: list[dict[str, str]],
    issues_rows: list[dict[str, str]],
) -> dict[str, int]:
    downloaded = sum(
        1
        for r in manifest_rows
        if r.get("file_verified_ok") == "yes"
        and r.get("status") in MANIFEST_VERIFIED_DOWNLOAD_STATUSES
    )
    skipped = 0
    failed = 0
    private_unavailable = 0
    for r in issues_rows:
        bucket = _classify_issue_status(r.get("status", ""), r.get("reason", ""))
        if bucket == "skipped":
            skipped += 1
        elif bucket == "private_unavailable":
            private_unavailable += 1
        else:
            failed += 1
    attempted = downloaded + skipped + failed + private_unavailable
    return {
        "attempted": attempted,
        "downloaded": downloaded,
        "skipped": skipped,
        "failed": failed,
        "private_unavailable": private_unavailable,
    }


def build_report_payload(
    log_dir: str,
    manifest_rows: list[dict[str, str]],
    issues_rows: list[dict[str, str]],
    counts: dict[str, int],
    *,
    regenerated_from_csv: bool = False,
) -> dict[str, Any]:
    manifest_fields = list(CSV_COLUMNS + MANIFEST_EXTRA)
    skipped_rows, private_rows, failed_rows, warnings_rows = partition_issue_rows(
        issues_rows
    )

    downloaded_payload: list[dict[str, Any]] = []
    for r in manifest_rows:
        row_out: dict[str, Any] = {k: r.get(k, "") for k in manifest_fields}
        row_out["_missingFile"] = r.get("file_verified_ok") == "no"
        row_out["remediation"] = ""
        if row_out["_missingFile"]:
            row_out["remediation"] = suggest_remediation(
                "Post-run verification: file missing on disk"
            )
        elif r.get("status") == "downloaded_merged":
            row_out["remediation"] = (
                "Merged output verified: final file (e.g. .mkv) on disk; hook path may have "
                "been a pre-merge DASH fragment removed after ffmpeg mux."
            )
        downloaded_payload.append(row_out)

    def issue_row_display(r: dict[str, str]) -> dict[str, Any]:
        out: dict[str, Any] = {k: r.get(k, "") for k in CSV_COLUMNS}
        out["remediation"] = suggest_remediation(r.get("reason", ""))
        return out

    payload: dict[str, Any] = {
        "runLabel": os.path.basename(os.path.abspath(log_dir)),
        "generatedAtUtc": _utc_now_iso(),
        "summary": counts,
        "navigation": _report_navigation(log_dir),
        "manifestColumns": list(manifest_fields) + ["remediation"],
        "issueColumns": list(ISSUE_DISPLAY_COLUMNS),
        "downloaded": downloaded_payload,
        "downloadedGroupTree": True,
        "skipped": [issue_row_display(r) for r in skipped_rows],
        "privateUnavailable": [issue_row_display(r) for r in private_rows],
        "failed": [issue_row_display(r) for r in failed_rows],
        "warnings": [issue_row_display(r) for r in warnings_rows],
    }
    if regenerated_from_csv:
        payload["regeneratedFromCsv"] = True
    return payload


def _report_html_escape(val: Any) -> str:
    return html.escape("" if val is None else str(val), quote=True)


def _path_to_file_uri(p: str) -> str:
    s = (p or "").strip()
    if not s:
        return ""
    try:
        return pathlib.Path(os.path.normpath(s)).as_uri()
    except ValueError:
        return ""


def build_static_report_fragments(payload: dict[str, Any]) -> dict[str, str]:
    """Pre-render summary and tables so report.html is useful when JS is blocked (e.g. file://)."""
    s = payload.get("summary") or {}
    pairs = [
        ("Attempted (approx.)", s.get("attempted")),
        ("Downloaded (verified)", s.get("downloaded")),
        ("Skipped", s.get("skipped")),
        ("Failed", s.get("failed")),
        ("Private / unavailable", s.get("private_unavailable")),
    ]
    dl_parts: list[str] = []
    for label, val in pairs:
        dl_parts.append(f"<dt>{_report_html_escape(label)}</dt>")
        dl_parts.append(f"<dd>{_report_html_escape(val)}</dd>")
    static_summary_dl = "".join(dl_parts)

    def visible_columns(columns: list[Any]) -> list[str]:
        return [str(c) for c in columns if c is not None and not str(c).startswith("_")]

    def static_table(columns: list[str], rows: list[dict[str, Any]]) -> str:
        cols = visible_columns(columns)
        if not cols:
            return '<p class="muted"><em>No columns.</em></p>'
        if not rows:
            return '<p class="muted"><em>No rows.</em></p>'
        th = "".join(f"<th>{_report_html_escape(c)}</th>" for c in cols)
        tr_parts: list[str] = []
        for r in rows:
            tds: list[str] = []
            missing = bool(r.get("_missingFile")) or r.get("file_verified_ok") == "no"
            merged = (not missing) and r.get("status") == "downloaded_merged"
            if missing:
                row_cls = ' class="row-missing"'
            elif merged:
                row_cls = ' class="row-merged"'
            else:
                row_cls = ""
            for c in cols:
                val = str(r.get(c, "") or "")
                if c in ("filepath", "_path") and val.strip():
                    href = _path_to_file_uri(val)
                    if href:
                        cell = (
                            f'<a class="path-link" href="{_report_html_escape(href)}">'
                            f"{_report_html_escape(val)}</a>"
                        )
                    else:
                        cell = _report_html_escape(val)
                elif c in ("webpage_url", "suggested_url") and val.strip().lower().startswith(
                    ("http://", "https://")
                ):
                    cell = (
                        f'<a class="path-link" href="{_report_html_escape(val)}">'
                        f"{_report_html_escape(val)}</a>"
                    )
                else:
                    cell = _report_html_escape(val)
                tds.append(f"<td>{cell}</td>")
            tr_parts.append(f"<tr{row_cls}>" + "".join(tds) + "</tr>")
        return (
            '<div class="table-scroll"><table class="data"><thead><tr>'
            + th
            + "</tr></thead><tbody>"
            + "".join(tr_parts)
            + "</tbody></table></div>"
        )

    manifest_cols = list(payload.get("manifestColumns") or [])
    issue_cols = list(payload.get("issueColumns") or [])
    downloaded = list(payload.get("downloaded") or [])
    skipped = list(payload.get("skipped") or [])
    private_u = list(payload.get("privateUnavailable") or [])
    failed = list(payload.get("failed") or [])
    warnings = list(payload.get("warnings") or [])
    s = payload.get("summary") or {}
    verified_dl = s.get("downloaded")

    return {
        "STATIC_SUMMARY_DL": static_summary_dl,
        "CNT_DOWNLOADED": str(verified_dl if verified_dl is not None else len(downloaded)),
        "CNT_SKIPPED": str(len(skipped)),
        "CNT_PRIVATE_UNAVAILABLE": str(len(private_u)),
        "CNT_FAILED": str(len(failed)),
        "CNT_WARNINGS": str(len(warnings)),
        "STATIC_BODY_DOWNLOADED": static_table(manifest_cols, downloaded),
        "STATIC_BODY_SKIPPED": static_table(issue_cols, skipped),
        "STATIC_BODY_PRIVATE_UNAVAILABLE": static_table(issue_cols, private_u),
        "STATIC_BODY_FAILED": static_table(issue_cols, failed),
        "STATIC_BODY_WARNINGS": static_table(issue_cols, warnings),
        "SUMMARY_COUNT_HINT": (
            "<p class=\"muted\" style=\"margin:0.5rem 0 0\">"
            "Downloaded badge = verified on disk (file_verified_ok=yes), including "
            "<code>downloaded_merged</code> when the final muxed file replaced a hook-listed fragment. "
            "Table lists every manifest row. "
            "Failed + Warnings badges sum to the summary line &quot;Failed&quot;. "
            "Private / unavailable matches its summary line.</p>"
        ),
    }


def render_report_html(
    log_dir: str,
    payload: dict[str, Any],
    report_path: str | None = None,
) -> None:
    """Write report.html using archive_report_template.html and embedded JSON payload."""
    if report_path is None:
        report_path = os.path.join(log_dir, "report.html")
    template_path = os.path.join(SCRIPT_DIR, "archive_report_template.html")
    try:
        with open(template_path, encoding="utf-8") as tf:
            tmpl = tf.read()
    except OSError:
        tmpl = (
            "<!DOCTYPE html><html><head><meta charset=utf-8><title>Report</title></head><body>"
            "<p>Missing archive_report_template.html next to archive_playlist_run.py</p>"
            "<dl id=\"summary-dl\">__STATIC_SUMMARY_DL__</dl>"
            "__SUMMARY_COUNT_HINT__"
            "<div id=\"body-downloaded\">__STATIC_BODY_DOWNLOADED__</div>"
            "<div id=\"body-skipped\">__STATIC_BODY_SKIPPED__</div>"
            "<div id=\"body-private-unavailable\">__STATIC_BODY_PRIVATE_UNAVAILABLE__</div>"
            "<div id=\"body-failed\">__STATIC_BODY_FAILED__</div>"
            "<div id=\"body-warnings\">__STATIC_BODY_WARNINGS__</div>"
            "__REPORT_DATA__</body></html>"
        )
    data_el = (
        '<script type="application/json" id="report-data">'
        + _json_embed_in_html(payload)
        + "</script>"
    )
    frags = build_static_report_fragments(payload)
    html_out = tmpl.replace("__REPORT_DATA__", data_el)
    for key, fragment in frags.items():
        html_out = html_out.replace(f"__{key}__", fragment)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html_out)


class RunReporter:
    """Accumulates manifest/issue rows, then writes CSV, summary, HTML, rerun list."""

    def __init__(
        self,
        log_dir: str,
        *,
        archive_path: str | None = None,
        summary_heading: str | None = None,
        archive_sync_log_prefix: str = "[archive_playlist_run]",
    ):
        self.log_dir = log_dir
        self._archive_path = archive_path or playlists_downloaded_path()
        self._summary_heading = summary_heading or "Archive playlist run summary (UTC)"
        self._archive_sync_log_prefix = archive_sync_log_prefix
        os.makedirs(log_dir, exist_ok=True)
        self.manifest_path = os.path.join(log_dir, "manifest.csv")
        self.issues_path = os.path.join(log_dir, "issues.csv")
        self.summary_path = os.path.join(log_dir, "summary.txt")
        self.report_path = os.path.join(log_dir, "report.html")
        self.run_log_path = os.path.join(log_dir, "run.log")
        self.rerun_urls_path = os.path.join(log_dir, "rerun_urls.txt")

        self._run_log = open(self.run_log_path, "w", encoding="utf-8")
        self._manifest_rows: list[dict[str, str]] = []
        self._issues_rows: list[dict[str, str]] = []
        self._manifest_ids: set[str] = set()
        self._rerun_urls: set[str] = set()
        self._cookie_auth_pause_last_mono: float = 0.0

    def close(self) -> None:
        self._run_log.close()

    def log_line(self, line: str) -> None:
        self._run_log.write(line)
        if not line.endswith("\n"):
            self._run_log.write("\n")
        self._run_log.flush()

    def append_rerun(self, url: str | None) -> None:
        if url:
            self._rerun_urls.add(url.strip())

    def record_manifest_row(
        self,
        video_id: str,
        title: str,
        filepath: str,
        file_size: int,
        playlist_id: str,
        webpage_url: str,
        extractor: str,
    ) -> None:
        if video_id in self._manifest_ids:
            return
        if not os.path.isfile(filepath):
            self.record_issue(
                "file_missing_after_hook",
                video_id,
                title,
                "",
                f"Hook reported path but file missing: {filepath}",
                webpage_url or _youtube_watch_url(video_id),
            )
            return
        actual = os.path.getsize(filepath)
        if file_size < 0 or file_size != actual:
            file_size = actual
        self._manifest_rows.append(
            {
                "video_id": video_id,
                "title": title,
                "filepath": os.path.abspath(filepath),
                "file_size_bytes": str(file_size),
                "status": "downloaded",
                "reason": f"yt-dlp finished; extractor={extractor or 'unknown'}",
                "timestamp_utc": _utc_now_iso(),
                "playlist_id": playlist_id,
                "webpage_url": webpage_url,
            }
        )
        self._manifest_ids.add(video_id)

    def record_issue(
        self,
        status: str,
        video_id: str,
        title: str,
        filepath: str,
        reason: str,
        suggested_url: str,
    ) -> None:
        self._issues_rows.append(
            {
                "video_id": video_id,
                "title": title,
                "filepath": filepath,
                "file_size_bytes": "",
                "status": status,
                "reason": reason,
                "timestamp_utc": _utc_now_iso(),
            }
        )
        self.append_rerun(suggested_url)

    def verify_manifest_files(self) -> None:
        """Re-check each manifest row; resolve merged output path; set file_verified_ok."""
        for row in self._manifest_rows:
            fp = (row.get("filepath") or "").strip()
            vid = (row.get("video_id") or "").strip()
            resolved, merge_note = _pick_verified_media_path(fp, vid)
            if resolved:
                row["filepath"] = resolved
                row["file_verified_ok"] = "yes"
                row["file_size_bytes"] = str(os.path.getsize(resolved))
                if merge_note:
                    row["status"] = "downloaded_merged"
                    row["reason"] = (row.get("reason", "").rstrip() + " | " + merge_note).strip(
                        " |"
                    )
            else:
                row["file_verified_ok"] = "no"
                self.record_issue(
                    "file_missing_on_verify",
                    row.get("video_id", ""),
                    row.get("title", ""),
                    fp,
                    "Post-run verification: no final media file on disk (checked hook path "
                    "and same-folder <id>.mkv/.mp4/.webm/.mov without .fNN fragment)",
                    _youtube_watch_url(row["video_id"])
                    if row.get("video_id")
                    else "",
                )
                row["status"] = "downloaded_file_missing_on_verify"
                row["reason"] = (
                    row.get("reason", "")
                    + " | Post-run verification failed (file missing)"
                ).strip(" |")

    def finalize(self) -> None:
        self.verify_manifest_files()
        sync_playlist_download_archive(self._manifest_rows, self._archive_path)
        try:
            with open(self.run_log_path, "a", encoding="utf-8") as af:
                af.write(
                    f"{self._archive_sync_log_prefix} download archive synced after verify "
                    f"({os.path.basename(self._archive_path)}: file_verified_ok=yes; "
                    "status downloaded or downloaded_merged).\n"
                )
        except OSError:
            pass

        counts = self._compute_counts()
        part = partition_issue_rows(self._issues_rows)
        chk = verify_summary_against_rows(
            counts, self._manifest_rows, self._issues_rows, part
        )
        try:
            with open(self.run_log_path, "a", encoding="utf-8") as af:
                if chk:
                    for msg in chk:
                        af.write(f"COUNT_CHECK: {msg}\n")
                else:
                    af.write(
                        "COUNT_CHECK: summary counts match partitioned issues + verified manifest.\n"
                    )
        except OSError:
            pass

        manifest_fields = CSV_COLUMNS + MANIFEST_EXTRA
        with open(self.manifest_path, "w", newline="", encoding="utf-8") as mf:
            w = csv.DictWriter(mf, fieldnames=manifest_fields, extrasaction="ignore")
            w.writeheader()
            for row in self._manifest_rows:
                out = {k: row.get(k, "") for k in manifest_fields}
                w.writerow(out)

        with open(self.issues_path, "w", newline="", encoding="utf-8") as inf:
            w = csv.DictWriter(inf, fieldnames=CSV_COLUMNS, extrasaction="ignore")
            w.writeheader()
            for row in self._issues_rows:
                w.writerow({k: row.get(k, "") for k in CSV_COLUMNS})

        with open(self.rerun_urls_path, "w", encoding="utf-8") as rf:
            for u in sorted(self._rerun_urls):
                rf.write(u + "\n")

        self._write_summary(counts)
        self._write_report_html(counts)

    def _compute_counts(self) -> dict[str, int]:
        return compute_summary_counts(self._manifest_rows, self._issues_rows)

    def _write_summary(self, counts: dict[str, int]) -> None:
        write_summary_text(
            self.log_dir, counts, heading=self._summary_heading
        )

    def _write_report_html(self, counts: dict[str, int]) -> None:
        payload = build_report_payload(
            self.log_dir,
            self._manifest_rows,
            self._issues_rows,
            counts,
            regenerated_from_csv=False,
        )
        render_report_html(self.log_dir, payload, self.report_path)


class ManifestYoutubeDL(YoutubeDL):
    def __init__(self, params: dict, reporter: RunReporter):
        self._reporter = reporter
        cf = (params.get("cookiefile") or "").strip()
        if cf:
            p = os.path.normpath(os.path.expanduser(cf))
            self._cookiefile_path_for_pause = (
                p if os.path.isabs(p) else os.path.normpath(os.path.join(SCRIPT_DIR, p))
            )
        else:
            self._cookiefile_path_for_pause = os.path.join(SCRIPT_DIR, "cookies.txt")
        super().__init__(params)

    def _trigger_cookie_auth_operator_pause_if_needed(self, plain: str) -> None:
        if not _env_truthy(ARCHIVE_PAUSE_ON_COOKIE_ERROR_ENV):
            return
        if not looks_like_likely_cookie_auth_error(plain):
            return
        now = time.monotonic()
        if now - self._reporter._cookie_auth_pause_last_mono < 3.0:
            return
        self._reporter._cookie_auth_pause_last_mono = now
        _emit_cookie_auth_pause_banner(self._cookiefile_path_for_pause, self._reporter)
        self._reporter.record_issue(
            "warning",
            "",
            "",
            "",
            "[archive] Operator cookie/auth pause - see run.log banner; queue continued after wait.",
            "",
        )
        _run_cookie_auth_blocking_wait(self._cookiefile_path_for_pause, self._reporter)

    def record_download_archive(self, info_dict):
        """
        yt-dlp normally appends to playlists_downloaded.txt as soon as a download finishes.
        We only persist IDs after post-run file verification (see sync_playlist_download_archive).
        Still add to in-memory archive so duplicate URLs in one playlist are skipped.
        """
        fn = self.params.get("download_archive")
        if not fn:
            return
        vid_id = self._make_archive_id(info_dict)
        if not vid_id:
            return
        self.archive.add(vid_id)
        self.write_debug(
            f"Deferred archive file write for {vid_id!r} (on-disk list updated after verify)"
        )

    def to_screen(self, message, skip_eol=False, quiet=None, only_once=False):
        plain = _strip_ansi(str(message))
        if plain:
            self._reporter.log_line(plain)
            self._parse_screen_message(plain)
        msg_out = augment_ytdlp_console_message(str(message), plain)
        return super().to_screen(
            msg_out, skip_eol=skip_eol, quiet=quiet, only_once=only_once
        )

    def to_stderr(self, message, only_once=False):
        plain = _strip_ansi(str(message))
        if plain:
            self._reporter.log_line(plain)
            self._trigger_cookie_auth_operator_pause_if_needed(plain)
        msg_out = augment_ytdlp_console_message(str(message), plain)
        return super().to_stderr(msg_out, only_once=only_once)

    def report_error(self, message, *args, **kwargs):
        try:
            plain_line = (
                message % args if args and isinstance(message, str) else str(message)
            )
        except (TypeError, ValueError):
            plain_line = str(message) + (
                (" " + " ".join(str(a) for a in args)) if args else ""
            )
        plain_line = _strip_ansi(plain_line)
        self._reporter.record_issue("error", "", "", "", plain_line, "")
        self._trigger_cookie_auth_operator_pause_if_needed(plain_line)
        return super().report_error(message, *args, **kwargs)

    def report_warning(self, message, only_once=False):
        plain = _strip_ansi(str(message))
        self._reporter.record_issue("warning", "", "", "", plain, "")
        return super().report_warning(message, only_once=only_once)

    def _parse_screen_message(self, plain: str) -> None:
        if not plain.startswith("[download]"):
            return
        m = ARCHIVE_SKIP_RE.match(plain)
        if m:
            vid, title = m.group(1), m.group(2).strip()
            self._reporter.record_issue(
                "skipped_archive",
                vid,
                title,
                "",
                plain,
                _youtube_watch_url(vid),
            )
            return
        if "has already been downloaded" in plain.lower():
            self._reporter.record_issue(
                "skipped_file_exists",
                "",
                "",
                "",
                plain,
                "",
            )
            return
        low = plain.lower()
        if "private video" in low or "video unavailable" in low or "not available" in low:
            self._reporter.record_issue(
                "unavailable_or_private", "", "", "", plain, ""
            )
            return
        if "does not pass filter" in low or "matches filter" in low:
            self._reporter.record_issue("match_filter", "", "", "", plain, "")


def _build_argv(script_dir: str) -> list[str]:
    return [
        "--config-locations",
        os.path.join(script_dir, "yt-dlp.conf"),
        "--download-archive",
        playlists_downloaded_path(),
        "--batch-file",
        os.path.join(script_dir, "playlists_input.txt"),
        "-o",
        os.path.join(
            _playlist_output_base(script_dir),
            "%(playlist_id)s",
            "%(upload_date)s - %(title)s - %(id)s.%(ext)s",
        ),
    ]


def _info_from_hook(d: dict) -> tuple[dict, str | None]:
    info = d.get("info_dict") or {}
    path = d.get("filename") or info.get("filepath")
    return info, path


def _resolve_video_id(info: dict, path: str | None) -> str | None:
    vid = info.get("id")
    if vid:
        return str(vid)
    if path:
        return _video_id_from_filename(path)
    return None


def main() -> int:
    os.chdir(SCRIPT_DIR)
    init_console()
    log_stamp = sys.argv[1] if len(sys.argv) > 1 else None
    if not log_stamp:
        log_stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    log_dir = os.path.join(SCRIPT_DIR, "logs", f"archive_run_{log_stamp}")
    reporter = RunReporter(log_dir)
    emit_driver_start_banner(
        reporter,
        title="Archive playlist run (Watch Later / playlists_input.txt)",
        subtitle="yt-dlp + deferred download-archive sync after verification",
    )

    argv = list(_build_argv(SCRIPT_DIR))
    if _env_truthy("ARCHIVE_DRY_RUN"):
        argv.append("--simulate")
        reporter.log_line(
            "[archive_playlist_run] ARCHIVE_DRY_RUN=1: passing --simulate to yt-dlp "
            "(no files written to disk or archive; hooks may not mirror a real run)."
        )
        print_role(
            "[archive] ARCHIVE_DRY_RUN=1: yt-dlp --simulate (no writes to disk/archive)",
            "warn",
        )
    try:
        po = yt_dlp.parse_options(argv)
    except SystemExit as e:
        reporter.record_issue("fatal", "", "", "", f"parse_options failed: {e}", "")
        reporter.close()
        reporter.finalize()
        rc_pe = int(e.code) if isinstance(e.code, int) else 1
        emit_final_summary(
            log_dir=log_dir,
            log_stamp=log_stamp,
            report_path=reporter.report_path,
            rc=rc_pe,
            driver_label="archive_playlist_run",
            pointer_lines=["Playlist pointer: logs\\latest_run.txt (written only on successful init)"],
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

    ydl_opts["progress_hooks"] = list(ydl_opts.get("progress_hooks") or []) + [progress_hook]
    ydl_opts["postprocessor_hooks"] = list(ydl_opts.get("postprocessor_hooks") or []) + [
        postprocessor_hook
    ]

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

    latest_path = os.path.join(SCRIPT_DIR, "logs", "latest_run.txt")
    try:
        with open(latest_path, "w", encoding="utf-8") as lf:
            lf.write(log_dir + "\n")
    except OSError:
        pass

    emit_final_summary(
        log_dir=log_dir,
        log_stamp=log_stamp,
        report_path=reporter.report_path,
        rc=rc,
        driver_label="archive_playlist_run",
        pointer_lines=["Playlist pointer: logs\\latest_run.txt"],
    )
    return rc


if __name__ == "__main__":
    if _env_truthy("ARCHIVE_SELFTEST_COOKIE_AUTH"):
        raise SystemExit(_cookie_auth_selftest())
    raise SystemExit(main())
