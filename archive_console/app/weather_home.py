"""Home view weather: Open-Meteo (no key) or OpenWeather when API key is set."""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from .settings import ConsoleState

logger = logging.getLogger(__name__)

FETCH_TIMEOUT_SEC = 8.0

# WMO weather code → short label (Open-Meteo)
_WMO_LABELS: dict[int, str] = {
    0: "Clear",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Fog",
    51: "Drizzle",
    53: "Drizzle",
    55: "Drizzle",
    61: "Rain",
    63: "Rain",
    65: "Rain",
    71: "Snow",
    73: "Snow",
    75: "Snow",
    80: "Rain showers",
    81: "Rain showers",
    82: "Rain showers",
    95: "Thunderstorm",
    96: "Thunderstorm",
    99: "Thunderstorm",
}


def effective_openweather_api_key(st: ConsoleState) -> str:
    """Persisted key overrides env when set; strips stray newlines (never log this)."""
    sk = (st.openweather_api_key or "").replace("\r", "").replace("\n", "").strip()
    if sk:
        return sk
    return (os.environ.get("OPENWEATHER_API_KEY") or "").strip()


def normalize_and_validate_weather_lat_lon(
    *,
    lat_in: str | None,
    lon_in: str | None,
    current_lat: str,
    current_lon: str,
) -> tuple[str, str]:
    """
    Coerce optional patch + current state into a pair of strings for storage.
    Both empty → use env at fetch time. Both non-empty → must parse as floats in range.
    Raises ValueError with a safe operator-facing message (no secrets).
    """
    lat = (
        lat_in.strip()
        if lat_in is not None
        else (current_lat or "").strip()
    )
    lon = (
        lon_in.strip()
        if lon_in is not None
        else (current_lon or "").strip()
    )
    if not lat and not lon:
        return ("", "")
    if bool(lat) ^ bool(lon):
        raise ValueError(
            "Provide both latitude and longitude, or leave both empty to use environment variables."
        )
    try:
        lat_f = float(lat)
        lon_f = float(lon)
    except ValueError as e:
        raise ValueError(
            "Latitude and longitude must be valid decimal numbers."
        ) from e
    if not (-90.0 <= lat_f <= 90.0 and -180.0 <= lon_f <= 180.0):
        raise ValueError(
            "Latitude must be between -90 and 90, longitude between -180 and 180."
        )
    return (lat, lon)


def resolve_weather_coordinates(
    st: ConsoleState,
) -> tuple[float, float] | tuple[None, None]:
    """
    If both weather_latitude and weather_longitude are set on state, use them (after parse).
    Otherwise use ARCHIVE_CONSOLE_WEATHER_LAT/LON env pair.
    Returns (lat, lon) or (None, None) if not configured or invalid stored pair.
    """
    lat_s = (st.weather_latitude or "").strip()
    lon_s = (st.weather_longitude or "").strip()
    if lat_s or lon_s:
        if not lat_s or not lon_s:
            return (None, None)
        try:
            lat = float(lat_s)
            lon = float(lon_s)
        except ValueError:
            return (None, None)
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
            return (None, None)
        return (lat, lon)

    lat_s = (os.environ.get("ARCHIVE_CONSOLE_WEATHER_LAT") or "").strip()
    lon_s = (os.environ.get("ARCHIVE_CONSOLE_WEATHER_LON") or "").strip()
    if not lat_s or not lon_s:
        return (None, None)
    try:
        lat = float(lat_s)
        lon = float(lon_s)
    except ValueError:
        return (None, None)
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return (None, None)
    return (lat, lon)


