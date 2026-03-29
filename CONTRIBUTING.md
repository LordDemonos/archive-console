# Contributing

This snapshot is meant to be forked or copied without the operator’s local paths,
cookies, or download trees.

## Setup

1. Clone or unpack the repository and `cd` into the repo root (`<ARCHIVE_ROOT>`).
2. Install **yt-dlp** (this snapshot does not ship `yt-dlp.exe`). Use `python -m pip install "yt-dlp[default]"` or your preferred method; the batch drivers invoke **Python** + **yt-dlp** the same way as a typical **pip** install.
3. Create `channels_input.txt`, `playlists_input.txt`, and `videos_input.txt` from the
   `*.sample.txt` files (one URL or `youtube id` per line; see comments in samples).
4. Copy `cookies.txt.example` to `cookies.txt` and add real Netscape-format cookies,
   or adjust `yt-dlp.conf` to use `--cookies-from-browser` (see yt-dlp docs).
5. Install Python 3.10+ on PATH. For **Archive Console**:
   - Run `start_archive_console.bat` once (creates `archive_console\.venv` and installs requirements).
   - Optional: copy `archive_console/state.json.example` to `archive_console/state.json` or let the UI create state on first run.
6. Set **Archive Console** archive root in the UI if needed (empty string = parent of `archive_console`).

## Tests (Archive Console)

From `archive_console/`, with the venv created by `start_archive_console.bat` activated:

```text
python -m pytest
```

Or: `archive_console\.venv\Scripts\python.exe -m pytest` from the `archive_console` directory.

## Third-party / disclaimer

This project is **not affiliated with YouTube, Google, or yt-dlp**. You provide your own
yt-dlp install and configuration; respect site terms of service and applicable law.
