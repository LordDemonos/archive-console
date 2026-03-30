"""Rolling one-off report rotation."""

from __future__ import annotations

import json
from pathlib import Path

import archive_oneoff_rolling as rolling


def test_rotate_archives_when_epoch_old(tmp_path: Path, monkeypatch) -> None:
    sd = str(tmp_path)
    rolling.rotate_if_needed(sd, 90)
    meta_path = Path(sd) / "logs" / "oneoff_report" / "meta.json"
    assert meta_path.is_file()
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    old_epoch = 1_000_000.0
    meta["epoch_start_unix"] = old_epoch
    meta_path.write_text(json.dumps(meta) + "\n", encoding="utf-8")
    jsonl = Path(sd) / "logs" / "oneoff_report" / "summary.jsonl"
    jsonl.parent.mkdir(parents=True, exist_ok=True)
    jsonl.write_text('{"url":"u"}\n', encoding="utf-8")
    html = Path(sd) / "logs" / "oneoff_report" / "report.html"
    html.write_text("<html></html>", encoding="utf-8")

    fixed_now = old_epoch + 200 * 86400

    monkeypatch.setattr(rolling.time, "time", lambda: fixed_now)
    rolling.rotate_if_needed(sd, 90)

    archived = list(Path(sd, "logs", "oneoff_report").glob("summary_*.jsonl"))
    assert archived, "jsonl should rotate to dated name"
    meta2 = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta2.get("epoch_start_unix") == fixed_now
