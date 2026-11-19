import argparse
import calendar
import csv
import json
import logging
import math
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

import psycopg2
from psycopg2.extras import execute_values

sys.path.append(str(Path(__file__).resolve().parents[1]))

from backend.config import Config
from scripts.build_free_source_dataset import load_district_locations


LOGGER = logging.getLogger(__name__)

DEFAULT_BOUNDARIES_PATH = Config.STATIC_DIR / "data" / "zambia_districts.geojson"
DEFAULT_OUTPUT_DIR = Config.DATA_DIR / "daily_weather_updates"
DEFAULT_CURRENT_WEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"

OUTPUT_COLUMNS = [
    "Date",
    "Year",
    "Month",
    "MonthName",
    "Province",
    "District",
    "DataSource",
    "Rainfall_mm",
    "Temp_Max_C",
    "Temp_Min_C",
    "Humidity_pct",
    "Evapotranspiration_mm",
    "WindSpeed_mps",
    "SolarRadiation_Wm2",
    "SoilMoisture_pct",
    "NDVI",
    "SPI",
    "SPEI",
    "PDSI",
    "DroughtSeverity",
    "CropYield_kg_ha",
    "LivestockMortality_pct",
    "FoodPrice_ZMW",
    "LakeKariba_Level_m",
    "Hydropower_MW",
    "PopulationAffected",
    "ReliefInterventions",
]


def coerce_float(value):
    try:
        if value is None:
            return None
        numeric = float(value)
        if not math.isfinite(numeric):
            return None
        return numeric
    except (TypeError, ValueError):
        return None


def round_or_none(value, digits=2):
    numeric = coerce_float(value)
    return round(numeric, digits) if numeric is not None else None


def local_date_from_payload(payload):
    observed_at = payload.get("dt")
    timezone_offset = payload.get("timezone", 0)
    try:
        tzinfo = timezone(timedelta(seconds=int(timezone_offset or 0)))
        return datetime.fromtimestamp(int(observed_at), tz=tzinfo).date()
    except (TypeError, ValueError, OSError, OverflowError):
        return datetime.now(timezone(timedelta(hours=2))).date()


def rainfall_from_payload(payload):
    rain = payload.get("rain") or {}
    snow = payload.get("snow") or {}
    rainfall = rain.get("1h")
    if rainfall is None:
        rainfall = rain.get("3h")
    if rainfall is None:
        rainfall = snow.get("1h")
    if rainfall is None:
        rainfall = snow.get("3h")
    return round_or_none(rainfall)


def build_weather_row(location, payload):
    main = payload.get("main") or {}
    wind = payload.get("wind") or {}
    record_date = local_date_from_payload(payload)
    temperature = coerce_float(main.get("temp"))

    temp_max = coerce_float(main.get("temp_max"))
    temp_min = coerce_float(main.get("temp_min"))
    if temp_max is None:
        temp_max = temperature
    if temp_min is None:
        temp_min = temperature

    return {
        "Date": record_date.isoformat(),
        "Year": record_date.year,
        "Month": record_date.month,
        "MonthName": calendar.month_name[record_date.month],
        "Province": location["province"],
        "District": location["district"],
        "DataSource": "OpenWeather",
        "Rainfall_mm": rainfall_from_payload(payload),
        "Temp_Max_C": round_or_none(temp_max),
        "Temp_Min_C": round_or_none(temp_min),
        "Humidity_pct": round_or_none(main.get("humidity")),
        "Evapotranspiration_mm": None,
        "WindSpeed_mps": round_or_none(wind.get("speed")),
        "SolarRadiation_Wm2": None,
        "SoilMoisture_pct": None,
        "NDVI": None,
        "SPI": None,
        "SPEI": None,
        "PDSI": None,
        "DroughtSeverity": None,
        "CropYield_kg_ha": None,
        "LivestockMortality_pct": None,
        "FoodPrice_ZMW": None,
        "LakeKariba_Level_m": None,
        "Hydropower_MW": None,
        "PopulationAffected": None,
        "ReliefInterventions": None,
    }


