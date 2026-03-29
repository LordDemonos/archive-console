# Batch files inventory (`*.bat`)

Complete catalog of **every** `*.bat` under this repo (recursive search: **12 files**, all in repo root).  
**Operational narrative:** use **`README.md`**. This file is the **authoritative** per-file inventory.

**Three PRIMARY drivers** (same stack: `yt-dlp.conf`, optional `python -m pip install --upgrade pip` unless `SKIP_PIP_UPDATE=1` (unset in batch defaults to skip), then pip `yt-dlp[default]` unless `SKIP_YTDLP_UPDATE=1`, `archive_playlist_run`/`ManifestYoutubeDL` pattern, deferred archive lines until verify, `logs\archive_run_<UTC>\`, `COUNT_CHECK` in `run.log`, separate `latest_run*.txt` per pipeline; all three honor **`ARCHIVE_CONSOLE_UNATTENDED=1`** to skip interactive `pause` steps for the **Archive Console**):

| Batch | Python entry | Input | Archive file | Output tree | `latest_run` pointer | Env (representative) |
|-------|--------------|-------|--------------|-------------|----------------------|----------------------|
| `monthly_watch_later_archive.bat` | `archive_playlist_run.py` | `playlists_input.txt` | `playlists_downloaded.txt` | `playlists\…` (or `ARCHIVE_OUT_PLAYLIST` if set) | `logs\latest_run.txt` | … + optional **`ARCHIVE_OUT_PLAYLIST`** (absolute output root for playlist tree; **Archive Console** sets this per saved settings) |
| `monthly_channels_archive.bat` | `archive_channel_run.py` | `channels_input.txt` | `channels_downloaded.txt` | `channels\…` or **`ARCHIVE_OUT_CHANNEL`** | `logs\latest_run_channel.txt` | Above + `ARCHIVE_CHANNEL_EXPAND_TABS` (set `=0` to disable tab split); optional **`ARCHIVE_OUT_CHANNEL`** |
| `monthly_videos_archive.bat` | `archive_video_run.py` | `videos_input.txt` | `videos_downloaded.txt` | `videos\…` or **`ARCHIVE_OUT_VIDEOS`** | `logs\latest_run_videos.txt` | Same cookie/pip/dry-run toggles as playlist; optional **`ARCHIVE_OUT_VIDEOS`** |

Verified against the `.bat` and `.py` sources (2026-03): each primary bat backs up its `*_downlisted.txt` before run, runs the matching `python "%~dp0archive_*_run.py"`, and prints paths from the correct `logs\latest_run*.txt`.

---

## Per-file inventory

| File | Purpose (one line) | Calls / entry | Status | Safe to delete? |
|------|---------------------|---------------|--------|------------------|
| `monthly_watch_later_archive.bat` | Monthly / batch **playlist** archive (Watch Later + `playlists_input.txt`). | `python "%~dp0archive_playlist_run.py"` | **PRIMARY** | **no** |
| `monthly_channels_archive.bat` | Monthly / batch **whole-channel** archive from `channels_input.txt`. | `python "%~dp0archive_channel_run.py"` | **PRIMARY** | **no** |
| `monthly_videos_archive.bat` | Batch **ad-hoc video URL list** from `videos_input.txt`. | `python "%~dp0archive_video_run.py"` | **PRIMARY** | **no** |
| `archive_playlists_advanced.bat` | Back-compat entry for renamed playlist driver. | `call "%~dp0monthly_watch_later_archive.bat"` | **STUB** | **no** — keep until shortcuts/Task Scheduler use `monthly_*` only |
| `archive_youtube_channels.bat` | Back-compat entry for renamed channel driver. | `call "%~dp0monthly_channels_archive.bat"` | **STUB** | **no** — same |
| `archive_videos.bat` | Back-compat entry for renamed video-list driver. | `call "%~dp0monthly_videos_archive.bat"` | **STUB** | **no** — same |
| `archive_channels_robust.bat` | Legacy name → channel driver (old direct-yt-dlp wrapper retired). | `call "%~dp0monthly_channels_archive.bat"` | **STUB** | **no** — optional **delete candidate** only after grep + shortcut audit |
| `regenerate_report.bat` | Rebuild `report.html` (+ CSV refresh) from an existing run folder. | `python "%~dp0regenerate_report.py" %*` | **UTILITY** | **no** |
| `verify_downloads.bat` | Rough comparison: `playlists\WL` `*.mp4` count vs `playlists_downloaded.txt` lines. | Inline `dir` / `find` (no Python) | **UTILITY** (legacy heuristic) | **only after** you rely on manifest/`report.html` only; does not understand `.mkv` or merged outputs |
| `archive_playlists.bat` | Minimal playlist download: raw `python -m yt_dlp` + `yt-dlp.conf`; **no** manifest, **no** deferred archive verify. | `python -m yt_dlp … --batch-file=playlists_input.txt` | **LEGACY / UNUSED** | **only after** you confirm you never want uninstrumented playlist runs; **no** other repo file references it |
| `archive_playlists_robust.bat` | Same raw `yt_dlp` playlist path as above with friendlier echoes/retry UI. | `python -m yt_dlp …` (same args pattern) | **LEGACY / UNUSED** | Same as `archive_playlists.bat` |
| `archive_channels.bat` | Minimal channel download: raw `python -m yt_dlp`; **no** manifest / verify stack. | `python -m yt_dlp … --batch-file=channels_input.txt` | **LEGACY / UNUSED** | **only after** confirming no use; **no** other repo file references it |

---

## Cross-check (repo references)

- **`yt-dlp.conf`** header lists the three **`monthly_*`** drivers + Python modules (not stub names).
- **`ARCHIVE_PLAYLIST_RUN_LOGS.txt`** documents all three pipelines + `regenerate_report.bat`; legacy stub names appear only in “legacy still works” lines where applicable.
- **Ripgrep** for basenames `archive_playlists.bat`, `archive_playlists_robust.bat`, `archive_channels.bat`: matches **only this file** — safe to treat as **optional delete candidates**, not **required** stubs.

Stubs (`archive_playlists_advanced`, `archive_youtube_channels`, `archive_videos`, `archive_channels_robust`) **are** referenced by name in this inventory and in deprecation echoes; keep unless you migrate external launchers.

---

## Task Scheduler / shortcuts

Prefer actions that target **`monthly_watch_later_archive.bat`**, **`monthly_channels_archive.bat`**, and **`monthly_videos_archive.bat`** directly. Stubs exist so **old paths keep working** without silent failure.

---

## Duplication policy

Do **not** merge `playlists_downloaded.txt`, `channels_downloaded.txt`, or `videos_downloaded.txt`. Each PRIMARY driver maintains its own completion state and **`logs\latest_run*.txt`**.
