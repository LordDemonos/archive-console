# Library player — control audit (post-fix)

**Purpose:** Embedded playlist + HTML5 **video/audio** and **slideshow images** over allowlisted `GET /reports/file?rel=…` (same security as **Open**). Queue persisted in **`localStorage`** key **`archive_console_library_player_v1`** (migrates from legacy **`archive_console_files_player_v1`**; payload **`v: 3`**; v2 still loads).

**Queueable types:** Video/audio (unchanged) plus raster images **`.jpg` `.jpeg` `.png` `.gif` `.webp`** (case-insensitive). Other extensions are rejected when adding to the queue. **`is_playable_media_path`** on the server remains **video/audio only** (Watch Now / clip export); folder enqueue uses **`is_files_player_queue_media_path`** (includes images).

| Control | Intended behavior | Handler | API / URL | Disabled when |
|--------|-------------------|---------|------------|---------------|
| **Video** | Play/pause/seek; `Range` via Starlette `FileResponse` | Native + `error` → inline error line | `src` = `/reports/file?rel=…` | Hidden when an image slide is active |
| **Image slide** | Two `<img>` layers; **crossfade** or **none**; `object-fit: contain` on **`#filesMediaStage`** | `fpApplyImageToStage` | `/reports/file?rel=…` | — |
| **Track ended** (video only) | **`ended` ignored** if `video` is hidden (image mode). **Loop on:** advance or wrap. **Loop off:** next or **End of queue** toast. **`video.loop` stays false**. | `ended` → `fpEnded` | — | — |
| **Timed slideshow** | When **Timed** is on and current item is an **image**, auto-advance after **interval** (s); **Pause** stops timer; **Resume** restarts. **GIF:** browser animates; timer still advances on schedule. | checkbox + `setTimeout` chain | — | — |
| **Play / pause** | **Video:** toggle `play()` / `pause()` when current is video. **Image + timed:** toggle slideshow pause (same as **Pause** in fullscreen HUD). Else resolve target → `fpPlayTargetRelNow`. | toolbar `click` | — | No target + empty queue (message) |
| **Prev** | Previous in `fpPlayOrder`; wrap if **loop** on | `fpPrev(true)` | — | Empty queue |
| **Next** | Next in `fpPlayOrder`; wrap if **loop** on | `fpNext(true)` | — | Empty queue |
| **Shuffle** | Toggle **on** → immediate Fisher–Yates on **`fpBaseQueue`** (whole list once). **Off** → **`fpPlayOrder`** = **`fpBaseQueue`** slice (insertion order). Applies to **all** queue item types. | `click` → `fpRebuildOrder` | — | — |
| **Loop** | Whole-queue wrap only | `click` | — | — |
| **Transition** | **Crossfade** (default) vs **None** (instant swap) | `<select>` | — | — |
| **Fullscreen** | **Fullscreen API** on **`#filesMediaStage`** (video + images + overlay + HUD). **Esc** / **Exit** leaves fullscreen. | `requestFullscreen` | — | — |
| **Info overlay** | Basename, path (truncated + `title` = full rel), size, dimensions; **metadata** size from list row, else **`GET /api/files/metadata?path=`** | toggle + `fpUpdateStageMeta` | `/api/files/metadata` | — |
| **Fullscreen HUD** | Prev / Pause / Next / Info / Exit (visible in fullscreen) | buttons | — | Hidden when not fullscreen |
| **Arrow keys** | **Prev** / **Next** when **Files** view active (not in inputs) | `window` `keydown` | — | — |
| **Space** | Video: play/pause. **Image + timed:** toggle slideshow pause. | `keydown` | — | — |
| **I** | Toggle info overlay | `keydown` | — | — |
| **Add selected file** | Append deduped **queueable** path | `fpQueueAppendPlayable` | — | No queueable selection |
| **Add folder (here)** | Enumerate **direct children**: video, audio, **and** slideshow images | `fetch` | `GET /api/files/playable-enumerate?path=&max_files=` | At virtual roots with no path |
| **Remove** | Drop row; reload current media if queue non-empty | splice `fpBaseQueue` | — | — |
| **Clear** | Empty queue; clear video + image layers | reset arrays | — | — |
| **Queue double-click** | `fpPlayTargetRelNow` | `dblclick` | `/reports/file` | — |
| **Image load error** | Inline error + **skip to next** (or clear if single item) | `img` `onerror` | — | — |

## Layout / persistence (`v: 3` fields)

| Field | Behavior |
|--------|----------|
| **`slideshowTimed`** | Timed advance for **images** |
| **`slideshowPaused`** | Timer pause state |
| **`slideshowIntervalSec`** | 1–120 |
| **`transition`** | `crossfade` \| `none` |
| **`overlayVisible`** | Stage meta panel |

| Control | Behavior |
|--------|----------|
| **Vertical splitter** | **`localStorage`:** `archive_console_library_split_pct` (migrates from `archive_console_files_split_pct`) |
| **Workspace height** | **`library.workspace.height`** (migrates from **`files.workspace.height`**) |
| **Media frame** | **`#filesVideoFrame`** wraps **`#filesMediaStage`**; height from **`ResizeObserver`** + aspect (**`videoWidth`/`videoHeight`** or image **`naturalWidth`/`naturalHeight`**; **16∶9** fallback). |

## Fixes applied (summary)

- **`browseTo` + `type === "file"`:** Resolves to parent directory listing so `filePath` is never left as a **file** path (which broke **Add folder** / enumerate with `404 not a directory`).
- **`filesDirForFolderEnqueue()`:** Uses `filePath` when set; else parent of `selectedRel` so folder add works after selecting a file without changing folders.
- **Clip export:** Client requires current track to be **video/audio** (not image).

## Manual QA (Firefox + Chromium)

- Flat folder vs nested-only files (subfolder not enqueued); cap **400** from server; empty folder toast.
- **Alt+double-click:** enqueue only. **Double-click / Enter:** play now.
- Image queue: crossfade, timed + pause, fullscreen + HUD, overlay + **I**, preload smoothness on next/prev.
