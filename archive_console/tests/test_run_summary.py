"""Tests for Process ledger run_stats (summary.txt / run_summary.json)."""

from __future__ import annotations

import json
from pathlib import Path

from app.run_summary import (
    enrich_history_entry_for_api,
    ledger_stats_from_raw,
    merge_run_summary_into_history_entry,
    parse_summary_txt,
    public_run_stats,
    read_run_summary_json,
    validate_ledger_stats,
    write_run_summary_json,
)

FIXTURE_PLAYLIST = """Archive playlist run summary (UTC)
================================

Attempted (approx.):     200
Downloaded (verified):   22
Skipped:                 15
Failed:                  160
Private / unavailable:   3

Notes:
"""

FIXTURE_VIDEO = """Archive video run summary (UTC)
================================

Attempted (approx.):     3
Downloaded (verified):   1
Skipped:                 1
Failed:                  1
Private / unavailable:   0

Notes:
"""

FIXTURE_MISMATCH = """Archive playlist run summary (UTC)
================================

Attempted (approx.):     10
Downloaded (verified):   1
Skipped:                 1
Failed:                  1
Private / unavailable:   0

Notes:
"""


def test_parse_summary_and_ledger_invariant():
    raw = parse_summary_txt(FIXTURE_VIDEO)
    assert raw is not None
    st = ledger_stats_from_raw(raw)
    assert st == {"tried": 3, "saved": 1, "ok": 2, "fail": 1}
    assert validate_ledger_stats(st)

    raw2 = parse_summary_txt(FIXTURE_PLAYLIST)
    assert raw2 is not None
    st2 = ledger_stats_from_raw(raw2)
    assert st2["tried"] == 200
    assert st2["ok"] == 37
    assert st2["fail"] == 163
    assert st2["saved"] == 22
    assert validate_ledger_stats(st2)


def test_parse_rejects_bad_sum():
    assert parse_summary_txt(FIXTURE_MISMATCH) is None


def test_merge_writes_json_and_entry(tmp_path: Path):
    logs = tmp_path / "logs" / "archive_run_test123"
    logs.mkdir(parents=True)
    (logs / "summary.txt").write_text(FIXTURE_VIDEO, encoding="utf-8")
    entry = {"log_folder_rel": "logs/archive_run_test123", "run_id": "x"}
    out = merge_run_summary_into_history_entry(tmp_path, entry)
    assert out["run_stats"]["tried"] == 3
    assert out["run_stats"]["saved"] == 1
    js = logs / "run_summary.json"
    assert js.is_file()
    data = json.loads(js.read_text(encoding="utf-8"))
    assert data["parser_version"] == 1
    assert data["tried"] == 3


def test_enrich_from_json_roundtrip(tmp_path: Path):
    logs = tmp_path / "logs" / "archive_run_x"
    logs.mkdir(parents=True)
    write_run_summary_json(logs, {"tried": 5, "ok": 3, "fail": 2, "saved": 2})
    row = enrich_history_entry_for_api(
        tmp_path,
        {"log_folder_rel": "logs/archive_run_x"},
    )
    assert row["run_stats"] == {"tried": 5, "ok": 3, "fail": 2, "saved": 2}


def test_enrich_backfills_summary_txt(tmp_path: Path):
    logs = tmp_path / "logs" / "archive_run_y"
    logs.mkdir(parents=True)
    (logs / "summary.txt").write_text(FIXTURE_VIDEO, encoding="utf-8")
    row = enrich_history_entry_for_api(
        tmp_path,
        {"log_folder_rel": "logs/archive_run_y"},
    )
    assert row["run_stats"]["tried"] == 3


def test_public_run_stats_invalid():
    assert public_run_stats({"tried": 1, "ok": 1, "fail": 1, "saved": 0}) is None


def test_read_run_summary_json(tmp_path: Path):
    p = tmp_path / "run_summary.json"
    p.write_text(
        json.dumps(
            {
                "parser_version": 1,
                "written_unix": 1,
                "tried": 2,
                "ok": 2,
                "fail": 0,
                "saved": 1,
            }
        ),
        encoding="utf-8",
    )
    assert read_run_summary_json(p) == {
        "tried": 2,
        "ok": 2,
        "fail": 0,
        "saved": 1,
    }