def fetch_current_weather(location, api_url, api_key, timeout):
    query_string = urlencode({
        "lat": location["latitude"],
        "lon": location["longitude"],
        "appid": api_key,
        "units": "metric",
    })
    request_url = f"{api_url}?{query_string}"

    try:
        with urlopen(request_url, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        if error.code in (401, 403):
            raise RuntimeError("Weather API credentials were rejected.") from error
        if error.code == 429:
            raise RuntimeError("Weather API rate limit reached.") from error
        raise RuntimeError(f"Weather API request failed with HTTP {error.code}.") from error
    except URLError as error:
        raise RuntimeError("Unable to reach the weather API.") from error


def output_path_for_run(output_dir, run_date):
    return output_dir / f"daily_weather_{run_date.isoformat()}.csv"


def write_daily_csv(rows, output_dir, run_date):
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_path_for_run(output_dir, run_date)
    latest_path = output_dir / "daily_weather_latest.csv"

    for path in (output_path, latest_path):
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)

    return output_path, latest_path


def row_to_record(row):
    return (
        row["Date"],
        row["Year"],
        row["Month"],
        row["MonthName"],
        row["Province"],
        row["District"],
        row["DataSource"],
        row["Rainfall_mm"],
        row["Temp_Max_C"],
        row["Temp_Min_C"],
        row["Humidity_pct"],
        row["Evapotranspiration_mm"],
        row["WindSpeed_mps"],
        row["SolarRadiation_Wm2"],
        row["SoilMoisture_pct"],
        row["NDVI"],
        row["SPI"],
        row["SPEI"],
        row["PDSI"],
        row["DroughtSeverity"],
        row["CropYield_kg_ha"],
        row["LivestockMortality_pct"],
        row["FoodPrice_ZMW"],
        row["LakeKariba_Level_m"],
        row["Hydropower_MW"],
        row["PopulationAffected"],
        row["ReliefInterventions"],
    )


def upsert_daily_rows(rows):
    if not rows:
        return 0

    records = [row_to_record(row) for row in rows]
    query = """
        INSERT INTO climate_records (
            date, year, month, month_name, province, district, data_source,
            rainfall_mm, temp_max_c, temp_min_c, humidity_pct,
            evapotranspiration_mm, wind_speed_mps, solar_radiation_wm2,
            soil_moisture_pct, ndvi, spi, spei, pdsi, drought_severity,
            crop_yield_kg_ha, livestock_mortality_pct, food_price_zmw,
            lake_kariba_level_m, hydropower_mw, population_affected,
            relief_interventions
        ) VALUES %s
        ON CONFLICT (date, province, district) DO UPDATE SET
            year = EXCLUDED.year,
            month = EXCLUDED.month,
            month_name = EXCLUDED.month_name,
            data_source = EXCLUDED.data_source,
            rainfall_mm = COALESCE(EXCLUDED.rainfall_mm, climate_records.rainfall_mm),
            temp_max_c = COALESCE(EXCLUDED.temp_max_c, climate_records.temp_max_c),
            temp_min_c = COALESCE(EXCLUDED.temp_min_c, climate_records.temp_min_c),
            humidity_pct = COALESCE(EXCLUDED.humidity_pct, climate_records.humidity_pct),
            evapotranspiration_mm = COALESCE(EXCLUDED.evapotranspiration_mm, climate_records.evapotranspiration_mm),
            wind_speed_mps = COALESCE(EXCLUDED.wind_speed_mps, climate_records.wind_speed_mps),
            solar_radiation_wm2 = COALESCE(EXCLUDED.solar_radiation_wm2, climate_records.solar_radiation_wm2),
            soil_moisture_pct = COALESCE(EXCLUDED.soil_moisture_pct, climate_records.soil_moisture_pct),
            ndvi = COALESCE(EXCLUDED.ndvi, climate_records.ndvi),
            spi = COALESCE(EXCLUDED.spi, climate_records.spi),
            spei = COALESCE(EXCLUDED.spei, climate_records.spei),
            pdsi = COALESCE(EXCLUDED.pdsi, climate_records.pdsi),
            drought_severity = COALESCE(EXCLUDED.drought_severity, climate_records.drought_severity),
            updated_at = CURRENT_TIMESTAMP
    """

    conn = None
    try:
        conn = psycopg2.connect(
            host=Config.DB_HOST,
            port=Config.DB_PORT,
            user=Config.DB_USER,
            password=Config.DB_PASSWORD,
            database=Config.DB_NAME,
        )
        with conn.cursor() as cursor:
            cursor.execute("""
                ALTER TABLE climate_records
                ADD COLUMN IF NOT EXISTS data_source VARCHAR(100) NOT NULL DEFAULT 'Unknown'
            """)
            execute_values(cursor, query, records)
        conn.commit()
        return len(records)
    except Exception:
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()


