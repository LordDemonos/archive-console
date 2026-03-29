"""
Idempotent publish: copy selected tree from SOURCE to DEST with text redaction.
Does not modify SOURCE. Safe to re-run (overwrites DEST files).

Usage:
  python tools/publish_staging.py
  python tools/publish_staging.py --source "D:\\my\\scripts" --dest "D:\\my\\scripts__publish_staging"
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

# Text file suffixes to run through redaction (UTF-8 with fallback).
REDACT_SUFFIXES = {
    ".bat",
    ".cmd",
    ".md",
    ".txt",
    ".conf",
    ".py",
    ".ps1",
    ".json",
    ".html",
    ".css",
    ".js",
    ".toml",
    ".yml",
    ".yaml",
    ".ini",
}

SKIP_DIR_NAMES = frozenset(
    {".git", ".venv", "__pycache__", ".pytest_cache", "node_modules", ".mypy_cache", ".idea"}
)

# Top-level dirs that are operator data / heavy artifacts
SKIP_TOP_LEVEL_DIRS = frozenset(
    {
        "logs",
        "playlists",
        "channels",
        "videos",
        "canvas",
        "test",
        # Local-only bundles / scratch (not part of core console + monthly drivers)
        "Archivist Scripts",
        "Audio-Only Scripts",
        "Watch Scripts",
    }
)

# Root-level filenames always excluded (secrets, vendored binaries, local inputs).
EXCLUDE_ROOT_NAMES = frozenset(
    {
        "credentials.json",
        "remove_wl_token.json",
        "test_input.txt",
        "yt-dlp.exe",
        "yt-dlp_x86.exe",
    }
)


def _skip_dir(rel: Path) -> bool:
    parts = rel.parts
    if any(p in SKIP_DIR_NAMES for p in parts):
        return True
    if parts and parts[0] in SKIP_TOP_LEVEL_DIRS:
        return True
    if len(parts) >= 2 and parts[0] == "archive_console" and parts[1] == "backups":
        return True
    return False


def _exclude_file(rel: Path) -> tuple[bool, str]:
    name = rel.name
    if len(rel.parts) == 1 and name in EXCLUDE_ROOT_NAMES:
        return True, "secrets, vendored binary, or local-only input (see manifest)"
    if name == "cookies.txt":
        return True, "secret / session (ship cookies.txt.example)"
    if name == "state.json" and rel.parts[:1] == ("archive_console",):
        return True, "local UI state paths/history (use state.example.json)"
    if name == "yt_dlp_ui_state.json":
        return True, "local editor UI state"
    if name == ".env":
        return True, "may contain secrets (use .env.example if needed)"
    if name.endswith("_downloaded.txt"):
        return True, "operator download-archive state"
    if name.endswith("_backup.txt"):
        return True, "backup of operator state"
    if rel in {
        Path("channels_input.txt"),
        Path("playlists_input.txt"),
        Path("videos_input.txt"),
    }:
        return True, "operator URL lists (ship *.sample.txt)"
    return False, ""


def _archive_root_variants(source_root: Path) -> list[str]:
    root = source_root.resolve()
    out: list[str] = []
    for base in (str(root), root.as_posix()):
        out.append(base)
        out.append(base + "\\")
        out.append(base + "/")
    # Windows drive letter case alias (e.g. e: vs E:)
    uniq: dict[str, None] = {}
    for s in out:
        if not s:
            continue
        if len(s) >= 2 and s[1] == ":":
            flipped = s[0].swapcase() + s[1:]
            uniq[flipped] = None
        uniq[s] = None
    return list(uniq.keys())


def _redact_text(text: str, source_root: Path) -> str:
    out = text
    for v in sorted(_archive_root_variants(source_root), key=len, reverse=True):
        out = out.replace(v, "<ARCHIVE_ROOT>")
    out = re.sub(r"(?i)(?<![A-Za-z0-9])[A-Za-z]:\\Users\\[^\\\r\n]+", "<USER_PROFILE>", out)
    return out


def _try_read_write_redacted(src: Path, dest: Path, source_root: Path) -> None:
    try:
        raw = src.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raw = src.read_text(encoding="utf-8", errors="replace")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(_redact_text(raw, source_root), encoding="utf-8", newline="\n")


def _copy_binary(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)


def _publish(
    source_root: Path,
    dest_root: Path,
    *,
    dry_run: bool = False,
) -> dict[str, list[str]]:
    """Copy tree. Returns manifest buckets."""
    included: list[str] = []
    excluded: list[str] = []
    if not source_root.is_dir():
        raise SystemExit(f"SOURCE not a directory: {source_root}")

    for path in source_root.rglob("*"):
        if not path.is_file():
            continue
        try:
            rel = path.relative_to(source_root)
        except ValueError:
            continue
        if _skip_dir(rel):
            continue
        ex, why = _exclude_file(rel)
        if ex:
            excluded.append(f"{rel.as_posix()} — {why}")
            continue

        dest_path = dest_root / rel
        included.append(rel.as_posix())
        if dry_run:
            continue

        if path.suffix.lower() in REDACT_SUFFIXES:
            try:
                _try_read_write_redacted(path, dest_path, source_root)
            except UnicodeDecodeError:
                _copy_binary(path, dest_path)
        else:
            _copy_binary(path, dest_path)

    return {"included": sorted(set(included)), "excluded": sorted(set(excluded))}


LICENSE_MIT = """MIT License