def fetch_weather_home(st: ConsoleState) -> dict[str, Any]:
    """
    Return JSON-serializable weather payload for the Home view.

    ok=True: includes temp_c, condition (short text), source;
    optional humidity_pct when the provider returns it.
    ok=False: error in { not_configured, rate_limited, error }.
    """
    lat, lon = resolve_weather_coordinates(st)
    if lat is None or lon is None:
        lat_s = (st.weather_latitude or "").strip()
        lon_s = (st.weather_longitude or "").strip()
        if (lat_s or lon_s) and (not lat_s or not lon_s):
            return {
                "ok": False,
                "error": "error",
                "message": "Weather: set both latitude and longitude in Settings (or clear both to use environment).",
            }
        if lat_s and lon_s:
            return {
                "ok": False,
                "error": "error",
                "message": "Weather: coordinates in Settings are invalid. Use decimal degrees (lat −90–90, lon −180–180).",
            }
        return {
            "ok": False,
            "error": "not_configured",
            "message": "Weather: set latitude and longitude in Settings, or set ARCHIVE_CONSOLE_WEATHER_LAT and ARCHIVE_CONSOLE_WEATHER_LON on the server.",
        }

    owm_key = effective_openweather_api_key(st)

    timeout = httpx.Timeout(FETCH_TIMEOUT_SEC, connect=FETCH_TIMEOUT_SEC)
    try:
        with httpx.Client(timeout=timeout) as client:
            if owm_key:
                url = "https://api.openweathermap.org/data/2.5/weather"
                r = client.get(
                    url,
                    params={
                        "lat": lat,
                        "lon": lon,
                        "appid": owm_key,
                        "units": "metric",
                    },
                )
                if r.status_code == 401:
                    return {
                        "ok": False,
                        "error": "error",
                        "message": "OpenWeather API key rejected.",
                    }
                if r.status_code == 429:
                    return {
                        "ok": False,
                        "error": "rate_limited",
                        "message": "Weather rate limited. Try again later.",
                    }
                if r.status_code != 200:
                    return {
                        "ok": False,
                        "error": "error",
                        "message": f"Weather HTTP {r.status_code}.",
                    }
                data = r.json()
                cond = ""
                if isinstance(data.get("weather"), list) and data["weather"]:
                    cond = str(data["weather"][0].get("description") or "").strip()
                temp = data.get("main", {}).get("temp")
                if temp is None:
                    return {
                        "ok": False,
                        "error": "error",
                        "message": "Weather response missing temperature.",
                    }
                out: dict[str, Any] = {
                    "ok": True,
                    "temp_c": round(float(temp), 1),
                    "condition": cond or "Weather",
                    "source": "openweathermap",
                }
                hum = data.get("main", {}).get("humidity")
                if hum is not None:
                    try:
                        out["humidity_pct"] = int(round(float(hum)))
                    except (TypeError, ValueError):
                        pass
                return out

            url = "https://api.open-meteo.com/v1/forecast"
            r = client.get(
                url,
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": "temperature_2m,weather_code,relative_humidity_2m",
                    "temperature_unit": "celsius",
                },
            )
            if r.status_code == 429:
                return {
                    "ok": False,
                    "error": "rate_limited",
                    "message": "Weather rate limited. Try again later.",
                }
            if r.status_code != 200:
                return {
                    "ok": False,
                    "error": "error",
                    "message": f"Weather HTTP {r.status_code}.",
                }
            data = r.json()
            cur = data.get("current") or {}
            temp = cur.get("temperature_2m")
            code = cur.get("weather_code")
            if temp is None:
                return {
                    "ok": False,
                    "error": "error",
                    "message": "Weather response missing temperature.",
                }
            try:
                code_i = int(code) if code is not None else -1
            except (TypeError, ValueError):
                code_i = -1
            cond = _WMO_LABELS.get(code_i, "Weather")
            out: dict[str, Any] = {
                "ok": True,
                "temp_c": round(float(temp), 1),
                "condition": cond,
                "source": "open-meteo",
            }
            rh = cur.get("relative_humidity_2m")
            if rh is not None:
                try:
                    out["humidity_pct"] = int(round(float(rh)))
                except (TypeError, ValueError):
                    pass
            return out
    except httpx.RequestError as e:
        logger.info("weather fetch failed: %s", e)
        return {
            "ok": False,
            "error": "error",
            "message": "Weather unreachable (network).",
        }
    except Exception as e:
        logger.info("weather parse failed: %s", e)
        return {
            "ok": False,
            "error": "error",
            "message": "Weather response could not be read.",
        }
