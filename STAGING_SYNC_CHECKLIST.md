# Staging sync checklist

**Purpose:** track what must appear in **`scripts__publish_staging`** (public/anonymized tree) vs operator-only content.

**Inventory — last 30 days**

| Source | What we used |
|--------|----------------|
| **Operator dev tree** (`<ARCHIVE_ROOT>`, e.g. sibling of this repo) | **Not a git repository** in this environment — no `git log`. Sync verified by running **`python tools/publish_staging.py`** from that tree (redacts paths to `<ARCHIVE_ROOT>`, strips secrets per script rules). |
| **This staging repo** | `git log --oneline --since="30 days ago"`: `832aee7` docs: README — cookie gate, tray reminders, settings copy; `3484cfd` docs: add anonymized UI screenshots for README; `fe1a6e4` chore: initial public import from publish staging. |

**How this sync was produced (2026-03-29)**

1. `py -3 tools/publish_staging.py --source <ARCHIVE_ROOT> --dest` a fresh build folder.
2. **Did not** delete the live staging folder while locked by the IDE; **`robocopy /E /IS /IT`** merged the fresh build into this repo, **preserving `.git`**.
3. Re-apply manual edits: this file, **`README.md`** tweaks below the auto “Public snapshot” block (publish script appends that block once).

**Sanity commands (operator)**

- Path / cookie grep (expect **no** raw profiles, **no** `Netscape` cookie dumps in shipped docs): search tree for `E:\Users`, machine-specific roots.
- **Tests:** from **`archive_console/`** with venv created by **`start_archive_console.bat`**:  
  `archive_console\.venv\Scripts\python.exe -m pytest`  
  (Global `py -3` may miss **`pluggy`** / venv deps.)

---

## Checklist

| Path / area | Must ship? | Synced? | Notes |
|-------------|------------|---------|--------|
| **`tools/publish_staging.py`** | Y | Y | Authoritative copy + redact rules; do not strip `LICENSE`/`.gitignore` workflow. |
| **`README.md`** (root) | Y | Y | Operator quick start, Console summary, tray/stop/token; `<ARCHIVE_ROOT>` placeholders only. |
| **`BAT_FILES.md`**, **`BAT_AUDIT.md`** | Y | Y | Audit may be optional for forks; included for maintainers. |
| **`ARCHIVE_PLAYLIST_RUN_LOGS.txt`**, **`yt-dlp.conf`**, monthly / one-off drivers | Y | Y | Core batch + Python stack. |
| **`archive_console/app/**` (FastAPI, shutdown, run, files, oneoff, settings, …) | Y | Y | Loopback-only shutdown; no weaker auth. |
| **`archive_console/static/app.js`**, **`app.css`**, **`templates/index.html`** | Y | Y | Modals, Files player/queue, shutdown UX. |
| **`archive_console/tray_app.py`**, tray assets | Y | Y | Spawn watch + HTTP shutdown header for token. |
| **`archive_console/ARCHIVE_CONSOLE.md`** | Y | Y | Detailed behavior (stop, tray, cookies, player). |
| **`archive_console/tests/**`** | Y | Y | Includes shutdown, cookie gate, oneoff, files player tests. |
| **`archive_console/state.example.json`**, **`state.json.example`** | Y | Y | No real **`state.json`** (excluded by publish). |
| **`PUBLISH_MANIFEST.md`**, **`CONTRIBUTING.md`**, **`LICENSE`**, **`.gitignore`** | Y | Y | Regenerated/overwritten by publish script each run. |
| **`STAGING_SYNC_CHECKLIST.md`** (this file) | Y | Y | Maintainer sync inventory; not produced by `publish_staging.py` — keep updated when cutting releases. |
| **`cookies.txt`**, **`channels_input.txt`**, real **`state.json`** | N | N | Never ship; use `.example` / `.sample.txt`. |
| **`logs/`, `playlists/`, `channels/`, `videos/`** (content trees) | N | N | Skipped by publish script. |
| **`!CLOSE CHROME FIRST.txt`**, **`!RUN AS ADMINISTRATOR.txt`** (0-byte markers) | N | Y | Harmless; optional to **`.gitignore`** for public repo cleanliness. |
| **Root `UPDATE *.png`** (screenshots) | Optional | Y | Fine for docs; large binaries — commit if you want visual README aids. |

**Rule:** anything marked **Must ship = Y** should show **Synced = Y** before push. If you add features only in the private tree, re-run **`publish_staging.py`** (or merge selective files) and update this table.
