"""API tests for Home bookmark icon, labels, weather, and /home redirect."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app import main as main_mod
from app.settings import ConsoleState


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_home_redirect(client: TestClient) -> None:
    r = client.get("/home", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers.get("location") == "/?view=home"


def test_bookmark_labels_api(client: TestClient) -> None:
    r = client.post(
        "/api/bookmarks/labels",
        json={"urls": ["https://example.com/", "https://example.com/docs"]},
    )
    assert r.status_code == 200
    j = r.json()
    assert j["labels"][0] == "example.com"
    assert "example.com" in j["labels"][1]
    assert j["titles"][0] == "https://example.com/"


def test_bookmark_labels_too_many(client: TestClient) -> None:
    r = client.post(
        "/api/bookmarks/labels",
        json={"urls": ["https://a.com/"] * 201},
    )
    assert r.status_code == 422


def test_bookmark_icon_bad_url(client: TestClient) -> None:
    r = client.get("/api/bookmark-icon", params={"url": "ftp://x/"})
    assert r.status_code == 400


def test_bookmark_icon_blocked_host(client: TestClient) -> None:
    r = client.get("/api/bookmark-icon", params={"url": "http://127.0.0.1/"})
    assert r.status_code == 400


def test_bookmark_icon_mocked_ok(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_fetch(u: str):
        assert "example.com" in u
        return (b"\x89PNG\r\n\x1a\n", "image/png")

    monkeypatch.setattr(main_mod, "fetch_bookmark_icon", fake_fetch)
    r = client.get(
        "/api/bookmark-icon", params={"url": "https://example.com/page"}
    )
    assert r.status_code == 200
    assert r.content.startswith(b"\x89PNG")


def test_bookmark_icon_mocked_404(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main_mod, "fetch_bookmark_icon", lambda _u: None)
    r = client.get("/api/bookmark-icon", params={"url": "https://example.com/"})
    assert r.status_code == 404


def _isolated_state(tmp_path) -> ConsoleState:
    ar = tmp_path / "bm"
    ar.mkdir()
    return ConsoleState(
        archive_root=str(ar.resolve()), allowlisted_rel_prefixes=["logs"]
    )


def test_bookmarks_get_empty(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setattr(main_mod, "_get_state", lambda: _isolated_state(tmp_path))
    r = client.get("/api/bookmarks")
    assert r.status_code == 200
    assert r.json() == {"bookmarks": []}


def test_bookmarks_put_roundtrip_and_normalizes(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    holder = {"st": _isolated_state(tmp_path)}
    monkeypatch.setattr(main_mod, "_get_state", lambda: holder["st"])
    monkeypatch.setattr(
        main_mod, "_persist_state", lambda s: holder.__setitem__("st", s)
    )
    r = client.put(
        "/api/bookmarks",
        json={"bookmarks": [{"id": "a", "url": "https://Example.com", "createdAt": 5.0}]},
    )
    assert r.status_code == 200
    bms = r.json()["bookmarks"]
    assert len(bms) == 1
    assert bms[0] == {"id": "a", "url": "https://example.com/", "createdAt": 5.0}
    assert holder["st"].home_bookmarks[0].url == "https://example.com/"
    r2 = client.get("/api/bookmarks")
    assert r2.json()["bookmarks"][0]["id"] == "a"


def test_bookmarks_put_rejects_invalid_url(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setattr(main_mod, "_get_state", lambda: _isolated_state(tmp_path))
    monkeypatch.setattr(main_mod, "_persist_state", lambda _s: None)
    r = client.put(
        "/api/bookmarks", json={"bookmarks": [{"id": "x", "url": "ftp://nope/"}]}
    )
    assert r.status_code == 400


def test_bookmarks_put_drops_duplicate_ids(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    holder = {"st": _isolated_state(tmp_path)}
    monkeypatch.setattr(main_mod, "_get_state", lambda: holder["st"])
    monkeypatch.setattr(
        main_mod, "_persist_state", lambda s: holder.__setitem__("st", s)
    )
    r = client.put(
        "/api/bookmarks",
        json={
            "bookmarks": [
                {"id": "dup", "url": "https://a.com/"},
                {"id": "dup", "url": "https://b.com/"},
            ]
        },
    )
    assert r.status_code == 200
    bms = r.json()["bookmarks"]
    assert len(bms) == 1
    assert bms[0]["url"] == "https://a.com/"


def test_bookmarks_put_caps_count(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setattr(main_mod, "_get_state", lambda: _isolated_state(tmp_path))
    monkeypatch.setattr(main_mod, "_persist_state", lambda _s: None)
    many = [{"id": str(i), "url": "https://a.com/"} for i in range(201)]
    r = client.put("/api/bookmarks", json={"bookmarks": many})
    assert r.status_code == 422


def test_weather_not_configured(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    ar = tmp_path / "a"
    ar.mkdir()
    st_iso = ConsoleState(
        archive_root=str(ar.resolve()),
        allowlisted_rel_prefixes=["logs"],
    )
    monkeypatch.setattr(main_mod, "_get_state", lambda: st_iso)
    monkeypatch.delenv("ARCHIVE_CONSOLE_WEATHER_LAT", raising=False)
    monkeypatch.delenv("ARCHIVE_CONSOLE_WEATHER_LON", raising=False)
    r = client.get("/api/weather")
    assert r.status_code == 200
    j = r.json()
    assert j.get("ok") is False
    assert j.get("error") == "not_configured"


def test_weather_open_meteo_mock(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    ar = tmp_path / "w"
    ar.mkdir()
    st_iso = ConsoleState(
        archive_root=str(ar.resolve()),
        allowlisted_rel_prefixes=["logs"],
    )
    monkeypatch.setattr(main_mod, "_get_state", lambda: st_iso)
    monkeypatch.setenv("ARCHIVE_CONSOLE_WEATHER_LAT", "52.5")
    monkeypatch.setenv("ARCHIVE_CONSOLE_WEATHER_LON", "13.4")
    monkeypatch.delenv("OPENWEATHER_API_KEY", raising=False)

    class FakeResp:
        status_code = 200

        def json(self):
            return {
                "current": {
                    "temperature_2m": 12.3,
                    "weather_code": 0,
                    "relative_humidity_2m": 55,
                },
            }

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url, params=None):
            assert "open-meteo" in url
            return FakeResp()

    import app.weather_home as wh

    monkeypatch.setattr(wh.httpx, "Client", lambda **kw: FakeClient())
    r = client.get("/api/weather")
    assert r.status_code == 200
    j = r.json()
    assert j["ok"] is True
    assert j["temp_c"] == 12.3
    assert j["humidity_pct"] == 55
    assert j["source"] == "open-meteo"
