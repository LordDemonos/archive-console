"""Parsing and API smoke for supported extractors (yt-dlp / gallery-dl)."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.main import app
import app.settings as sm
from app.supported_sites import (
    _safe_http_url,
    _unique_slug,
    build_supported_sites_payload,
    invalidate_supported_sites_cache,
    parse_gallery_dl_list_extractors,
    parse_ytdlp_list_extractors,
)


def test_safe_http_url() -> None:
    assert _safe_http_url("https://example.com/x") == "https://example.com/x"
    assert _safe_http_url("http://a.test") == "http://a.test"
    assert _safe_http_url("javascript:alert(1)") is None
    assert _safe_http_url(None) is None


def test_unique_slug() -> None:
    seen: set[str] = set()
    assert _unique_slug("a", seen) == "a"
    assert _unique_slug("a", seen) == "a__2"
    assert _unique_slug("a", seen) == "a__3"


def test_parse_ytdlp_list_extractors() -> None:
    out = "youtube\nfoo:bar\n"
    rows = parse_ytdlp_list_extractors(out)
    labels = {r.label for r in rows}
    assert "youtube" in labels
    assert "foo:bar" in labels
    assert all(r.doc_url.endswith("supportedsites.md") for r in rows)


def test_parse_gallery_dl_list_extractors() -> None:
    block = """FooExtractor
Description line
Category: cat1 - Subcategory: sub1
Example : https://example.com/gallery/1

BarExtractor
Category: cat2 - Subcategory: sub2
Example : javascript:void(0)
"""
    rows = parse_gallery_dl_list_extractors(block)
    assert len(rows) >= 2
    ids = {r.id for r in rows}
    assert "cat1:sub1" in ids
    assert "cat2:sub2" in ids
    foo = next(r for r in rows if r.id == "cat1:sub1")
    assert foo.example_url == "https://example.com/gallery/1"
    bar = next(r for r in rows if r.id == "cat2:sub2")
    assert bar.example_url is None


@pytest.fixture
def supported_sites_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ar = tmp_path / "archive"
    ar.mkdir()
    st_path = tmp_path / "state.json"
    st_path.write_text(
        json.dumps(
            {
                "host": "127.0.0.1",
                "port": 8756,
                "archive_root": str(ar),
                "allowlisted_rel_prefixes": ["logs"],
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
    invalidate_supported_sites_cache()
    with TestClient(app) as client:
        yield client


def test_api_supported_sites_returns_tools(supported_sites_client) -> None:
    r = supported_sites_client.get("/api/supported-sites")
    assert r.status_code == 200
    j = r.json()
    assert "tools" in j
    assert len(j["tools"]) == 2
    ids = {t["id"] for t in j["tools"]}
    assert ids == {"yt-dlp", "gallery-dl"}
    for t in j["tools"]:
        assert "doc_hub_url" in t
        assert "extractors" in t


def test_build_supported_sites_cache_hit() -> None:
    invalidate_supported_sites_cache()
    a = build_supported_sites_payload(force_refresh=True)
    b = build_supported_sites_payload(force_refresh=False)
    assert b.get("cached") is True
    assert a.get("cached") is False
    assert len(b["tools"]) == len(a["tools"])
