"""Weather: settings vs env precedence, validation, and /api/weather wiring."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import main as main_mod
from app.main import app
from app.settings import ConsoleState
from app.weather_home import (
    effective_openweather_api_key,
    fetch_weather_home,
    normalize_and_validate_weather_lat_lon,
    resolve_weather_coordinates,
)


def _minimal_state(**kwargs: object) -> ConsoleState:
    archive_root = str(kwargs.pop("archive_root", "/tmp"))
    allowlisted = kwargs.pop(
        "allowlisted_rel_prefixes", ["logs"]
    )
    return ConsoleState(
        archive_root=archive_root,
        allowlisted_rel_prefixes=list(allowlisted),
        **kwargs,
    )


def test_normalize_weather_lat_lon_both_empty() -> None:
    lat, lon = normalize_and_validate_weather_lat_lon(
        lat_in="",
        lon_in="",
        current_lat="",
        current_lon="",
    )
    assert lat == "" and lon == ""


def test_normalize_weather_lat_lon_partial_rejected() -> None:
    with pytest.raises(ValueError, match="both"):
        normalize_and_validate_weather_lat_lon(
            lat_in="1",
            lon_in="",
            current_lat="",
            current_lon="",
        )


def test_normalize_weather_lat_lon_out_of_range() -> None:
    with pytest.raises(ValueError, match="Latitude"):
        normalize_and_validate_weather_lat_lon(
            lat_in="91",
            lon_in="0",
            current_lat="",
            current_lon="",
        )


def test_resolve_coords_state_overrides_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARCHIVE_CONSOLE_WEATHER_LAT", "1")
    monkeypatch.setenv("ARCHIVE_CONSOLE_WEATHER_LON", "2")
    st = _minimal_state(weather_latitude="52.5", weather_longitude="13.4")
    lat, lon = resolve_weather_coordinates(st)
    assert lat == 52.5 and lon == 13.4


def test_resolve_coords_env_when_state_blank(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARCHIVE_CONSOLE_WEATHER_LAT", "10")
    monkeypatch.setenv("ARCHIVE_CONSOLE_WEATHER_LON", "20")
    st = _minimal_state()
    lat, lon = resolve_weather_coordinates(st)
    assert lat == 10.0 and lon == 20.0


def test_effective_openweather_key_state_over_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENWEATHER_API_KEY", "env-only")
    st = _minimal_state(openweather_api_key="stored-key")
    assert effective_openweather_api_key(st) == "stored-key"


def test_effective_openweather_env_when_state_blank(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENWEATHER_API_KEY", "from-env")
    st = _minimal_state()
    assert effective_openweather_api_key(st) == "from-env"


def test_fetch_weather_invalid_stored_pair_message() -> None:
    st = _minimal_state(weather_latitude="not-a-float", weather_longitude="3")
    out = fetch_weather_home(st)
    assert out["ok"] is False
    assert out["error"] == "error"
    assert "invalid" in out["message"].lower()


@pytest.fixture
def client_isolated_state(monkeypatch: pytest.MonkeyPatch, tmp_path) -> TestClient:
    ar = tmp_path / "ar"
    ar.mkdir()
    st = ConsoleState(archive_root=str(ar.resolve()), allowlisted_rel_prefixes=["logs"])
    monkeypatch.setattr(main_mod, "_get_state", lambda: st)
    return TestClient(app)


def test_api_weather_not_configured_isolated(
    client_isolated_state: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ARCHIVE_CONSOLE_WEATHER_LAT", raising=False)
    monkeypatch.delenv("ARCHIVE_CONSOLE_WEATHER_LON", raising=False)
    r = client_isolated_state.get("/api/weather")
    assert r.status_code == 200
    j = r.json()
    assert j.get("ok") is False
    assert j.get("error") == "not_configured"


def test_api_settings_weather_invalid_lat(client_isolated_state: TestClient) -> None:
    r = client_isolated_state.post(
        "/api/settings",
        json={"weather_latitude": "91", "weather_longitude": "0"},
    )
    assert r.status_code == 400
    body = r.json()
    assert "detail" in body


def test_api_settings_weather_one_coord_only(client_isolated_state: TestClient) -> None:
    r = client_isolated_state.post(
        "/api/settings",
        json={"weather_latitude": "12", "weather_longitude": ""},
    )
    assert r.status_code == 400
