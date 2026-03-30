# Repo cleanup record (working tree / GitHub hygiene)

**WRAPPER_FORWARD shims are not “unnecessary”; only phantom docs, cruft, and explicitly approved legacy utilities may be removed.**

## Git

At cleanup time, **`<ARCHIVE_ROOT>`** was **not** a git repository in this environment (`fatal: not a git repository`). Apply the same edits in your real clone, then run **`git status`** and commit in themed chunks (e.g. `.gitignore` only, then docs).

## Deleted paths (this pass)

| Path | Reason | Reference check |
|------|--------|-----------------|
| *(none)* | No safe deletions required: **WRAPPER_FORWARD** / **PRIMARY** / **LAUNCHER** bats unchanged; **`verify_downloads.bat`** still referenced (see below). | — |

## Kept by policy

| Path / name | Notes |
|-------------|--------|
| **`verify_downloads.bat`** | **Legacy heuristic** per **`BAT_AUDIT.md`**; listed in **`BAT_FILES.md`** and **`tools/publish_staging.py`** `bat_files`. Not removed. |
| **`archive_playlists_advanced.bat`**, **`archive_youtube_channels.bat`**, **`archive_channels_robust.bat`**, **`archive_videos.bat`** | **WRAPPER_FORWARD** — must stay unless operator migrates Task Scheduler / shortcuts. |
| **`monthly_*_archive.bat`** | **PRIMARY**; **`archive_console/app/run_manager.py`** maps jobs only to these three names. |

## Intentional “phantom” names (not on-disk in full tree)

Placeholders **`archive_playlists.bat`**, **`archive_playlists_robust.bat`**, **`archive_channels.bat`** appear in **`README.md`**, **`BAT_FILES.md`**, **`BAT_AUDIT.md`**, and **`tools/publish_staging.py`** (**STUB_ERROR** in staging only). This is **by design**, not a stale reference.

**Grep (illustrative):** from repo root, `rg "archive_playlists\\.bat"` should show only docs + `publish_staging.py` + manifest strings — **no** false inventory row claiming the file exists in the developer tree ( **`BAT_FILES.md`** “Names documented historically…” section).

## Changed paths (2026-03-29 pass)

| Path | Change |
|------|--------|
| `.gitignore` | Ignore **`logs/*`** except **`logs/example_run/**`**, **`latest_run*.txt`**, Python **`__pycache__`/`.pytest_cache`**, **`debug-*.log`**. |
| `BAT_AUDIT.md` | Cleanup checklist + pointer here. |
| `README.md` | File map → **`CLEANUP_PR.md`**. |
| `CLEANUP_PR.md` | This file. |

## `run_manager.py` (three PRIMARY)

Unchanged mapping:

- **`watch_later`** → `monthly_watch_later_archive.bat`
- **`channels`** → `monthly_channels_archive.bat`
- **`videos`** → `monthly_videos_archive.bat`

## Publish staging

**Default unchanged:** `LEGACY_BAT` placeholders (**`exit /b 2`**) for the three legacy names; no new flag to copy **WRAPPER_FORWARD** bodies unless the operator requests it.

## Verification

- **`pytest`** (Archive Console): `archive_console/tests` — **pass** (2026-03-29, 100%).
