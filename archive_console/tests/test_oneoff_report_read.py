"""Rolling one-off summary: last allowlisted media path for Watch Now."""

from __future__ import annotations

import json
from pathlib import Path

from app.oneoff_report_read import (
    _load_entries,
    last_ok_media_rel,
    oneoff_rolling_payload,
)


def _write_jsonl(root: Path, lines: list[dict]) -> None:
    p = root / "logs" / "oneoff_report" / "summary.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in lines) + "\n",
        encoding="utf-8",
    )


def test_last_ok_media_rel_resolves_absolute_media_path(tmp_path: Path) -> None:
    root = tmp_path
    media = root / "oneoff" / "ch" / "v1.mp4"
    media.parent.mkdir(parents=True)
    media.write_bytes(b"x")
    prefixes = ["oneoff"]
    _write_jsonl(
        root,
        [
            {
                "outcome": "fail",
                "media_path": str(media),
                "completed_utc": "a",
            },
            {
                "outcome": "ok",
                "media_path": str(media),
                "completed_utc": "b",
                "log_folder": "",
            },
        ],
    )
    entries = _load_entries(root)
    rel = last_ok_media_rel(root, entries, prefixes)
    assert rel == "oneoff/ch/v1.mp4"


def test_last_ok_skips_when_not_on_allowlist(tmp_path: Path) -> None:
    root = tmp_path
    media = root / "other" / "a.mp4"
    media.parent.mkdir(parents=True)
    media.write_bytes(b"x")
    _write_jsonl(
        root,
        [{"outcome": "ok", "media_path": str(media), "log_folder": ""}],
    )
    entries = _load_entries(root)
    assert last_ok_media_rel(root, entries, ["oneoff"]) is None


def test_last_ok_prefers_newest_ok(tmp_path: Path) -> None:
    root = tmp_path
    old_f = root / "oneoff" / "old.mp4"
    new_f = root / "oneoff" / "new.mkv"
    old_f.parent.mkdir(parents=True)
    old_f.write_bytes(b"a")
    new_f.write_bytes(b"b")
    prefixes = ["oneoff"]
    _write_jsonl(
        root,
        [
            {"outcome": "ok", "media_path": str(old_f), "log_folder": ""},
            {"outcome": "fail", "media_path": str(new_f), "log_folder": ""},
        ],
    )
    entries = _load_entries(root)
    assert last_ok_media_rel(root, entries, prefixes) == "oneoff/old.mp4"


def test_manifest_prefers_video_over_audio(tmp_path: Path) -> None:
    root = tmp_path
    log_dir = root / "logs" / "archive_run_x"
    log_dir.mkdir(parents=True)
    aud = root / "oneoff" / "a.m4a"
    vid = root / "oneoff" / "a.mp4"
    aud.parent.mkdir(parents=True, exist_ok=True)
    aud.write_bytes(b"a")
    vid.write_bytes(b"v")
    manifest = log_dir / "manifest.csv"
    manifest.write_text(
        "video_id,title,filepath,file_size_bytes,status,reason,timestamp_utc,"
        "playlist_id,webpage_url,file_verified_ok\n"
        f"x,t,{aud},3,downloaded,r,t,,,yes\n"
        f"x,t,{vid},3,downloaded,r,t,,,yes\n",
        encoding="utf-8",
    )
    log_rel = "logs/archive_run_x"
    _write_jsonl(
        root,
        [
            {
                "outcome": "ok",
                "media_path": str(aud),
                "log_folder": log_rel.replace("/", "\\"),
            },
        ],
    )
    entries = _load_entries(root)
    rel = last_ok_media_rel(root, entries, ["oneoff", "logs"])
    assert rel == "oneoff/a.mp4"


def test_oneoff_rolling_payload_includes_last_media_rel(tmp_path: Path) -> None:
    root = tmp_path
    media = root / "videos" / "z.webm"
    media.parent.mkdir(parents=True)
    media.write_bytes(b"z")
    _write_jsonl(
        root,
        [{"outcome": "ok", "media_path": str(media), "log_folder": ""}],
    )
    payload = oneoff_rolling_payload(root, ["videos"])
    assert payload["stats"]["last_media_rel"] == "videos/z.webm"
