"""gallery-dl setup API: parse/serialize, presets, /api/gallery-dl/setup routes."""

from __future__ import annotations

import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.gallery_dl_setup import (
    apply_builtin_preset,
    parse_gallery_dl_conf_text,
    serialize_gallery_dl_conf,
)
from app.main import app
import app.settings as sm


@pytest.fixture
def gallery_setup_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ar = tmp_path / "archive"
    ar.mkdir()
    st_path = tmp_path / "state.json"
    st_path.write_text(
        json.dumps(
            {
                "host": "127.0.0.1",
                "port": 8756,
                "archive_root": str(ar),
                "allowlisted_rel_prefixes": ["logs", "galleries"],
                "download_dirs": {
                    "watch_later": "",
                    "channels": "",
                    "videos": "",
                    "oneoff": "",
                    "galleries": "",
                },
                "features": {
                    "scheduler_enabled": False,
                    "notifications_stub": False,
                    "require_cookie_confirm_manual": True,
                    "tray_notify_before_schedule": False,
                },
                "schedules": [],
                "run_history": [],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(sm, "DEFAULT_STATE_PATH", st_path)
    main._state = None
    main._manager = None
    with TestClient(app) as client:
        yield client, ar


def test_parse_preserves_unknown_keys() -> None:
    raw = {
        "extractor": {"timeout": 9.0},
        "zzz_custom": {"nested": True},
        "downloader": {},
    }
    text = json.dumps(raw)
    state, warns = parse_gallery_dl_conf_text(text)
    assert warns == []
    assert state.get("zzz_custom") == {"nested": True}
    assert state["extractor"].get("timeout") == 9.0


def test_round_trip_serialize_parse() -> None:
    state, _ = parse_gallery_dl_conf_text(
        '{"extractor":{"base-directory":"/tmp","directory":["a","b"]},'
        '"keep_me":[1,2]}',
    )
    out = serialize_gallery_dl_conf(state)
    again, w2 = parse_gallery_dl_conf_text(out)
    assert not w2
    assert again.get("keep_me") == [1, 2]


def test_apply_builtin_preset_deep_merge() -> None:
    base = {
        "extractor": {
            "timeout": 1.0,
            "directory": ["x", "y"],
            "reddit": {"api": "oauth", "client-id": "abc"},
        },
        "noise": 42,
    }
    merged = apply_builtin_preset(base, "fast_local")
    assert merged["noise"] == 42
    assert merged["extractor"]["timeout"] != 1.0
    assert merged["extractor"]["directory"] == ["x", "y"]
    assert merged["extractor"]["reddit"]["api"] == "oauth"
    assert merged["extractor"]["reddit"]["client-id"] == "abc"


def test_preset_list_is_rate_only() -> None:
    from app.gallery_dl_setup import PRESET_META, PRESET_PATCHES

    assert set(PRESET_PATCHES.keys()) == {
        "balanced",
        "conservative",
        "fast_local",
        "slow_safe",
    }
    assert len(PRESET_META) == 4
    ids = {p["id"] for p in PRESET_META}
    assert ids == {"balanced", "conservative", "fast_local", "user_preferences"}


def test_get_gallery_dl_setup_missing_file(gallery_setup_client) -> None:
    client, ar = gallery_setup_client
    r = client.get("/api/gallery-dl/setup")
    assert r.status_code == 200
    body = r.json()
    assert body["conf_exists"] is False
    assert body["mtime"] is None
    assert "state" in body
    assert body["conf_path"] == str(ar / "gallery-dl.conf")
    assert body["archive_root"] == str(ar.resolve())
    assert isinstance(body["tier_a_groups"], list)
    assert isinstance(body["presets"], list)


def test_get_loads_only_canonical_path(gallery_setup_client) -> None:
    """Nested gallery-dl.conf is ignored; Galleries and setup use archive_root basename only."""
    client, ar = gallery_setup_client
    sub = ar / "scripts"
    sub.mkdir()
    (sub / "gallery-dl.conf").write_text(
        json.dumps({"misplaced_marker": True}),
        encoding="utf-8",
    )
    r = client.get("/api/gallery-dl/setup")
    assert r.status_code == 200
    body = r.json()
    assert body["conf_exists"] is False
    assert "misplaced_marker" not in body["state"]


def test_get_loads_file_at_archive_root(gallery_setup_client) -> None:
    client, ar = gallery_setup_client
    (ar / "gallery-dl.conf").write_text(
        json.dumps({"at_archive_root": 42, "extractor": {}}),
        encoding="utf-8",
    )
    r = client.get("/api/gallery-dl/setup")
    assert r.status_code == 200
    body = r.json()
    assert body["conf_exists"] is True
    assert body["state"].get("at_archive_root") == 42


def test_post_preview(gallery_setup_client) -> None:
    client, _ar = gallery_setup_client
    r = client.post(
        "/api/gallery-dl/setup/preview",
        json={"state": {"extractor": {"timeout": 33.0}, "verbose": True}},
    )
    assert r.status_code == 200
    j = r.json()
    assert "preview" in j
    assert "serialized_preview" in j
    assert "33" in j["serialized_preview"] or "33.0" in j["serialized_preview"]


def test_post_save_writes_disk(gallery_setup_client) -> None:
    client, ar = gallery_setup_client
    state = {"extractor": {"timeout": 40.0}, "custom_key": [1]}
    r = client.post(
        "/api/gallery-dl/setup/save",
        json={
            "state": state,
            "active_preset_id": "balanced",
            "conf_smoke": False,
        },
    )
    assert r.status_code == 200
    out = r.json()
    assert out.get("ok") is True
    assert "mtime" in out
    assert out["mtime"] is not None
    p = ar / "gallery-dl.conf"
    assert p.is_file()
    disk = json.loads(p.read_text(encoding="utf-8"))
    assert disk["custom_key"] == [1]


def test_apply_preset_user_without_snapshot_400(gallery_setup_client) -> None:
    client, _ar = gallery_setup_client
    r = client.post(
        "/api/gallery-dl/setup/apply-preset",
        json={"preset_id": "user_preferences"},
    )
    assert r.status_code == 400


def test_tier_a_reddit_groups_public_default(gallery_setup_client) -> None:
    client, _ar = gallery_setup_client
    r = client.get("/api/gallery-dl/setup")
    assert r.status_code == 200
    groups = r.json().get("tier_a_groups") or []
    labels = [g.get("label") for g in groups]
    assert "Reddit" in labels
    advanced = [g for g in groups if g.get("collapsible")]
    assert len(advanced) == 1
    assert "OAuth" in advanced[0]["label"]
    assert advanced[0].get("collapsed") is True
    assert len(advanced[0].get("fields") or []) >= 4


def test_apply_preset_rejects_removed_legacy_ids(gallery_setup_client) -> None:
    client, _ar = gallery_setup_client
    for legacy in ("reddit_oauth", "debug_verbose", "directory_tidy"):
        r = client.post(
            "/api/gallery-dl/setup/apply-preset",
            json={"preset_id": legacy},
        )
        assert r.status_code == 404
