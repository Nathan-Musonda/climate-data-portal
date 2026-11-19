import json
import logging
import time
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from backend.config import Config
from backend.utils.live_weather_storage import persist_live_weather_observation


logger = logging.getLogger(__name__)

DEFAULT_LIVE_WEATHER_CACHE_TTL_SECONDS = 300
DEFAULT_LIVE_WEATHER_API_URL = "https://api.openweathermap.org/data/2.5/weather"
LIVE_WEATHER_CACHE = {}


def _coerce_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_coordinate(value, lower_bound, upper_bound, label):
    numeric_value = _coerce_float(value)
    if numeric_value is None:
        raise ValueError(f"{label} must be a valid number.")
    if numeric_value < lower_bound or numeric_value > upper_bound:
        raise ValueError(
            f"{label} must be between {lower_bound} and {upper_bound}."
        )
    return round(numeric_value, 6)


def _build_cache_key(latitude, longitude):
    return f"{latitude:.3f}:{longitude:.3f}"


def _format_location_name(place_name, country_code):
    place = str(place_name or "").strip()
    country = str(country_code or "").strip().upper()
    if place and country:
        return f"{place}, {country}"
    return place or country or "your current area"


def _build_observed_at_label(timestamp, timezone_offset_seconds):
    try:
        observed_at = int(timestamp)
    except (TypeError, ValueError):
        return "Latest weather update"

    try:
        tzinfo = timezone(timedelta(seconds=int(timezone_offset_seconds or 0)))
    except (TypeError, ValueError, OverflowError):
        tzinfo = timezone.utc

    return (
        "Updated at "
        f"{datetime.fromtimestamp(observed_at, tz=tzinfo).strftime('%Y-%m-%d %H:%M')}"
    )


def get_live_weather(latitude, longitude):
    configured_url = str(Config.LIVE_WEATHER_API_URL or "").strip()
    configured_key = str(Config.LIVE_WEATHER_API_KEY or "").strip()
    daily_key = str(getattr(Config, "DAILY_WEATHER_API_KEY", "") or "").strip()

    request_base_url = (
        configured_url
        if configured_url and not configured_url.lower().startswith("replace-with")
        else DEFAULT_LIVE_WEATHER_API_URL
    )
    api_key = configured_key if configured_key and not configured_key.lower().startswith("replace-with") else daily_key
    if not request_base_url or not api_key:
        raise RuntimeError("Live weather is not configured on the server.")

    normalized_latitude = _normalize_coordinate(latitude, -90, 90, "Latitude")
    normalized_longitude = _normalize_coordinate(longitude, -180, 180, "Longitude")
    cache_key = _build_cache_key(normalized_latitude, normalized_longitude)
    now = time.time()
    cache_ttl_seconds = max(
        int(
            getattr(
                Config,
                "LIVE_WEATHER_CACHE_TTL_SECONDS",
                DEFAULT_LIVE_WEATHER_CACHE_TTL_SECONDS
            ) or DEFAULT_LIVE_WEATHER_CACHE_TTL_SECONDS
        ),
        60
    )

    cached_entry = LIVE_WEATHER_CACHE.get(cache_key)
    if cached_entry and cached_entry.get("expires_at", 0) > now:
        return cached_entry["value"]

    query_string = urlencode({
        "lat": normalized_latitude,
        "lon": normalized_longitude,
        "appid": api_key,
        "units": "metric"
    })
    request_url = f"{request_base_url}?{query_string}"

    try:
        with urlopen(
            request_url,
            timeout=float(getattr(Config, "LIVE_WEATHER_TIMEOUT_SECONDS", 6) or 6)
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        if error.code in (401, 403):
            raise RuntimeError("Live weather credentials were rejected by the weather service.") from error
        if error.code == 429:
            raise RuntimeError("Live weather updates are temporarily busy. Try again shortly.") from error
        raise RuntimeError("Live weather could not be loaded right now.") from error
    except URLError as error:
        raise RuntimeError("Unable to reach the live weather service right now.") from error

    weather_rows = payload.get("weather") or []
    primary_weather = weather_rows[0] if weather_rows else {}
    main_data = payload.get("main") or {}
    wind_data = payload.get("wind") or {}
    cloud_data = payload.get("clouds") or {}
    system_data = payload.get("sys") or {}
    timezone_offset_seconds = payload.get("timezone", 0)

    normalized_payload = {
        "source": "Live weather",
        "location_name": _format_location_name(payload.get("name"), system_data.get("country")),
        "place_name": str(payload.get("name") or "").strip(),
        "country_code": str(system_data.get("country") or "").strip().upper() or None,
        "coordinates": {
            "latitude": normalized_latitude,
            "longitude": normalized_longitude
        },
        "observed_at_unix": int(payload.get("dt") or 0) or None,
        "observed_at_label": _build_observed_at_label(payload.get("dt"), timezone_offset_seconds),
        "timezone_offset_seconds": int(timezone_offset_seconds or 0),
        "weather_main": str(primary_weather.get("main") or "").strip() or None,
        "weather_description": str(primary_weather.get("description") or "").strip() or None,
        "temperature_c": _coerce_float(main_data.get("temp")),
        "feels_like_c": _coerce_float(main_data.get("feels_like")),
        "humidity_pct": _coerce_float(main_data.get("humidity")),
        "pressure_hpa": _coerce_float(main_data.get("pressure")),
        "wind_speed_mps": _coerce_float(wind_data.get("speed")),
        "cloudiness_pct": _coerce_float(cloud_data.get("all")),
        "visibility_m": _coerce_float(payload.get("visibility")),
        "raw_payload": payload
    }

    try:
        persisted_id = persist_live_weather_observation(normalized_payload)
        if persisted_id is not None:
            normalized_payload["persistent_observation_id"] = persisted_id
    except Exception as error:
        logger.warning("Live weather was fetched but could not be persisted: %s", error)

    LIVE_WEATHER_CACHE[cache_key] = {
        "expires_at": now + cache_ttl_seconds,
        "value": normalized_payload
    }
    return normalized_payload
