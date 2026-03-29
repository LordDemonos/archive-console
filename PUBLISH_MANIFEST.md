# Publish manifest

Anonymized snapshot for public sharing. **Do not** treat paths in this repo as the operator’s machine.

## Third-party / disclaimer

This project is **not affiliated with YouTube, Google LLC, or the yt-dlp project**. yt-dlp is third-party software; you install and configure it yourself and must comply with applicable site terms and laws.

## BAT_FILES.md checklist (`.bat` coverage)

| BAT_FILES.md entry | Staging | Note |
|--------------------|---------|------|
| `monthly_watch_later_archive.bat` | included | from source (redacted) |
| `monthly_channels_archive.bat` | included | from source (redacted) |
| `monthly_videos_archive.bat` | included | from source (redacted) |
| `archive_playlists_advanced.bat` | included | from source (redacted) |
| `archive_youtube_channels.bat` | included | from source (redacted) |
| `archive_videos.bat` | included | from source (redacted) |
| `archive_channels_robust.bat` | included | from source (redacted) |
| `regenerate_report.bat` | included | from source (redacted) |
| `verify_downloads.bat` | included | from source (redacted) |
| `start_archive_console.bat` | included | from source (redacted) |
| `start_archive_console_tray.bat` | included | from source (redacted) |
| `archive_console/start_archive_console.bat` | included | from source (redacted) |
| `archive_console/_launch_uvicorn.bat` | included | from source (redacted) |
| `archive_playlists.bat` | placeholder stub | BAT_FILES.md legacy; not in source tree |
| `archive_playlists_robust.bat` | placeholder stub | same |
| `archive_channels.bat` | placeholder stub | same |

- **On-disk `.bat` files scanned (excl. `.venv`):** 13

## Included (categories)

- Root drivers: `archive_*_run.py`, `archive_run_console.py`, `archive_print_role.py`, `regenerate_report.py`, `repair_playlist_download_archive.py`, `yt-dlp.conf`
- Batch entrypoints and stubs (see table)
- Docs: `README.md`, `BAT_FILES.md`, `ARCHIVE_PLAYLIST_RUN_LOGS.txt`, `archive_console/ARCHIVE_CONSOLE.md`
- Archive Console app: `archive_console/app/`, `templates/`, `static/`, `tests/`, `requirements.txt`, `print_bind.py`, tray sources, `state.example.json` / `state.json.example`, `*.ps1`
- Tooling: `tools/publish_staging.py` (regenerate staging from a full tree)

## Excluded (why)

- `archive_console/state.json — local UI state paths/history (use state.example.json)`
- `archive_console/yt_dlp_ui_state.json — local editor UI state`
- `channels_downloaded.txt — operator download-archive state`
- `channels_downloaded_backup.txt — backup of operator state`
- `channels_input.txt — operator URL lists (ship *.sample.txt)`
- `cookies.txt — secret / session (ship cookies.txt.example)`
- `credentials.json — secrets, vendored binary, or local-only input (see manifest)`
- `playlists_downloaded.txt — operator download-archive state`
- `playlists_downloaded_backup.txt — backup of operator state`
- `playlists_input.txt — operator URL lists (ship *.sample.txt)`
- `remove_wl_token.json — secrets, vendored binary, or local-only input (see manifest)`
- `test_input.txt — secrets, vendored binary, or local-only input (see manifest)`
- `videos_downloaded.txt — operator download-archive state`
- `videos_input.txt — operator URL lists (ship *.sample.txt)`
- `yt-dlp.exe — secrets, vendored binary, or local-only input (see manifest)`
- `yt-dlp_x86.exe — secrets, vendored binary, or local-only input (see manifest)`

### Excluded — entire directory classes

- `logs/` — run outputs
- `playlists/`, `channels/`, `videos/`, top-level `test/` — download trees / scratch
- `Archivist Scripts/`, `Audio-Only Scripts/`, `Watch Scripts/` — local bundles not in core publish set
- Root `credentials.json`, `remove_wl_token.json`, `yt-dlp.exe`, `yt-dlp_x86.exe`, `test_input.txt`
- `.venv/`, `__pycache__/`, `.pytest_cache/` — environments
- `archive_console/backups/` — may contain copies of operator inputs

## Generated at runtime (do not ship from operator disk)

- `logs/archive_run_*`, `latest_run*.txt`, `run_summary.json`, etc.
- `*_downloaded.txt`, `*_backup.txt`
- `archive_console/state.json`, `archive_console/yt_dlp_ui_state.json`
- `cookies.txt`

## Reproduce this staging folder

```bat
cd <ARCHIVE_ROOT>
python tools\publish_staging.py
```

Default destination: sibling `<ARCHIVE_ROOT>__publish_staging`.
