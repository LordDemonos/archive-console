#!/usr/bin/env python3
"""
Rebuild report.html from existing manifest/issues data (no yt-dlp run).

Reads manifest.csv + issues.csv, or legacy manifest.tsv + issues.tsv (older runs).
Reconciles file paths from disk (merged .mkv vs hook-listed .fNNN fragment), prunes stale
file_missing_on_verify issues when the manifest verifies, then writes manifest.csv,
issues.csv, summary.txt, and report.html.

Default: folder from logs/latest_run.txt (Watch Later / playlist driver).
For channel runs, use logs/latest_run_channel.txt or pass a folder path.
For video-list runs, use logs/latest_run_videos.txt or pass a folder path.
  python regenerate_report.py "<ARCHIVE_ROOT>\\logs\\archive_run_..."
"""

from __future__ import annotations

import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from archive_playlist_run import (  # noqa: E402
    build_report_payload,
    compute_summary_counts,
    read_manifest_issues_from_disk,
    render_report_html,
    write_manifest_issues_csv_files,
    write_summary_text,
    _utc_now_iso,
)

_CHANNEL_SUMMARY_PREFIX = "Archive channel run summary"
_VIDEO_SUMMARY_PREFIX = "Archive video run summary"


def _resolve_log_dir(argv: list[str]) -> str:
    if len(argv) > 1:
        p = os.path.abspath(argv[1].strip().strip('"'))
        if not os.path.isdir(p):
            raise SystemExit(f"Not a directory: {p}")
        return p
    latest = os.path.join(SCRIPT_DIR, "logs", "latest_run.txt")
    if not os.path.isfile(latest):
        raise SystemExit(
            "No folder argument and logs\\latest_run.txt not found.\n"
            "Usage: python regenerate_report.py [path_to_archive_run_..._folder]"
        )
    with open(latest, encoding="utf-8") as f:
        line = f.read().strip()
    if not line or not os.path.isdir(line):
        raise SystemExit(f"logs\\latest_run.txt does not point to a valid folder:\n  {line!r}")
    return line


def main() -> int:
    log_dir = _resolve_log_dir(sys.argv)
    has_new = os.path.isfile(os.path.join(log_dir, "manifest.csv")) or os.path.isfile(
        os.path.join(log_dir, "issues.csv")
    )
    has_legacy = os.path.isfile(os.path.join(log_dir, "manifest.tsv")) or os.path.isfile(
        os.path.join(log_dir, "issues.tsv")
    )
    if not has_new and not has_legacy:
        raise SystemExit(
            f"No manifest/issues files in:\n  {log_dir}\n"
            "Expected manifest.csv + issues.csv, or legacy manifest.tsv + issues.tsv"
        )

    manifest_rows, issues_rows, meta = read_manifest_issues_from_disk(log_dir)
    print(
        "Loaded: manifest="
        f"{meta.get('manifest_source') or '(none)'}, issues="
        f"{meta.get('issues_source') or '(none)'} "
        f"({len(manifest_rows)} rows, {len(issues_rows)} issue rows)"
    )
    if meta.get("upgraded_from_tsv"):
        write_manifest_issues_csv_files(log_dir, manifest_rows, issues_rows)
        print(f"Wrote canonical manifest.csv + issues.csv (from .tsv where needed)")

    counts = compute_summary_counts(manifest_rows, issues_rows)
    summary_path = os.path.join(log_dir, "summary.txt")
    heading = "Archive playlist run summary (UTC)"
    if os.path.isfile(summary_path):
        try:
            with open(summary_path, encoding="utf-8") as sf:
                first = sf.readline().strip()
            if first.startswith(_CHANNEL_SUMMARY_PREFIX) or first.startswith(
                _VIDEO_SUMMARY_PREFIX
            ):
                heading = first
        except OSError:
            pass
    write_summary_text(log_dir, counts, heading=heading)

    payload = build_report_payload(
        log_dir,
        manifest_rows,
        issues_rows,
        counts,
        regenerated_from_csv=True,
    )
    payload["generatedAtUtc"] = _utc_now_iso()
    out = os.path.join(log_dir, "report.html")
    render_report_html(log_dir, payload, out)
    write_manifest_issues_csv_files(log_dir, manifest_rows, issues_rows)
    print(f"Wrote: {out}")
    print(f"Wrote: {os.path.join(log_dir, 'summary.txt')}")
    print(
        "Wrote: manifest.csv + issues.csv (paths/status reconciled from disk; stale "
        "file_missing_on_verify rows dropped when manifest verifies)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