Copyright (c) 2026 Archive Console contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

GITIGNORE = """# Runtime / local
logs/
archive_run_*/
latest_run*.txt
cookies.txt
.env
.env.local
archive_console/state.json
archive_console/yt_dlp_ui_state.json
archive_console/.run/
archive_console/backups/
playlists/
channels/
videos/
*_downloaded.txt
*_backup.txt

# Python
__pycache__/
*.py[cod]
*$py.class
.pytest_cache/
.mypy_cache/
.venv/
venv/

# Node (if added later)
node_modules/

# Editors
.idea/
.vscode/

# OS
Thumbs.db
Desktop.ini
"""

CONTRIBUTING = """# Contributing

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
   - Run `start_archive_console.bat` once (creates `archive_console\\.venv` and installs requirements).
   - Optional: copy `archive_console/state.json.example` to `archive_console/state.json` or let the UI create state on first run.
6. Set **Archive Console** archive root in the UI if needed (empty string = parent of `archive_console`).

## Tests (Archive Console)

From `archive_console/`, with the venv created by `start_archive_console.bat` activated:

```text
python -m pytest
```

Or: `archive_console\\.venv\\Scripts\\python.exe -m pytest` from the `archive_console` directory.

## Third-party / disclaimer

This project is **not affiliated with YouTube, Google, or yt-dlp**. You provide your own
yt-dlp install and configuration; respect site terms of service and applicable law.
"""

COOKIES_EXAMPLE = """# Replace this file with cookies.txt (Netscape format) or remove this stub.
# Do not commit real cookies to git.
#
# Options:
# 1. Export cookies from your browser in Netscape format and save as cookies.txt next to yt-dlp.conf.
# 2. Or comment --cookies in yt-dlp.conf and use --cookies-from-browser (see yt-dlp documentation).
#
# This repository ships no cookie data.
"""

SAMPLE_CHANNELS = """# Sample channel / playlist lines (replace with your own). One entry per line.
# Lines starting with # are ignored by the drivers when used as input (verify drivers if you rely on this).
https://www.youtube.com/@ExampleChannelOne
https://www.youtube.com/@ExampleChannelTwo/videos
https://www.youtube.com/c/ExampleBroadcastChannel
"""

SAMPLE_PLAYLISTS = """# Sample playlist identifiers. One per line.
# Use full playlist URLs or PL... ids as supported by yt-dlp.
https://www.youtube.com/playlist?list=PLaceholder00ExamplePlaylist00
WL
https://www.youtube.com/playlist?list=PLaceholder01ExamplePlaylist01
"""

SAMPLE_VIDEOS = """# Sample video URLs. One per line.
https://www.youtube.com/watch?v=dQw4w9WgXcQ
https://youtu.be/dQw4w9WgXcQ
https://www.youtube.com/watch?v=xxxxxxxxxxx
"""

LEGACY_BAT = """@echo off
echo This legacy entrypoint is not present in the public source snapshot.
echo Use monthly_watch_later_archive.bat, monthly_channels_archive.bat, or monthly_videos_archive.bat.
echo See BAT_FILES.md and README.md.
exit /b 2
"""


