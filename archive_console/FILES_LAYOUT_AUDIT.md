# Library workspace layout audit

## DOM chain (Library tab)

`body` → `.shell` (flex row) → `main.main` → (banners) → `#view-library` → `header.view-head` → `.card.files-layout` → `#filesWorkspace.files-workspace` → `#filesWorkspaceShell.files-workspace-shell` → `.files-workspace-split-wrap` → `#filesSplit.files-split` (grid) → `.files-detail-stack` → `#filesPlayer.files-player` → `#filesVideoFrame.files-player-video-frame` → `#filesVideo.files-player-video`

## Binding constraint (root cause)

**The first ancestor that prevented the workspace from growing with the window was the combination of:**

1. **`main.main`** — `display` was not flex; **`#view-library`** (formerly `#view-files`) was `display: block` like other views, so the Library route had **no `flex: 1; min-height: 0`** path to consume **remaining viewport height** below the header and banners.
2. **`.files-workspace`** — used a **standalone `height` / `max-height` based on `100vh`**, decoupled from the **actual** height available inside **`main` padding + view-head + card chrome**. Tuning `fpUpdateVideoFrameLayout` could not fix “dead band” or a short player column because **`getBoundingClientRect().height` on `.files-workspace`** did not track “fill main to bottom” — it tracked a **fixed vh recipe** that did not participate in the flex column.

**Secondary:** **`.files-player`** used **`overflow-y: auto`**, so the whole player (including the video) could scroll; combined with a **fixed `reserveNonVideo` constant** in JS, **`maxH` for the video frame** was often misestimated versus real chrome.

## Fix summary (architecture)

- **`main`**: flex column, `min-height: 100vh`, so the active Files view can use `flex: 1; min-height: 0`.
- **`#view-library.is-active`**: flex column + `flex: 1; min-height: 0`; **`.files-layout`**: `flex: 1; min-height: 0`.
- **`#filesWorkspaceShell`**: **fixed pixel height** for both columns (`--files-workspace-height`, JS + **`files.workspace.height`**). **`.files-workspace`**: **`flex: 0 0 auto`** — outer height is **not** derived from list `scrollHeight`.
- **`.files-workspace-resize-y`**: vertical drag (**`ns-resize`**) adjusts the shell; window **resize** reclamps.
- **`.files-player`**: **overflow-y: hidden**; queue scrolls. **`fpUpdateVideoFrameLayout`**: **`maxH` from measured chrome + queue `min-height`**.
