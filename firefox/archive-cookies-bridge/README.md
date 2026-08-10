# Archive Console Cookies

Firefox companion for **Archive Console** (fork of [cookies-txt](https://github.com/hrdl-github/cookies-txt)). Uses the same gold-arrow icon as the Console tray. Pushes **YouTube + Google** Netscape cookies while a yt-dlp batch run is paused on cookie/auth errors.

Upstream export-to-file and clipboard behavior is unchanged. This fork adds:

- Background poll of `GET /api/cookies/youtube-refresh`
- Automatic `PUT /api/cookies/youtube` when `refresh_needed` or `preflight_needed` is true (before a run starts, or while paused mid-run)
- Optional **reload of YouTube tab(s)** before export (default on) — helps with yt-dlp `The page needs to be reloaded` / stale player session
- Popup **Send to Console** for manual/test export
- Options page for Console URL, poll interval, and reload mode

## Prerequisites

1. **Archive Console** running on loopback during batch jobs (check **Settings → port**; this install uses `http://127.0.0.1:9876` unless you changed it).
2. **YouTube batch** in Console: enable **ARCHIVE_PAUSE_ON_COOKIE_ERROR** and set poll interval (e.g. **15s**). Saved in `state.json` → `ytdlp_batch_run`.
3. Firefox logged into YouTube in the **same profile** the extension uses.
4. `archive_root` in Console points at your scripts folder (where `cookies.txt` lives).

## Install (development)

1. Open Firefox → `about:debugging` → **This Firefox**.
2. **Load Temporary Add-on…** → select `manifest.json` in this folder.
3. Open extension **Options** → confirm base URL matches Console port.
4. Optional: use **Send to Console** in the popup to verify PUT works before a live run.

For a persistent install, package/sign the extension or use your preferred Firefox sideload workflow.

## How it works

```text
Before start (preflight, default in Console):
  → POST /api/run/start → Console writes .archive_needs_cookies.txt (preflight_before_run:<job>)
  → extension alarm (~10s) sees preflight_needed on GET /api/cookies/youtube-refresh
  → export from open **Watch Later** tab (or active YouTube tab) in that Firefox profile + PUT /api/cookies/youtube → yt-dlp batch spawns

Mid-run (pause on cookie error / "page needs to be reloaded"):
  → archive driver writes .archive_needs_cookies.txt and pauses
  → extension sees refresh_needed
  → reloads export YouTube tab (or all YouTube tabs — Options) and waits for complete
  → export + PUT /api/cookies/youtube
  → driver sees cookies.txt mtime change → cookies.run.txt + reload → resume
```

If no YouTube tab is open, auto-export falls back to `youtube.com` + `google.com`
in the configured cookie store (default `firefox-default`).

Only update **`cookies.txt`**. Never edit **`cookies.run.txt`** (yt-dlp scratch copy).

## Archive Console API

Base URL: `http://127.0.0.1:<port>` (from Settings / `state.json`).

### `GET /api/cookies/youtube-refresh`

Response (200):

```json
{
  "refresh_needed": true,
  "preflight_needed": false,
  "request": { "requested_utc": "...", "reason": "cookie_auth_warning" },
  "cookies_txt_mtime": 1710000000.0,
  "cookies_txt_size": 4096,
  "run": { "phase": "running", "job": "watch_later", ... }
}
```

Poll when `refresh_needed === true` or `preflight_needed === true`.

### `PUT /api/cookies/youtube`

Request:

```json
{
  "content": "# Netscape HTTP Cookie File\n...",
  "unlock_cookies": true
}
```

Response (200): `{ "rel": "cookies.txt", "mtime": ..., "refresh_cleared": true, ... }`

Allowed **while a job is running** (unlike `PUT /api/files/cookies.txt`).

## Options

| Setting | Default | Notes |
|---------|---------|--------|
| Auto-poll | on | Master switch for background alarm |
| Reload YouTube tab(s) before export | on | Refresh player/session before `cookies.getAll` |
| Which tabs to reload | export tab only | Or **all** open `youtube.com` / Music tabs |
| Base URL | `http://127.0.0.1:9876` (match Console **Settings → port**) | Must match Console |
| Poll interval | 0.167 min (~10s) | Should be ≤ Console cookie poll (15s) |
| Cookie store ID | empty | Optional override; auto-export normally uses the open YouTube tab’s store |

## Dry test (no batch)

1. Start Archive Console.
2. Create sentinel in archive root: empty file `.archive_needs_cookies.txt` or run `request_cookie_refresh` via a failing job.
3. Open `GET /api/cookies/youtube-refresh` → `refresh_needed: true`.
4. Click **Send to Console** in the popup (or wait for alarm).
5. Confirm `cookies.txt` updated and sentinel removed.

## Troubleshooting

| Symptom | Likely cause |
|---------|----------------|
| `refresh_needed` always false | Pause env off; no sentinel; wrong `archive_root` |
| PUT 400 | Empty export or invalid Netscape format |
| PUT OK but run stuck | Poll env off on driver; same file content (mtime unchanged) |
| Extension silent | Console down; wrong port; auto-poll disabled |
| yt-dlp still warns | Stale browser session — reload YouTube tab, verify playback, re-export; also update yt-dlp if ancient |
| Auto export wrong account | No YouTube tab open (fallback used) or override wrong store ID — keep Subscriptions (or any youtube.com tab) open |

## License

This fork includes upstream cookies-txt code (see `LICENCE`). Archive Console integration is part of the YT-DLP scripts project.
