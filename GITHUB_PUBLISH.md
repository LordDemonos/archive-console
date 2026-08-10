# Publishing to GitHub

Public repo: https://github.com/LordDemonos/archive-console

This tree is an **anonymized snapshot**. Rebuild it from the operator’s full working copy with `tools/publish_staging.py` — do not hand-copy secrets, logs, or download folders.

## Workflow

1. From the private scripts root (the tree with real cookies and downloads):

```bat
python tools\\publish_staging.py --dest <STAGING_DEST>
```

Replace `<STAGING_DEST>` with a clean folder outside your private download trees.

2. Prefer publishing **into** an existing git clone of **archive-console** so `.git` is preserved:

```bat
python tools\\publish_staging.py --dest <path-to-archive-console-clone>
```

`publish_staging.py` clears DEST contents but **keeps `.git`**. Alternatively publish to a temp folder and copy over a clone while leaving `.git` alone.

3. Review `git status`. Confirm none of these appear as new/changed tracked files:

- `cookies.txt`, `credentials.json`, `*_downloaded.txt`, `logs/`
- `playlists/`, `channels/`, `videos/`, `galleries/`, `oneoff/`, `cookies/`
- `yt-dlp.exe`, `archive_console/state.json`, gallery-dl debug captures (`_gdl_*.txt`, `gdl_*.txt`)

4. Commit and push to `main`.

## Generated files

Each staging run overwrites generated docs in the output folder:

- `CONTRIBUTING.md`, `PUBLISH_MANIFEST.md`, `LICENSE`
- `cookies.txt.example`, `.env.example`, `*.sample.txt`
- Placeholder legacy `.bat` stubs (`archive_playlists.bat`, etc.)

See **`PUBLISH_MANIFEST.md`** for the authoritative include/exclude list.
