# Batch files audit (content-backed)

**Scope:** All `*.bat` under this repo **excluding** `**/.venv/**` (Python venv shims are not project entrypoints).  
**Rule of thumb:** If a `.bat` exits **non-zero without** `call`ing or `start`ing a `monthly_*` driver (or a documented utility), it is **not** a supported archive entrypoint.

**Sources read:** Each file body (2026-03); `BAT_FILES.md`; ripgrep for basenames in `*.md`, `*.py`, `*.txt`, `*.json`, `tools/publish_staging.py`.

---

## Classification table

| Path | First lines / behavior | Class | Invokes / calls | Exit | Doc refs |
|------|------------------------|-------|-----------------|------|----------|
| `monthly_watch_later_archive.bat` | L1 `@echo off`, L2 `cd /d "%~dp0"` | **PRIMARY** | L89 `python "%~dp0archive_playlist_run.py"`; pip blocks L51–76 | L143 `exit /b %YTDLP_RC%` | `BAT_FILES.md`, `README.md`, `ARCHIVE_CONSOLE.md`, `run_manager.py`, `ARCHIVE_PLAYLIST_RUN_LOGS.txt` |
| `monthly_channels_archive.bat` | L1–2 same | **PRIMARY** | L89 `python "%~dp0archive_channel_run.py"` | L131 `exit /b %YTDLP_RC%` | same |
| `monthly_videos_archive.bat` | L1–2 same | **PRIMARY** | L89 `python "%~dp0archive_video_run.py"` | L131 `exit /b %YTDLP_RC%` | same |
| `archive_playlists_advanced.bat` | L1 `@echo off`, L2–3 REM deprecated | **WRAPPER_FORWARD** | L8 `call "%~dp0monthly_watch_later_archive.bat" %*` | L9 `exit /b %errorlevel%` | `BAT_FILES.md`, `README.md`, `publish_staging.py` list |
| `archive_youtube_channels.bat` | L1 `@echo off`, REM deprecated | **WRAPPER_FORWARD** | L8 `call "%~dp0monthly_channels_archive.bat" %*` | L9 `exit /b %errorlevel%` | same |
| `archive_channels_robust.bat` | L1–2 `@echo off` + `cd /d` | **WRAPPER_FORWARD** | L7 `call "%~dp0monthly_channels_archive.bat" %*` | L8 `exit /b %errorlevel%` | same |
| `archive_videos.bat` | L1–2 `@echo off` + `cd /d` | **WRAPPER_FORWARD** | L7 `call "%~dp0monthly_videos_archive.bat" %*` | **`exit /b %ERRORLEVEL%`** after `call` (aligned with other stubs) | same |
| `regenerate_report.bat` | L1–3 REM + L3 `cd /d "%~dp0"` | **OTHER** (utility) | L4 `python "%~dp0regenerate_report.py" %*` | Implicit from `python`; L5 `pause` on failure | `BAT_FILES.md`, `ARCHIVE_PLAYLIST_RUN_LOGS.txt` |
| `verify_downloads.bat` | L1–2 `@echo off`, `cd /d` | **OTHER** (legacy heuristic) | `dir` / `find` only; **no** `monthly_*`, **no** Python driver | Ends L45 `pause`; no `exit /b` — typical **0** after user keypress | `BAT_FILES.md` |
| `start_archive_console.bat` (repo root) | `setlocal`, venv, `print_bind`, health check | **LAUNCHER_ONLY** | `python` venv pip, `port_busy.ps1`, `stop_server.ps1`, `start … _launch_uvicorn.bat` or attached uvicorn, `Start-Sleep`, `start http://…` | L69 / L81 `exit /b` as coded | `README.md`, `ARCHIVE_CONSOLE.md` |
| `start_archive_console_tray.bat` | venv, `pip`, `start /D` + `pythonw.exe tray_app.py` | **LAUNCHER_ONLY** | Detached **`pythonw`**; batch exits **0** after `start` | `exit /b 0` | same |
| `archive_console/_launch_uvicorn.bat` | L1 `@echo off` helper | **LAUNCHER_ONLY** | L17 `.venv\Scripts\python.exe -m uvicorn app.main:app …` | L18 `exit /b %ERRORLEVEL%` | `ARCHIVE_CONSOLE.md`, root launcher |
| `archive_console/start_archive_console.bat` | L1–4 wrapper | **WRAPPER_FORWARD** | L5 `call start_archive_console.bat %*` (from parent dir) | Forwards nested call | `publish_staging.py` list |

