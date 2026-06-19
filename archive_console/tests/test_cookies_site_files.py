"""cookies/ site files API and editor allowlist."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.cookies_paths import (
    apply_site_cookies_from_disk,
    cookie_stem_for_extractor_id,
    ensure_cookies_dir,
    is_sensitive_cookie_rel,
    is_simple_cookie_stem,
    is_site_cookies_rel,
    list_site_cookie_files,
    site_cookie_rel_for_stem,
    site_cookie_rel_from_basename,
)
from app.editor_files import parse_editor_filename
from app.main import app
from app.paths import PathNotAllowedError
import app.settings as sm


@pytest.fixture
def cookies_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ar = tmp_path / "archive"
    ar.mkdir()
    st_path = tmp_path / "state.json"
    st_path.write_text(
        json.dumps(
            {
                "host": "127.0.0.1",
                "port": 8756,
                "archive_root": str(ar),
                "allowlisted_rel_prefixes": ["logs", "galleries", "cookies"],
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


def test_site_cookie_path_helpers() -> None:
    assert is_site_cookies_rel("cookies/instagram.txt")
    assert is_site_cookies_rel("cookies/twitter.txt")
    assert not is_site_cookies_rel("cookies/nested/x.txt")
    assert is_sensitive_cookie_rel("cookies.txt")
    assert is_sensitive_cookie_rel("cookies/reddit.txt")
    assert site_cookie_rel_from_basename("instagram") == "cookies/instagram.txt"
    assert site_cookie_rel_for_stem("instagram") == "cookies/instagram.txt"
    assert cookie_stem_for_extractor_id("instagram:tag") == "instagram"
    assert cookie_stem_for_extractor_id("cat1:sub1") == "cat1"
    assert cookie_stem_for_extractor_id("bad/id") is None
    assert is_simple_cookie_stem("twitter")
    with pytest.raises(PathNotAllowedError):
        site_cookie_rel_from_basename("../evil")


def test_apply_site_cookies_from_disk(tmp_path: Path) -> None:
    ar = tmp_path / "archive"
    (ar / "cookies").mkdir(parents=True)
    (ar / "cookies" / "twitter.txt").write_text("x", encoding="utf-8")
    conf = {
        "extractor": {
            "instagram": {"cookies": "custom/path.txt"},
            "patreon": {"cookies": ""},
        }
    }
    out = apply_site_cookies_from_disk(conf, ar)
    assert out["extractor"]["twitter"]["cookies"] == "cookies/twitter.txt"
    assert out["extractor"]["instagram"]["cookies"] == "custom/path.txt"
    assert out["extractor"]["patreon"]["cookies"] == ""


def test_parse_editor_filename_accepts_site_cookies() -> None:
    assert parse_editor_filename("cookies/instagram.txt") == "cookies/instagram.txt"


def test_list_and_ensure_cookies_dir(tmp_path: Path) -> None:
    ar = tmp_path / "archive"
    ar.mkdir()
    ensure_cookies_dir(ar)
    (ar / "cookies" / "twitter.txt").write_text("# netscape\n", encoding="utf-8")
    files = list_site_cookie_files(ar)
    assert len(files) == 1
    assert files[0]["rel"] == "cookies/twitter.txt"


def test_api_site_files_list_and_create(cookies_env) -> None:
    client, ar = cookies_env
    r = client.get("/api/cookies/site-files")
    assert r.status_code == 200
    body = r.json()
    assert body["dir_rel"] == "cookies"
    assert body["allowlist_has_cookies_dir"] is True
    assert (ar / "cookies").is_dir()

    r2 = client.post("/api/cookies/site-files", json={"name": "instagram"})
    assert r2.status_code == 200
    rel = r2.json()["rel"]
    assert rel == "cookies/instagram.txt"
    assert (ar / rel).is_file()

    r3 = client.get("/api/cookies/site-files")
    assert len(r3.json()["files"]) == 1


def test_site_cookie_file_locked_until_unlock(cookies_env) -> None:
    client, ar = cookies_env
    rel = "cookies/patreon.txt"
    (ar / "cookies").mkdir(exist_ok=True)
    (ar / rel).write_text("secret", encoding="utf-8")

    r = client.get("/api/files/" + rel)
    assert r.status_code == 200
    body = r.json()
    assert body["locked"] is True
    assert body["content"] is None

    r2 = client.get("/api/files/" + rel + "?unlock_cookies=1")
    assert r2.status_code == 200
    assert r2.json()["content"] == "secret"

    r3 = client.put(
        "/api/files/" + rel,
        json={"content": "new", "unlock_cookies": False},
    )
    assert r3.status_code == 403

    r4 = client.put(
        "/api/files/" + rel,
        json={"content": "new", "unlock_cookies": True},
    )
    assert r4.status_code == 200
    assert (ar / rel).read_text(encoding="utf-8") == "new"
