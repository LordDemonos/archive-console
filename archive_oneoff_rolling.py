"""Rolling one-off report: jsonl append + HTML regen + retention rotation (Archive Console)."""

from __future__ import annotations

import html
import json
import os
import re
import shutil
import time
from datetime import datetime, timezone
from typing import Any

_SAFE_NAME = re.compile(r"[^\w.\-]+")


def oneoff_report_dir(script_dir: str) -> str:
    return os.path.join(script_dir, "logs", "oneoff_report")


def meta_path(script_dir: str) -> str:
    return os.path.join(oneoff_report_dir(script_dir), "meta.json")


def summary_jsonl_path(script_dir: str) -> str:
    return os.path.join(oneoff_report_dir(script_dir), "summary.jsonl")


def report_html_path(script_dir: str) -> str:
    return os.path.join(oneoff_report_dir(script_dir), "report.html")


def _read_meta(script_dir: str) -> dict[str, Any]:
    p = meta_path(script_dir)
    if not os.path.isfile(p):
        return {}
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _write_meta(script_dir: str, data: dict[str, Any]) -> None:
    d = oneoff_report_dir(script_dir)
    os.makedirs(d, exist_ok=True)
    with open(meta_path(script_dir), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def rotate_if_needed(script_dir: str, retention_days: int) -> None:
    """Archive current report/jsonl when epoch age exceeds retention_days."""
    if retention_days < 1:
        retention_days = 90
    d = oneoff_report_dir(script_dir)
    meta = _read_meta(script_dir)
    now = time.time()
    epoch = float(meta.get("epoch_start_unix") or 0.0)
    if epoch <= 0:
        _write_meta(
            script_dir,
            {
                "epoch_start_unix": now,
                "epoch_start_utc": datetime.now(timezone.utc).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                ),
            },
        )
        return
    age_sec = now - epoch
    if age_sec <= retention_days * 86400:
        return

    stamp = datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y%m%d")
    if os.path.isdir(d):
        rp = report_html_path(script_dir)
        if os.path.isfile(rp):
            dest = os.path.join(d, f"report_{stamp}.html")
            base, ext = dest.rsplit(".", 1) if "." in dest else (dest, "")
            n = 0
            while os.path.isfile(dest):
                n += 1
                dest = f"{base}_{n}.html" if ext else f"{base}_{n}"
            try:
                shutil.move(rp, dest)
            except OSError:
                pass
        sp = summary_jsonl_path(script_dir)
        if os.path.isfile(sp):
            dest_j = os.path.join(d, f"summary_{stamp}.jsonl")
            n = 0
            while os.path.isfile(dest_j):
                n += 1
                dest_j = os.path.join(d, f"summary_{stamp}_{n}.jsonl")
            try:
                shutil.move(sp, dest_j)
            except OSError:
                pass
    _write_meta(
        script_dir,
        {
            "epoch_start_unix": now,
            "epoch_start_utc": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
            "rotated_from_utc": meta.get("epoch_start_utc"),
        },
    )


def _load_entries(script_dir: str) -> list[dict[str, Any]]:
    p = summary_jsonl_path(script_dir)
    if not os.path.isfile(p):
        return []
    rows: list[dict[str, Any]] = []
    with open(p, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def append_entry(script_dir: str, entry: dict[str, Any]) -> None:
    d = oneoff_report_dir(script_dir)
    os.makedirs(d, exist_ok=True)
    p = summary_jsonl_path(script_dir)
    line = json.dumps(entry, ensure_ascii=False)
    with open(p, "a", encoding="utf-8") as af:
        af.write(line + "\n")
    entries = _load_entries(script_dir)
    _write_report_html(script_dir, entries)


def _write_report_html(script_dir: str, entries: list[dict[str, Any]]) -> None:
    rows: list[str] = []
    for e in reversed(entries):
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(e.get('completed_utc', '')))}</td>"
            f"<td>{html.escape(str(e.get('url', '')))}</td>"
            f"<td>{html.escape(str(e.get('outcome', '')))}</td>"
            f"<td>{html.escape(str(e.get('exit_code', '')))}</td>"
            f"<td>{html.escape(str(e.get('bytes', '')))}</td>"
            f"<td>{html.escape(str(e.get('media_path', '')))}</td>"
            f"<td>{html.escape(str(e.get('error_snippet', '')))}</td>"
            f"<td>{html.escape(str(e.get('log_folder', '')))}</td>"
            "</tr>"
        )
    body = "\n".join(rows) if rows else "<tr><td colspan='8'>No entries yet.</td></tr>"
    title = "Archive Console — one-off rolling report"
    html_out = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/><title>{title}</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 1rem; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border: 1px solid #ccc; padding: 0.35rem 0.5rem; font-size: 0.9rem; vertical-align: top; }}
th {{ background: #f0f0f0; text-align: left; }}
.muted {{ color: #555; font-size: 0.85rem; }}
</style></head><body>
<h1>{title}</h1>
<p class="muted">Appended by archive_oneoff_run.py. Retention rotation is configured in Archive Console Settings.</p>
<table>
<thead><tr>
<th>Completed (UTC)</th><th>URL</th><th>Outcome</th><th>Exit</th><th>Bytes</th><th>Media path</th><th>Error</th><th>Run folder</th>
</tr></thead>
<tbody>
{body}
</tbody>
</table>
</body></html>
"""
    outp = report_html_path(script_dir)
    with open(outp, "w", encoding="utf-8") as f:
        f.write(html_out)


def rolling_stats(entries: list[dict[str, Any]]) -> dict[str, Any]:
    ok = sum(1 for e in entries if e.get("outcome") == "ok")
    fail = sum(1 for e in entries if e.get("outcome") == "fail")
    last = entries[-1] if entries else {}
    return {
        "total": len(entries),
        "ok": ok,
        "fail": fail,
        "last_url": last.get("url", ""),
        "last_completed_utc": last.get("completed_utc", ""),
        "last_outcome": last.get("outcome", ""),
    }