### Excluded from table (toolchain)

| Path | Class |
|------|--------|
| `archive_console/.venv/Scripts/activate.bat`, `deactivate.bat` | **OTHER** — Python venv; do not document as archive drivers |

---

## `BAT_FILES.md` mismatches (resolved in this pass)

| Issue | Evidence |
|-------|----------|
| Header claimed **12** root `.bat` files / “recursive search” without excluding venv | Glob (2026-03): **13** project bats excluding `.venv`; venv adds 2 more under `archive_console/.venv`. |
| Inventory rows for `archive_playlists.bat`, `archive_playlists_robust.bat`, `archive_channels.bat` described real files with `python -m yt_dlp` | **No such files** in this working tree. **Only** references: `BAT_FILES.md` itself and `tools/publish_staging.py` (which **writes** stub `.bat` with `exit /b 2` into **publish staging** only). |
| `archive_videos.bat` listed like other stubs with explicit `exit /b` | **Fixed:** explicit `exit /b %errorlevel%` added after `call` (matches other WRAPPER_FORWARD shims). |

---

## Publish staging vs full tree (GitHub snapshot)

`tools/publish_staging.py` defines `LEGACY_BAT` (echo “not present in the public source snapshot” + **`exit /b 2`**) and writes it as **`archive_playlists.bat`**, **`archive_playlists_robust.bat`**, **`archive_channels.bat`** into the staging root — class **STUB_ERROR** there only. The **full** repo does not ship those three names as real drivers; contributors must not describe them as PRIMARY.

---

## In-repo references (not exhaustive)

- **Monthly drivers only in `run_manager.py`:** `monthly_watch_later_archive.bat`, `monthly_channels_archive.bat`, `monthly_videos_archive.bat`.
- **Stubs** appear by name in `README.md`, `BAT_FILES.md`, `ARCHIVE_PLAYLIST_RUN_LOGS.txt`, `publish_staging.py`.
- **External risk:** Task Scheduler / shortcuts on operator PCs may still point at **`archive_*.bat`** — keep **WRAPPER_FORWARD** shims unless operator opts in to migration.

---

## Recommendations (ordered)

1. **KEEP** — All three **`monthly_*_archive.bat`**; **`start_archive_console.bat`**; **`start_archive_console_tray.bat`**; **`archive_console/_launch_uvicorn.bat`**; **`archive_console/start_archive_console.bat`**; **`regenerate_report.bat`**.
2. **KEEP (compatibility)** — **`archive_playlists_advanced.bat`**, **`archive_youtube_channels.bat`**, **`archive_videos.bat`**, **`archive_channels_robust.bat`** as **WRAPPER_FORWARD** until external launchers are migrated.
3. **KEEP_DOC_ONLY / clarify** — **`verify_downloads.bat`**: document as **legacy heuristic** only; prefer manifest / `report.html` for truth.
4. **MERGE (docs only)** — Remove phantom rows from **`BAT_FILES.md`**; point **`publish_staging`** STUB_ERROR behavior here and in **`README.md`**.
5. **DO NOT REMOVE** — **`WRAPPER_FORWARD`** shims without explicit operator sign-off and **README/BAT_FILES** migration paragraph for Task Scheduler users.
6. **Done** — **`archive_videos.bat`** now ends with `exit /b %errorlevel%` after `call`.

---

## Cleanup checklist (safe order)

- [x] Add this **`BAT_AUDIT.md`**.
- [x] Fix **`BAT_FILES.md`**: remove nonexistent `.bat` from per-file inventory; add publish-staging / snapshot note.
- [x] Patch **`README.md`**: three PRIMARY drivers + legacy shims + snapshot caveat.
- [ ] (Optional) Operator: grep **Task Scheduler** export XML / shortcuts on your PC for old names before deleting any stub.
- [ ] (Optional) Replace publish-staging **STUB_ERROR** files with **WRAPPER_FORWARD** copies from a machine that has full tree — only if you want public clone to run those names without editing tasks.
- [x] Root **`.gitignore`**: `logs/*` except **`logs/example_run/**`**, Python caches, **`latest_run*.txt`**, **`debug-*.log`** (see **`CLEANUP_PR.md`**).
- [x] Add **`CLEANUP_PR.md`**: table of removed paths + grep proofs + staging notes (this pass: **no** `.bat` deletions; **`verify_downloads.bat`** kept).
