#!/usr/bin/env python3
"""
Gallery batch driver (Archive Console). Invokes gallery-dl as a subprocess; writes
per-run logs under logs/archive_run_<UTC>/ (manifest, issues, summary, report).

Spike / CLI notes (verify with your installed gallery-dl: gallery-dl --help):
- Preview (no files on disk): gallery-dl -s -j <URL>  (-s/--simulate extracts metadata only;
  -j/--dump-json prints one JSON object per line to stdout). Still performs HTTP requests.
- Run (download): gallery-dl -o <dest> <URL>  (omit -s). Optional: -c gallery-dl.conf,
  --cookies cookies.txt (Netscape, same file as yt-dlp often uses for Reddit NSFW/private).
- Reddit user "all submissions": gallery-dl typically expects .../user/NAME/submitted/ ;
  bare /user/NAME/ may behave differently — normalize host to www.reddit.com in the console API.

Env (set by Archive Console):
  ARCHIVE_GALLERY_URL          Target URL (normalized)
  ARCHIVE_OUT_GALLERIES        Output root; files go under <root>/gallery_<log_stamp>/
  ARCHIVE_GALLERY_DL_EXE       gallery-dl executable (default: gallery-dl on PATH)
  ARCHIVE_GALLERY_PREVIEW_JSON Path to preview_snapshot.json (optional)
  ARCHIVE_GALLERY_VIDEO_FALLBACK  Set to 1 to run yt-dlp on v.redd.it URLs still missing files
  ARCHIVE_DRY_RUN              If set, gallery-dl runs with -s only (no media files written)
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from archive_playlist_run import RunReporter
from archive_run_console import emit_driver_start_banner, emit_final_summary, init_console, print_role

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def _write_latest_gallery_pointer(log_dir: str) -> None:
    latest_path = os.path.join(SCRIPT_DIR, "logs", "latest_run_galleries.txt")
    try:
        with open(latest_path, "w", encoding="utf-8") as lf:
            lf.write(log_dir + "\n")
    except OSError:
        pass


def _gallery_dl_exe() -> str:
    return (os.environ.get("ARCHIVE_GALLERY_DL_EXE") or "gallery-dl").strip() or "gallery-dl"


def _cookies_path() -> str | None:
    p = os.path.join(SCRIPT_DIR, "cookies.txt")
    return p if os.path.isfile(p) else None


def _conf_path() -> str | None:
    p = os.path.join(SCRIPT_DIR, "gallery-dl.conf")
    return p if os.path.isfile(p) else None


def _load_preview_rows(path: str | None) -> tuple[list[dict], int]:
    if not path or not os.path.isfile(path):
        return [], 0
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [], 0
    rows = data.get("rows") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return [], 0
    return rows, len(rows)


def _v_reddit_urls_from_preview(rows: list[dict]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for r in rows:
        for u in r.get("media_urls") or []:
            if not isinstance(u, str):
                continue
            if "v.redd.it" in u and u not in seen:
                seen.add(u)
                out.append(u)
    return out


def _walk_files(root: str) -> list[str]:
    paths: list[str] = []
    if not os.path.isdir(root):
        return paths
    for dirpath, _dirnames, filenames in os.walk(root):
        for fn in filenames:
            paths.append(os.path.join(dirpath, fn))
    return sorted(paths)


def _file_maybe_for_vreddit(paths: list[str], vurl: str) -> bool:
    """Heuristic: v.redd.it/<id> often appears in filename or path."""
    m = re.search(r"v\.redd\.it/([^/?#]+)", vurl)
    if not m:
        return False
    vid = m.group(1)
    for p in paths:
        if vid in p.replace("\\", "/"):
            return True
    return False


def _run_ytdlp_fallback(
    urls: list[str],
    dest_dir: str,
    log_append_path: str,
) -> dict:
    if not urls:
        return {"ran": False, "urls": [], "exit_code": None, "message": "no_urls"}
    ytc = [sys.executable, "-m", "yt_dlp", "--no-playlist"]
    ck = _cookies_path()
    if ck:
        ytc.extend(["--cookies", ck])
    ytc.extend(["-o", os.path.join(dest_dir, "%(title).200B [%(id)s].%(ext)s")])
    ytc.extend(urls)
    try:
        proc = subprocess.run(
            ytc,
            cwd=SCRIPT_DIR,
            capture_output=True,
            text=True,
            timeout=3600,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        with open(log_append_path, "a", encoding="utf-8") as af:
            af.write(f"\n[archive_gallery_run] yt-dlp fallback failed to run: {e}\n")
        return {"ran": True, "urls": urls, "exit_code": -1, "message": str(e)}
    with open(log_append_path, "a", encoding="utf-8") as af:
        af.write("\n--- yt-dlp fallback ---\n")
        af.write(proc.stdout or "")
        af.write(proc.stderr or "")
    return {
        "ran": True,
        "urls": urls,
        "exit_code": proc.returncode,
        "message": "ok" if proc.returncode == 0 else "yt_dlp_nonzero",
    }


def main() -> int:
    os.chdir(SCRIPT_DIR)
    init_console()

    url = (os.environ.get("ARCHIVE_GALLERY_URL") or "").strip()
    out_root = (os.environ.get("ARCHIVE_OUT_GALLERIES") or "").strip()
    preview_json = (os.environ.get("ARCHIVE_GALLERY_PREVIEW_JSON") or "").strip()
    dry = _env_truthy("ARCHIVE_DRY_RUN")
    want_fallback = _env_truthy("ARCHIVE_GALLERY_VIDEO_FALLBACK")

    log_stamp = sys.argv[1] if len(sys.argv) > 1 else None
    if not log_stamp:
        log_stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    log_dir = os.path.join(SCRIPT_DIR, "logs", f"archive_run_{log_stamp}")
    os.makedirs(log_dir, exist_ok=True)

    reporter = RunReporter(
        log_dir,
        archive_path=os.path.join(SCRIPT_DIR, "playlists_downloaded.txt"),
        summary_heading="Archive gallery-dl run summary (UTC)",
        archive_sync_log_prefix="[archive_gallery_run]",
        skip_download_archive_sync=True,
    )

    emit_driver_start_banner(
        reporter,
        title="Archive Galleries (gallery-dl)",
        subtitle="Console-driven; see summary.txt / report.html",
    )

    preview_rows, preview_n = _load_preview_rows(preview_json or None)
    if preview_json and os.path.isfile(preview_json):
        try:
            snap_dst = os.path.join(log_dir, "preview_snapshot.json")
            Path(snap_dst).write_text(
                Path(preview_json).read_text(encoding="utf-8"), encoding="utf-8"
            )
        except OSError:
            pass

    if not url:
        reporter.record_issue("fatal", "", "", "", "ARCHIVE_GALLERY_URL is empty", "")
        reporter.close()
        reporter.finalize()
        _write_latest_gallery_pointer(log_dir)
        emit_final_summary(
            log_dir=log_dir,
            log_stamp=log_stamp,
            report_path=reporter.report_path,
            rc=1,
            driver_label="archive_gallery_run",
            pointer_lines=["Galleries pointer: logs\\latest_run_galleries.txt"],
        )
        return 1

    if not out_root:
        reporter.record_issue("fatal", "", "", "", "ARCHIVE_OUT_GALLERIES is empty", url)
        reporter.close()
        reporter.finalize()
        _write_latest_gallery_pointer(log_dir)
        emit_final_summary(
            log_dir=log_dir,
            log_stamp=log_stamp,
            report_path=reporter.report_path,
            rc=1,
            driver_label="archive_gallery_run",
            pointer_lines=["Galleries pointer: logs\\latest_run_galleries.txt"],
        )
        return 1

    dest_dir = os.path.join(out_root, f"gallery_{log_stamp}")
    os.makedirs(dest_dir, exist_ok=True)

    exe = _gallery_dl_exe()
    cmd: list[str] = [exe]
    cp = _conf_path()
    if cp:
        cmd.extend(["-c", cp])
    ck = _cookies_path()
    if ck:
        cmd.extend(["--cookies", ck])
    cmd.extend(["-o", dest_dir])
    if dry:
        cmd.append("-s")
    cmd.append(url)

    reporter.log_line(f"[archive_gallery_run] cmd: {subprocess.list2cmdline(cmd)}")
    reporter.log_line(f"[archive_gallery_run] URL: {url}")
    reporter.log_line(f"[archive_gallery_run] destination: {dest_dir}")

    rc = 1
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=SCRIPT_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            reporter.log_line(line.rstrip("\r\n"))
        rc = proc.wait()
    except FileNotFoundError:
        reporter.record_issue(
            "fatal",
            "",
            "",
            "",
            f"gallery-dl executable not found: {exe!r} (install gallery-dl or set ARCHIVE_GALLERY_DL_EXE)",
            url,
        )
        rc = 127
    except OSError as e:
        reporter.record_issue("fatal", "", "", "", repr(e), url)
        rc = 1

    if rc != 0:
        reporter.record_issue(
            "failed",
            "",
            "",
            "",
            f"gallery-dl exited with code {rc}",
            url,
        )

    paths_after = _walk_files(dest_dir)

    fb_info: dict = {"ran": False, "urls": [], "exit_code": None}
    if want_fallback and not dry and preview_rows:
        vurls = _v_reddit_urls_from_preview(preview_rows)
        pending = [u for u in vurls if not _file_maybe_for_vreddit(paths_after, u)]
        if pending:
            reporter.log_line(
                f"[archive_gallery_run] yt-dlp fallback for {len(pending)} v.redd.it URL(s)"
            )
            fb_info = _run_ytdlp_fallback(pending, dest_dir, reporter.run_log_path)

    paths_final = _walk_files(dest_dir)
    for fp in paths_final:
        try:
            sz = int(os.path.getsize(fp))
        except OSError:
            continue
        rel = os.path.relpath(fp, dest_dir).replace("\\", "/")
        vid = hashlib.sha256(rel.encode()).hexdigest()[:16]
        reporter.record_manifest_row(
            vid,
            os.path.basename(fp),
            os.path.abspath(fp),
            sz,
            "",
            url,
            "gallery-dl",
        )

    if dry and not paths_final:
        reporter.record_issue(
            "warning",
            "",
            "",
            "",
            "ARCHIVE_DRY_RUN: gallery-dl ran with -s (simulate); no media files written. Use Preview for metadata.",
            url,
        )

    verification = {
        "preview_row_count": preview_n,
        "files_on_disk": len(paths_final),
        "paths_sample": [p.replace("\\", "/") for p in paths_final[:200]],
        "truncated_paths": len(paths_final) > 200,
        "yt_dlp_fallback": fb_info,
    }
    try:
        Path(os.path.join(log_dir, "verification.json")).write_text(
            json.dumps(verification, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError:
        pass

    reporter.close()
    reporter.finalize()

    _write_latest_gallery_pointer(log_dir)

    final_rc = 0 if rc == 0 else rc
    if final_rc == 0 and not paths_final and not dry:
        final_rc = 1

    emit_final_summary(
        log_dir=log_dir,
        log_stamp=log_stamp,
        report_path=reporter.report_path,
        rc=final_rc,
        driver_label="archive_gallery_run",
        pointer_lines=["Galleries pointer: logs\\latest_run_galleries.txt"],
    )

    if final_rc != 0:
        print_role(f"[archive_gallery_run] finished with exit {final_rc}", "warn")
    return final_rc


if __name__ == "__main__":
    raise SystemExit(main())
