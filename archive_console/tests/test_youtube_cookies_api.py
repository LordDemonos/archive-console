"""Archive Console YouTube cookie refresh API (extension integration)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.main import app
import app.settings as sm

_SCRIPTS_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from archive_cookies import (  # noqa: E402
    COOKIE_REFRESH_SENTINEL_NAME,
    request_cookie_refresh,
)

_NETSCAPE = (
    "# Netscape HTTP Cookie File\n"
    "# https://curl.haxx.se/rfc/cookie_spec.html\n\n"
    ".youtube.com\tTRUE\t/\tTRUE\t0\tSID\tabc\n"
)


@pytest.fixture
def yt_cookie_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ar = tmp_path / "archive"
    ar.mkdir()
    (ar / "cookies.txt").write_text("# stale\n", encoding="utf-8")
    st_path = tmp_path / "state.json"
    st_path.write_text(
        json.dumps(
            {
                "host": "127.0.0.1",
                "port": 8756,
                "archive_root": str(ar),
                "allowlisted_rel_prefixes": ["logs", "playlists"],
                "features": {
                    "scheduler_enabled": False,
                    "require_cookie_confirm_manual": True,
                },
                "ytdlp_batch_run": {
                    "pause_on_cookie_error": True,
                    "cookie_auth_poll_sec": 15,
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(sm, "DEFAULT_STATE_PATH", st_path)
    main._state = None
    main._manager = None
    with TestClient(app) as client:
        yield client, ar


def test_youtube_refresh_false_without_sentinel(yt_cookie_client) -> None:
    client, _ar = yt_cookie_client
    r = client.get("/api/cookies/youtube-refresh")
    assert r.status_code == 200
    body = r.json()
    assert body["refresh_needed"] is False
    assert body["request"] is None


def test_youtube_refresh_true_with_sentinel(yt_cookie_client) -> None:
    client, ar = yt_cookie_client
    request_cookie_refresh(str(ar), reason="test")
    assert (ar / COOKIE_REFRESH_SENTINEL_NAME).is_file()

    r = client.get("/api/cookies/youtube-refresh")
    assert r.status_code == 200
    body = r.json()
    assert body["refresh_needed"] is True
    assert body["request"]["reason"] == "test"


def test_youtube_put_clears_sentinel_and_updates_cookies(yt_cookie_client) -> None:
    client, ar = yt_cookie_client
    request_cookie_refresh(str(ar), reason="test")
    before_mtime = (ar / "cookies.txt").stat().st_mtime

    r = client.put(
        "/api/cookies/youtube",
        json={"content": _NETSCAPE, "unlock_cookies": True},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["refresh_cleared"] is True
    assert body["size"] > 0
    assert not (ar / COOKIE_REFRESH_SENTINEL_NAME).is_file()
    assert (ar / "cookies.txt").read_text(encoding="utf-8") == _NETSCAPE
    assert (ar / "cookies.txt").stat().st_mtime >= before_mtime

    r2 = client.get("/api/cookies/youtube-refresh")
    assert r2.json()["refresh_needed"] is False


def test_youtube_put_rejects_invalid_netscape(yt_cookie_client) -> None:
    client, _ar = yt_cookie_client
    r = client.put(
        "/api/cookies/youtube",
        json={"content": "not cookies", "unlock_cookies": True},
    )
    assert r.status_code == 400
