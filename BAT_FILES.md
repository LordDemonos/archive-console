# Batch files inventory (`*.bat`)

Authoritative **per-file** inventory for batch entrypoints in this repo. **Operational narrative:** `README.md`. **Content-backed audit (classes, line evidence, staging caveats):** **`BAT_AUDIT.md`**.

## Supported monthly drivers (PRIMARY)

Exactly **three** batch entrypoints run the instrumented Python stack (manifest, deferred archive, `logs\archive_run_<UTC>\`, `report.html`, separate `latest_run*.txt` pointers). All honor **`ARCHIVE_CONSOLE_UNATTENDED=1`** for Archive Console:

| Batch | Python entry | Input | Archive file | Output tree | `latest_run` pointer |
|-------|--------------|-------|--------------|-------------|----------------------|
| `monthly_watch_later_archive.bat` | `archive_playlist_run.py` | `playlists_input.txt` | `playlists_downloaded.txt` | `playlists\…` (or `ARCHIVE_OUT_PLAYLIST`) | `logs\latest_run.txt` |
| `monthly_channels_archive.bat` | `archive_channel_run.py` | `channels_input.txt` | `channels_downloaded.txt` | `channels\…` (or `ARCHIVE_OUT_CHANNEL`) | `logs\latest_run_channel.txt` |
| `monthly_videos_archive.bat` | `archive_video_run.py` | `videos_input.txt` | `videos_downloaded.txt` | `videos\…` (or `ARCHIVE_OUT_VIDEOS`) | `logs\latest_run_videos.txt` |

---

## Per-file inventory (files that exist here)

Excludes **`archive_console\.venv\Scripts\*.bat`** (Python venv; not archive drivers).

| File | Purpose (one line) | Calls / entry | Class | Safe to delete? |
|------|---------------------|---------------|-------|------------------|
| `monthly_watch_later_archive.bat` | Playlist / Watch Later + `playlists_input.txt`. | `python "%~dp0archive_playlist_run.py"` (see file L89) | **PRIMARY** | **no** |
| `monthly_channels_archive.bat` | Whole-channel archive from `channels_input.txt`. | `python "%~dp0archive_channel_run.py"` (L89) | **PRIMARY** | **no** |
| `monthly_videos_archive.bat` | Video URL list from `videos_input.txt`. | `python "%~dp0archive_video_run.py"` (L89) | **PRIMARY** | **no** |
| `oneoff_archive.bat` | Thin wrapper for **`archive_oneoff_run.py`** (expects UTC log stamp argv). | `python -u "%~dp0archive_oneoff_run.py" %1` | **OPTIONAL** (UI-primary path is Archive Console) | optional |
| `archive_playlists_advanced.bat` | Deprecated name → forwards to playlist monthly. | `call "%~dp0monthly_watch_later_archive.bat" %*` then `exit /b %errorlevel%` | **WRAPPER_FORWARD** | **no** — keep for Task Scheduler / shortcuts |
| `archive_youtube_channels.bat` | Deprecated name → forwards to channel monthly. | `call "%~dp0monthly_channels_archive.bat" %*` then `exit /b %errorlevel%` | **WRAPPER_FORWARD** | **no** |
| `archive_videos.bat` | Deprecated name → forwards to video monthly. | `call "%~dp0monthly_videos_archive.bat" %*` then `exit /b %errorlevel%` | **WRAPPER_FORWARD** | **no** |
| `archive_channels_robust.bat` | Deprecated name → forwards to channel monthly. | `call "%~dp0monthly_channels_archive.bat" %*` then `exit /b %errorlevel%` | **WRAPPER_FORWARD** | **no** |
| `regenerate_report.bat` | Rebuild `report.html` from existing run folder. | `python "%~dp0regenerate_report.py" %*` | **UTILITY** | **no** |
| `verify_downloads.bat` | Rough `dir` / `find` count vs archive lines (playlist WL heuristic only). | No Python driver; no `monthly_*` | **UTILITY (legacy)** | optional if you rely only on manifest / `report.html` |
| `start_archive_console.bat` (repo root) | Create/use venv, health check, start or open Archive Console. | PowerShell helpers, `uvicorn` via `_launch_uvicorn.bat` or attached | **LAUNCHER** | **no** |
| `start_archive_console_tray.bat` | Start tray (`tray_app.py`) with **no lingering CMD** (venv/`pip` then `pythonw` + `start /D`). | `pythonw.exe tray_app.py` detached under `archive_console` | **LAUNCHER** | **no** |
| `archive_console/_launch_uvicorn.bat` | Dedicated window: run uvicorn with host/port env. | `python -m uvicorn app.main:app …` | **LAUNCHER** | **no** |
| `archive_console/start_archive_console.bat` | Wrapper: `cd` to parent and `call start_archive_console.bat`. | `call start_archive_console.bat %*` | **WRAPPER_FORWARD** | **no** |

---

## Names documented historically but not in this tree

These **do not exist** as `.bat` files in the full developer tree:

- `archive_playlists.bat`
- `archive_playlists_robust.bat`
- `archive_channels.bat`

**Public / GitHub snapshot:** `tools/publish_staging.py` may create **placeholder** files with those names that **only** echo a message and **`exit /b 2`** — they **do not** call `monthly_*`. Do not treat them as archive entrypoints; point Task Scheduler at the **`monthly_*`** names or the **WRAPPER_FORWARD** stubs above. See **`BAT_AUDIT.md`** and **`README.md`** (snapshot note).

---

## Cross-check (repo references)

- **`yt-dlp.conf`** header lists the three **`monthly_*`** drivers + Python modules (not stub names).
- **`ARCHIVE_PLAYLIST_RUN_LOGS.txt`** documents all three pipelines + `regenerate_report.bat`; legacy stub names are noted where applicable.
- **Archive Console** `run_manager.py` spawns **`monthly_watch_later_archive.bat`**, **`monthly_channels_archive.bat`**, **`monthly_videos_archive.bat`**, and (for **One-off**) **`python -u archive_oneoff_run.py`** directly.

**WRAPPER_FORWARD** stubs **are** referenced by name in `README.md`, this file, and operator docs; keep unless you migrate **external** launchers.

---

## Task Scheduler / shortcuts

**Prefer** actions that target **`monthly_watch_later_archive.bat`**, **`monthly_channels_archive.bat`**, and **`monthly_videos_archive.bat`** directly.

If a task still uses **`archive_playlists_advanced.bat`**, **`archive_youtube_channels.bat`**, **`archive_videos.bat`**, or **`archive_channels_robust.bat`**, those files **`call`** the correct **`monthly_*`** driver — safe **compatibility** paths.

---

## Duplication policy

Do **not** merge `playlists_downloaded.txt`, `channels_downloaded.txt`, or `videos_downloaded.txt`. Each PRIMARY driver maintains its own completion state and **`logs\latest_run*.txt`**.