def _bat_inventory(source_root: Path) -> list[str]:
    return sorted(
        p.relative_to(source_root).as_posix()
        for p in source_root.rglob("*.bat")
        if ".venv" not in p.parts and "__pycache__" not in p.parts
    )


def _write_extra_staging(dest_root: Path, source_root: Path, buckets: dict[str, list[str]]) -> None:
    (dest_root / "LICENSE").write_text(LICENSE_MIT, encoding="utf-8", newline="\n")
    (dest_root / ".gitignore").write_text(GITIGNORE, encoding="utf-8", newline="\n")
    (dest_root / "CONTRIBUTING.md").write_text(CONTRIBUTING, encoding="utf-8", newline="\n")
    (dest_root / "cookies.txt.example").write_text(COOKIES_EXAMPLE, encoding="utf-8", newline="\n")
    (dest_root / ".env.example").write_text(
        "# No secrets are required for local runs by default.\n"
        "# If you add integration keys, copy to .env (untracked) — never commit .env.\n",
        encoding="utf-8",
        newline="\n",
    )
    (dest_root / "channels_input.sample.txt").write_text(SAMPLE_CHANNELS, encoding="utf-8", newline="\n")
    (dest_root / "playlists_input.sample.txt").write_text(SAMPLE_PLAYLISTS, encoding="utf-8", newline="\n")
    (dest_root / "videos_input.sample.txt").write_text(SAMPLE_VIDEOS, encoding="utf-8", newline="\n")

    state_example = dest_root / "archive_console/state.example.json"
    if state_example.is_file():
        shutil.copy(state_example, dest_root / "archive_console/state.json.example")

    for name in ("archive_playlists.bat", "archive_playlists_robust.bat", "archive_channels.bat"):
        (dest_root / name).write_text(LEGACY_BAT, encoding="utf-8", newline="\n")

    bat_files = [
        "monthly_watch_later_archive.bat",
        "monthly_channels_archive.bat",
        "monthly_videos_archive.bat",
        "archive_playlists_advanced.bat",
        "archive_youtube_channels.bat",
        "archive_videos.bat",
        "archive_channels_robust.bat",
        "regenerate_report.bat",
        "verify_downloads.bat",
        "start_archive_console.bat",
        "start_archive_console_tray.bat",
        "archive_console/start_archive_console.bat",
        "archive_console/_launch_uvicorn.bat",
    ]

    on_disk = _bat_inventory(source_root)
    present = []
    missing = []
    for rel in bat_files:
        if (source_root / rel).is_file():
            present.append(rel)
        else:
            missing.append(rel)

    manifest_lines = [
        "# Publish manifest",
        "",
        "Anonymized snapshot for public sharing. **Do not** treat paths in this repo as the operator’s machine.",
        "",
        "## Third-party / disclaimer",
        "",
        "This project is **not affiliated with YouTube, Google LLC, or the yt-dlp project**. yt-dlp is third-party software; you install and configure it yourself and must comply with applicable site terms and laws.",
        "",
        "## BAT_FILES.md checklist (`.bat` coverage)",
        "",
        "| BAT_FILES.md entry | Staging | Note |",
        "|--------------------|---------|------|",
    ]

    def row(entry: str, staging: str, note: str) -> None:
        manifest_lines.append(f"| `{entry}` | {staging} | {note} |")

    for rel in bat_files:
        if rel in missing:
            row(rel, "absent in source", "not in this working tree")
        else:
            row(rel, "included", "from source (redacted)")

    row("archive_playlists.bat", "placeholder stub", "BAT_FILES.md legacy; not in source tree")
    row("archive_playlists_robust.bat", "placeholder stub", "same")
    row("archive_channels.bat", "placeholder stub", "same")

    manifest_lines += [
        "",
        f"- **On-disk `.bat` files scanned (excl. `.venv`):** {len(on_disk)}",
        "",
        "## Included (categories)",
        "",
        "- Root drivers: `archive_*_run.py`, `archive_run_console.py`, `archive_print_role.py`, `regenerate_report.py`, `repair_playlist_download_archive.py`, `yt-dlp.conf`",
        "- Batch entrypoints and stubs (see table)",
        "- Docs: `README.md`, `BAT_FILES.md`, `ARCHIVE_PLAYLIST_RUN_LOGS.txt`, `archive_console/ARCHIVE_CONSOLE.md`",
        "- Archive Console app: `archive_console/app/`, `templates/`, `static/`, `tests/`, `requirements.txt`, `print_bind.py`, tray sources, `state.example.json` / `state.json.example`, `*.ps1`",
        "- Tooling: `tools/publish_staging.py` (regenerate staging from a full tree)",
        "",
        "## Excluded (why)",
        "",
    ]
    for line in buckets["excluded"]:
        manifest_lines.append(f"- `{line}`")

    manifest_lines += [
        "",
        "### Excluded — entire directory classes",
        "",
        "- `logs/` — run outputs",
        "- `playlists/`, `channels/`, `videos/`, top-level `test/` — download trees / scratch",
        "- `Archivist Scripts/`, `Audio-Only Scripts/`, `Watch Scripts/` — local bundles not in core publish set",
        "- Root `credentials.json`, `remove_wl_token.json`, `yt-dlp.exe`, `yt-dlp_x86.exe`, `test_input.txt`",
        "- `.venv/`, `__pycache__/`, `.pytest_cache/` — environments",
        "- `archive_console/backups/` — may contain copies of operator inputs",
        "",
        "## Generated at runtime (do not ship from operator disk)",
        "",
        "- `logs/archive_run_*`, `latest_run*.txt`, `run_summary.json`, etc.",
        "- `*_downloaded.txt`, `*_backup.txt`",
        "- `archive_console/state.json`, `archive_console/yt_dlp_ui_state.json`",
        "- `cookies.txt`",
        "",
        "## Reproduce this staging folder",
        "",
        "```bat",
        "cd <ARCHIVE_ROOT>",
        "python tools\\publish_staging.py",
        "```",
        "",
        "Default destination: sibling `<ARCHIVE_ROOT>__publish_staging`.",
    ]

    (dest_root / "PUBLISH_MANIFEST.md").write_text("\n".join(manifest_lines) + "\n", encoding="utf-8")


