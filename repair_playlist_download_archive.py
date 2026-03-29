#!/usr/bin/env python3
"""
Drop youtube <id> lines from playlists_downloaded.txt for manifest rows with
file_verified_ok=no (and append any verified=yes rows missing from the file).

Use after an older yt-dlp run wrote the archive before post-run verification, so bad IDs
were skipped on retry. Point at the run folder that recorded the failure.

  python repair_playlist_download_archive.py
  python repair_playlist_download_archive.py "<ARCHIVE_ROOT>\\logs\\archive_run_YYYYMMDD_HHMMSS"
"""

from __future__ import annotations

import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from archive_playlist_run import (  # noqa: E402
    playlists_downloaded_path,
    read_manifest_issues_from_disk,
    sync_playlist_download_archive,
    write_manifest_issues_csv_files,
)


def main() -> int:
    os.chdir(SCRIPT_DIR)
    if len(sys.argv) > 1:
        log_dir = os.path.abspath(sys.argv[1].strip().strip('"'))
    else:
        latest = os.path.join(SCRIPT_DIR, "logs", "latest_run.txt")
        if not os.path.isfile(latest):
            print("No logs\\latest_run.txt — pass log folder path as argument.", file=sys.stderr)
            return 1
        with open(latest, encoding="utf-8") as f:
            log_dir = f.read().strip()
    if not os.path.isdir(log_dir):
        print(f"Not a directory: {log_dir}", file=sys.stderr)
        return 1
    manifest_rows, issues_rows, meta = read_manifest_issues_from_disk(log_dir)
    if not manifest_rows:
        print(f"No manifest in {log_dir} (manifest_source={meta.get('manifest_source')!r})")
        return 1
    p = playlists_downloaded_path()
    sync_playlist_download_archive(manifest_rows, p)
    write_manifest_issues_csv_files(log_dir, manifest_rows, issues_rows)
    n_bad = sum(1 for r in manifest_rows if r.get("file_verified_ok") == "no")
    print(f"Synced {p} from {log_dir} ({len(manifest_rows)} rows, {n_bad} not verified on disk).")
    print(f"Wrote manifest.csv + issues.csv under {log_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
