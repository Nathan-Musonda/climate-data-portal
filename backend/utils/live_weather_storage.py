import logging
from datetime import datetime, timezone

from psycopg2.extras import Json

from backend.config import Config
from backend.utils.database import db_manager


logger = logging.getLogger(__name__)


def _observed_datetime(observed_at_unix):
    try:
        if observed_at_unix is None:
            return None
        return datetime.fromtimestamp(int(observed_at_unix), tz=timezone.utc)
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def _coordinate_value(weather, key):
    coordinates = weather.get("coordinates") or {}
    try:
        value = coordinates.get(key)
        return round(float(value), 6) if value is not None else None
    except (TypeError, ValueError):
        return None


def ensure_live_weather_table():
    db_manager.execute_query(
        """
        CREATE TABLE IF NOT EXISTS live_weather_observations (
            id SERIAL PRIMARY KEY,
            source VARCHAR(100) NOT NULL DEFAULT 'Live weather',
            location_name VARCHAR(255),
            place_name VARCHAR(255),
            country_code VARCHAR(10),
            latitude DECIMAL(9,6) NOT NULL,
            longitude DECIMAL(9,6) NOT NULL,
            observed_at TIMESTAMPTZ,
            observed_at_unix BIGINT,
            timezone_offset_seconds INTEGER,
            weather_main VARCHAR(100),
            weather_description VARCHAR(255),
            temperature_c DECIMAL(6,2),
            feels_like_c DECIMAL(6,2),
            humidity_pct DECIMAL(6,2),
            pressure_hpa DECIMAL(8,2),
            wind_speed_mps DECIMAL(7,2),
            cloudiness_pct DECIMAL(6,2),
            visibility_m DECIMAL(10,2),
            raw_payload JSONB,
            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(source, latitude, longitude, observed_at_unix)
        )
        """
    )
    db_manager.execute_query(
        "CREATE INDEX IF NOT EXISTS idx_live_weather_observed_at "
        "ON live_weather_observations(observed_at DESC)"
    )
    db_manager.execute_query(
        "CREATE INDEX IF NOT EXISTS idx_live_weather_location_time "
        "ON live_weather_observations(latitude, longitude, observed_at DESC)"
    )


def persist_live_weather_observation(weather):
    if not Config.LIVE_WEATHER_PERSIST_ENABLED or not weather:
        return None

    latitude = _coordinate_value(weather, "latitude")
    longitude = _coordinate_value(weather, "longitude")
    observed_at_unix = weather.get("observed_at_unix")
    if latitude is None or longitude is None or observed_at_unix is None:
        return None

    ensure_live_weather_table()
    observed_at = _observed_datetime(observed_at_unix)
    row = db_manager.execute_query(
        """
        INSERT INTO live_weather_observations (
            source, location_name, place_name, country_code,
            latitude, longitude, observed_at, observed_at_unix,
            timezone_offset_seconds, weather_main, weather_description,
            temperature_c, feels_like_c, humidity_pct, pressure_hpa,
            wind_speed_mps, cloudiness_pct, visibility_m, raw_payload
        ) VALUES (
            %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s, %s
        )
        ON CONFLICT (source, latitude, longitude, observed_at_unix) DO UPDATE SET
            location_name = EXCLUDED.location_name,
            place_name = EXCLUDED.place_name,
            country_code = EXCLUDED.country_code,
            timezone_offset_seconds = EXCLUDED.timezone_offset_seconds,
            weather_main = EXCLUDED.weather_main,
            weather_description = EXCLUDED.weather_description,
            temperature_c = EXCLUDED.temperature_c,
            feels_like_c = EXCLUDED.feels_like_c,
            humidity_pct = EXCLUDED.humidity_pct,
            pressure_hpa = EXCLUDED.pressure_hpa,
            wind_speed_mps = EXCLUDED.wind_speed_mps,
            cloudiness_pct = EXCLUDED.cloudiness_pct,
            visibility_m = EXCLUDED.visibility_m,
            raw_payload = EXCLUDED.raw_payload,
            updated_at = CURRENT_TIMESTAMP
        RETURNING id
        """,
        [
            weather.get("source") or "Live weather",
            weather.get("location_name"),
            weather.get("place_name"),
            weather.get("country_code"),
            latitude,
            longitude,
            observed_at,
            observed_at_unix,
            weather.get("timezone_offset_seconds"),
            weather.get("weather_main"),
            weather.get("weather_description"),
            weather.get("temperature_c"),
            weather.get("feels_like_c"),
            weather.get("humidity_pct"),
            weather.get("pressure_hpa"),
            weather.get("wind_speed_mps"),
            weather.get("cloudiness_pct"),
            weather.get("visibility_m"),
            Json(weather.get("raw_payload") or {}),
        ],
    )
    return row[0]["id"] if row else None


def _format_observation(row):
    observed_at = row.get("observed_at")
    created_at = row.get("created_at")
    return {
        "id": row.get("id"),
        "source": row.get("source"),
        "location_name": row.get("location_name"),
        "place_name": row.get("place_name"),
        "country_code": row.get("country_code"),
        "coordinates": {
            "latitude": float(row["latitude"]) if row.get("latitude") is not None else None,
            "longitude": float(row["longitude"]) if row.get("longitude") is not None else None,
        },
        "observed_at": observed_at.isoformat() if observed_at else None,
        "observed_at_unix": row.get("observed_at_unix"),
        "weather_main": row.get("weather_main"),
        "weather_description": row.get("weather_description"),
        "temperature_c": float(row["temperature_c"]) if row.get("temperature_c") is not None else None,
        "feels_like_c": float(row["feels_like_c"]) if row.get("feels_like_c") is not None else None,
        "humidity_pct": float(row["humidity_pct"]) if row.get("humidity_pct") is not None else None,
        "pressure_hpa": float(row["pressure_hpa"]) if row.get("pressure_hpa") is not None else None,
        "wind_speed_mps": float(row["wind_speed_mps"]) if row.get("wind_speed_mps") is not None else None,
        "cloudiness_pct": float(row["cloudiness_pct"]) if row.get("cloudiness_pct") is not None else None,
        "visibility_m": float(row["visibility_m"]) if row.get("visibility_m") is not None else None,
        "created_at": created_at.isoformat() if created_at else None,
    }


def get_live_weather_history(latitude=None, longitude=None, limit=None, coordinate_tolerance=0.01):
    ensure_live_weather_table()
    query = (
        "SELECT id, source, location_name, place_name, country_code, latitude, longitude, "
        "observed_at, observed_at_unix, weather_main, weather_description, temperature_c, "
        "feels_like_c, humidity_pct, pressure_hpa, wind_speed_mps, cloudiness_pct, "
        "visibility_m, created_at "
        "FROM live_weather_observations WHERE 1=1"
    )
    params = []

    if latitude is not None and longitude is not None:
        query += " AND ABS(latitude - %s) <= %s AND ABS(longitude - %s) <= %s"
        params.extend([latitude, coordinate_tolerance, longitude, coordinate_tolerance])

    requested_limit = limit or Config.LIVE_WEATHER_HISTORY_DEFAULT_LIMIT
    try:
        requested_limit = int(requested_limit)
    except (TypeError, ValueError):
        requested_limit = Config.LIVE_WEATHER_HISTORY_DEFAULT_LIMIT
    requested_limit = max(1, min(requested_limit, 500))

    query += " ORDER BY observed_at DESC NULLS LAST, created_at DESC LIMIT %s"
    params.append(requested_limit)

    rows = db_manager.execute_query(query, params) or []
    return [_format_observation(row) for row in rows]