def _append_readme_public(dest_root: Path) -> None:
    readme = dest_root / "README.md"
    if not readme.is_file():
        return
    block = """

---

## Public snapshot notes

- Replace machine-specific roots with `<ARCHIVE_ROOT>` in your mind: working directory is the folder that contains `yt-dlp.conf` and the `monthly_*.bat` files.
- Copy `*.sample.txt` to `channels_input.txt`, `playlists_input.txt`, and `videos_input.txt` before running batch jobs.
- See **`CONTRIBUTING.md`**, **`PUBLISH_MANIFEST.md`**, and **`cookies.txt.example`**.

**Third-party / disclaimer:** this project is **not affiliated with YouTube, Google LLC, or yt-dlp**. You supply yt-dlp and obey site terms of service.

"""
    text = readme.read_text(encoding="utf-8")
    if "Public snapshot notes" not in text:
        readme.write_text(text.rstrip() + block, encoding="utf-8", newline="\n")


def main() -> None:
    ap = argparse.ArgumentParser(description="Build anonymized publish staging tree.")
    ap.add_argument(
        "--source",
        type=Path,
        default=None,
        help="Source repo root (default: parent of tools/)",
    )
    ap.add_argument(
        "--dest",
        type=Path,
        default=None,
        help="Destination (default: <source> sibling __publish_staging)",
    )
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    script_dir = Path(__file__).resolve().parent
    source_root = (args.source or script_dir.parent).resolve()
    if args.dest:
        dest_root = args.dest.resolve()
    else:
        dest_root = source_root.parent / f"{source_root.name}__publish_staging"

    dry = args.dry_run
    if not dry:
        if dest_root.exists():
            shutil.rmtree(dest_root)
        dest_root.mkdir(parents=True, exist_ok=True)

    buckets = _publish(source_root, dest_root, dry_run=dry)
    if dry:
        print(f"DRY-RUN: would write to {dest_root}")
        print(f"included files: {len(buckets['included'])}")
        return

    _write_extra_staging(dest_root, source_root, buckets)
    _append_readme_public(dest_root)
    print(f"Wrote staging to {dest_root}")


if __name__ == "__main__":
    main()