def update_daily_weather(args):
    api_url = str(args.api_url or Config.DAILY_WEATHER_API_URL or Config.LIVE_WEATHER_API_URL or DEFAULT_CURRENT_WEATHER_URL).strip()
    api_key = str(args.api_key or Config.DAILY_WEATHER_API_KEY or Config.LIVE_WEATHER_API_KEY or "").strip()
    if not api_key:
        raise RuntimeError("Set DAILY_WEATHER_API_KEY or LIVE_WEATHER_API_KEY before running daily ingestion.")

    locations = load_district_locations(args.boundaries)
    if args.limit_districts:
        locations = locations[:args.limit_districts]

    rows = []
    failures = []
    LOGGER.info("Fetching daily weather for %s districts", len(locations))
    for index, location in enumerate(locations, start=1):
        try:
            LOGGER.info("[%s/%s] %s, %s", index, len(locations), location["district"], location["province"])
            payload = fetch_current_weather(location, api_url, api_key, args.timeout)
            rows.append(build_weather_row(location, payload))
        except Exception as error:
            LOGGER.warning("Skipped %s, %s: %s", location["district"], location["province"], error)
            failures.append({
                "province": location["province"],
                "district": location["district"],
                "latitude": location["latitude"],
                "longitude": location["longitude"],
                "error": str(error),
            })
            if args.stop_on_failure:
                raise
        if args.sleep_seconds:
            time.sleep(args.sleep_seconds)

    run_date = datetime.now(timezone(timedelta(hours=2))).date()
    output_path, latest_path = write_daily_csv(rows, args.output_dir, run_date)
    LOGGER.info("Wrote %s daily rows to %s", len(rows), output_path)
    LOGGER.info("Updated latest snapshot at %s", latest_path)

    if failures:
        failure_path = output_path.with_suffix(".failed.json")
        with open(failure_path, "w", encoding="utf-8") as handle:
            json.dump(failures, handle, indent=2)
        LOGGER.warning("Skipped %s districts; details written to %s", len(failures), failure_path)

    if args.skip_db:
        LOGGER.info("Skipped database upsert because --skip-db was used")
        return rows

    upserted = upsert_daily_rows(rows)
    LOGGER.info("Upserted %s daily rows into climate_records", upserted)
    return rows


def parse_args():
    parser = argparse.ArgumentParser(
        description="Fetch current district weather and persist it as daily climate records."
    )
    parser.add_argument("--api-url", default=None, help="Weather endpoint. Defaults to DAILY_WEATHER_API_URL, LIVE_WEATHER_API_URL, then OpenWeather current weather.")
    parser.add_argument("--api-key", default=None, help="Weather API key. Prefer the DAILY_WEATHER_API_KEY or LIVE_WEATHER_API_KEY environment variable.")
    parser.add_argument("--boundaries", type=Path, default=DEFAULT_BOUNDARIES_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--limit-districts", type=int, default=0, help="Use a small number for quick tests.")
    parser.add_argument("--sleep-seconds", type=float, default=0.25)
    parser.add_argument("--timeout", type=float, default=10)
    parser.add_argument("--skip-db", action="store_true", help="Write CSV snapshots without updating PostgreSQL.")
    parser.add_argument("--stop-on-failure", action="store_true")
    return parser.parse_args()


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    update_daily_weather(parse_args())


if __name__ == "__main__":
    main()
