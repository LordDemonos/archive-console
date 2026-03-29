"""Run folder statistics for the Process ledger (aligned with archive_*_run summary.txt).

Metric definitions (business-level, not process exit code):
- **tried** — Same as summary.txt "Attempted (approx.)": verified downloads + skipped +
  failed + private/unavailable (one count per queued video after playlist expansion).
- **ok** — Downloaded (verified) + Skipped: finished without treating the item as an
  error row (skipped = already satisfied / intentionally skipped).
- **fail** — Failed + Private / unavailable: errors or unavailable content per driver rules.
- **saved** — Downloaded (verified): media verified on disk (manifest file_verified_ok).

Invariant: ``ok + fail == tried``. Source: ``logs/archive_run_*/summary.txt`` written by
RunReporter; we avoid parsing large run.log files. ``run_summary.json`` is a small snapshot
written when the console records a completed run.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

RUN_SUMMARY_FILENAME = "run_summary.json"
RUN_SUMMARY_PARSER_VERSION = 1

# summary.txt lines, e.g. "Attempted (approx.):     200"
_RE_ATTEMPTED = re.compile(r"^Attempted\s*\(approx\.\):\s*(\d+)\s*$", re.MULTILINE)
_RE_DOWNLOADED = re.compile(r"^Downloaded\s*\(verified\):\s*(\d+)\s*$", re.MULTILINE)
_RE_SKIPPED = re.compile(r"^Skipped:\s*(\d+)\s*$", re.MULTILINE)
_RE_FAILED = re.compile(r"^Failed:\s*(\d+)\s*$", re.MULTILINE)
_RE_PRIVATE = re.compile(
    r"^Private\s*/\s*unavailable:\s*(\d+)\s*$", re.MULTILINE
)


def parse_summary_txt(text: str) -> dict[str, int] | None:
    """Parse archive driver summary.txt; return raw counters or None if not usable."""
    m_a = _RE_ATTEMPTED.search(text)
    m_d = _RE_DOWNLOADED.search(text)
    m_s = _RE_SKIPPED.search(text)
    m_f = _RE_FAILED.search(text)
    m_p = _RE_PRIVATE.search(text)
    if not all([m_a, m_d, m_s, m_f, m_p]):
        return None
    attempted = int(m_a.group(1))
    downloaded = int(m_d.group(1))
    skipped = int(m_s.group(1))
    failed = int(m_f.group(1))
    private_unavailable = int(m_p.group(1))
    check = downloaded + skipped + failed + private_unavailable
    if check != attempted:
        return None
    return {
        "attempted": attempted,
        "downloaded": downloaded,
        "skipped": skipped,
        "failed": failed,
        "private_unavailable": private_unavailable,
    }


def ledger_stats_from_raw(raw: dict[str, int]) -> dict[str, int]:
    """Map raw summary counters to ledger fields (tried, ok, fail, saved)."""
    d = raw["downloaded"]
    sk = raw["skipped"]
    return {
        "tried": raw["attempted"],
        "saved": d,
        "ok": d + sk,
        "fail": raw["failed"] + raw["private_unavailable"],
    }


def validate_ledger_stats(stats: dict[str, int]) -> bool:
    return stats["ok"] + stats["fail"] == stats["tried"]


def parse_summary_txt_file(path: Path) -> dict[str, int] | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    raw = parse_summary_txt(text)
    if raw is None:
        return None
    return ledger_stats_from_raw(raw)


def public_run_stats(blob: Any) -> dict[str, int] | None:
    """Return only the four integers for API/UI, or None."""
    if not isinstance(blob, dict):
        return None
    keys = ("tried", "ok", "fail", "saved")
    if not all(isinstance(blob.get(k), int) and blob.get(k) >= 0 for k in keys):
        return None
    st = {k: int(blob[k]) for k in keys}
    if not validate_ledger_stats(st):
        return None
    return st


def read_run_summary_json(path: Path) -> dict[str, int] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    if int(data.get("parser_version", 0)) < 1:
        return None
    return public_run_stats(
        {k: data.get(k) for k in ("tried", "ok", "fail", "saved")}
    )


def load_run_stats_for_log_folder(archive_root: Path, log_folder_rel: str) -> dict[str, int] | None:
    """Load stats from run_summary.json or summary.txt under the run folder."""
    folder = (archive_root / Path(log_folder_rel)).resolve()
    try:
        folder.relative_to(archive_root.resolve())
    except ValueError:
        return None
    js = folder / RUN_SUMMARY_FILENAME
    if js.is_file():
        got = read_run_summary_json(js)
        if got is not None:
            return got
    return parse_summary_txt_file(folder / "summary.txt")


def write_run_summary_json(log_folder: Path, stats: dict[str, int]) -> None:
    """Write canonical snapshot; callers should only pass validated public stats."""
    payload = {
        "parser_version": RUN_SUMMARY_PARSER_VERSION,
        "written_unix": time.time(),
        "tried": stats["tried"],
        "ok": stats["ok"],
        "fail": stats["fail"],
        "saved": stats["saved"],
    }
    path = log_folder / RUN_SUMMARY_FILENAME
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def merge_run_summary_into_history_entry(
    archive_root: Path, entry: dict[str, Any]
) -> dict[str, Any]:
    """
    If log_folder_rel resolves and summary data exists, set entry['run_stats'] and
    write run_summary.json. Otherwise omit run_stats (caller may normalize to null).
    """
    rel = entry.get("log_folder_rel")
    if not rel or not isinstance(rel, str):
        return entry
    folder = (archive_root / Path(rel)).resolve()
    try:
        folder.relative_to(archive_root.resolve())
    except ValueError:
        return entry
    raw_path = folder / "summary.txt"
    raw_txt = None
    try:
        raw_txt = raw_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        pass
    raw_counts = parse_summary_txt(raw_txt) if raw_txt else None
    if raw_counts is None:
        return entry
    stats = ledger_stats_from_raw(raw_counts)
    if not validate_ledger_stats(stats):
        return entry
    try:
        write_run_summary_json(folder, stats)
    except OSError:
        pass
    out = dict(entry)
    out["run_stats"] = stats
    return out


def enrich_history_entry_for_api(
    archive_root: Path, entry: dict[str, Any]
) -> dict[str, Any]:
    """Attach run_stats for GET /api/history (state row + disk backfill)."""
    out = dict(entry)
    pub = public_run_stats(out.get("run_stats"))
    if pub is not None:
        out["run_stats"] = pub
        return out
    rel = out.get("log_folder_rel")
    if not rel:
        out["run_stats"] = None
        return out
    loaded = load_run_stats_for_log_folder(archive_root, rel)
    out["run_stats"] = loaded
    return out
