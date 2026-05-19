import argparse
import calendar
import json
import logging
import math
import re
import sys
import time
from collections import defaultdict
from datetime import date
from pathlib import Path

import pandas as pd
import requests

sys.path.append(str(Path(__file__).resolve().parents[1]))

from config import Config


LOGGER = logging.getLogger(__name__)
OPEN_METEO_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
DEFAULT_BOUNDARIES_PATH = Config.BASE_DIR / "static" / "data" / "zambia_districts.geojson"
DEFAULT_OUTPUT_PATH = Config.DATA_DIR / "free_sources_zambia_climate_data.csv"
DEFAULT_CACHE_DIR = Config.BASE_DIR / "data" / "raw" / "free_source_cache"

OPEN_METEO_DAILY_VARIABLES = [
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_sum",
    "relative_humidity_2m_mean",
    "wind_speed_10m_mean",
    "shortwave_radiation_sum",
    "et0_fao_evapotranspiration",
    "soil_moisture_0_to_100cm_mean",
]

OUTPUT_COLUMNS = [
    "Date",
    "Year",
    "Month",
    "MonthName",
    "Province",
    "District",
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


def flatten_coordinate_pairs(coordinates):
    if not coordinates:
        return

    first = coordinates[0]
    if isinstance(first, (int, float)) and len(coordinates) >= 2:
        yield float(coordinates[0]), float(coordinates[1])
        return

    for item in coordinates:
        yield from flatten_coordinate_pairs(item)


def feature_centroid(feature):
    points = list(flatten_coordinate_pairs(feature.get("geometry", {}).get("coordinates", [])))
    if not points:
        return None, None

    longitudes = [point[0] for point in points]
    latitudes = [point[1] for point in points]
    return (
        (min(latitudes) + max(latitudes)) / 2,
        (min(longitudes) + max(longitudes)) / 2,
    )


def load_district_locations(boundaries_path):
    with open(boundaries_path, "r", encoding="utf-8") as handle:
        data = json.load(handle)

    locations = []
    for feature in data.get("features", []):
        props = feature.get("properties") or {}
        province = props.get("PROVINCE") or props.get("province") or props.get("ADM1_EN")
        district = props.get("DISTRICT") or props.get("district") or props.get("ADM2_EN")
        latitude, longitude = feature_centroid(feature)
        if province and district and latitude is not None and longitude is not None:
            locations.append({
                "province": str(province).strip(),
                "district": str(district).strip(),
                "latitude": round(latitude, 5),
                "longitude": round(longitude, 5),
            })

    locations.sort(key=lambda item: (item["province"], item["district"]))
    return locations


def fetch_open_meteo_daily(latitude, longitude, start_date, end_date, timeout=60, retries=6, backoff_seconds=8):
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": start_date,
        "end_date": end_date,
        "daily": ",".join(OPEN_METEO_DAILY_VARIABLES),
        "timezone": "Africa/Lusaka",
        "models": "era5",
        "wind_speed_unit": "ms",
    }
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            response = requests.get(OPEN_METEO_ARCHIVE_URL, params=params, timeout=timeout)
            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                wait_seconds = float(retry_after) if retry_after else backoff_seconds * attempt
                LOGGER.warning("Open-Meteo rate limit hit; waiting %.1f seconds before retry %s/%s", wait_seconds, attempt, retries)
                time.sleep(wait_seconds)
                continue
            response.raise_for_status()
            payload = response.json()
            break
        except requests.RequestException as error:
            last_error = error
            if attempt >= retries:
                raise
            wait_seconds = backoff_seconds * attempt
            LOGGER.warning("Open-Meteo request failed (%s); waiting %.1f seconds before retry %s/%s", error, wait_seconds, attempt, retries)
            time.sleep(wait_seconds)
    else:
        raise RuntimeError(f"Open-Meteo request failed: {last_error}")

    if payload.get("error"):
        raise RuntimeError(payload.get("reason") or "Open-Meteo returned an error")
    return payload.get("daily") or {}


def slugify(value):
    return re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-") or "item"


def cache_path_for_location(cache_dir, location, start_date, end_date):
    filename = (
        f"open_meteo_{start_date}_{end_date}_"
        f"{slugify(location['province'])}_{slugify(location['district'])}.json"
    )
    return cache_dir / filename


def load_or_fetch_open_meteo(location, start_date, end_date, args):
    args.cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_path_for_location(args.cache_dir, location, start_date, end_date)
    if cache_path.exists() and not args.refresh_cache:
        with open(cache_path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    daily = fetch_open_meteo_daily(
        location["latitude"],
        location["longitude"],
        start_date,
        end_date,
        timeout=args.timeout,
        retries=args.retries,
        backoff_seconds=args.backoff_seconds,
    )
    with open(cache_path, "w", encoding="utf-8") as handle:
        json.dump(daily, handle)
    return daily


def finite_mean(values):
    clean = [float(value) for value in values if value is not None and not pd.isna(value)]
    return sum(clean) / len(clean) if clean else None


def finite_sum(values):
    clean = [float(value) for value in values if value is not None and not pd.isna(value)]
    return sum(clean) if clean else None


def round_or_none(value, digits):
    if value is None or not math.isfinite(float(value)):
        return None
    return round(float(value), digits)


def build_monthly_rows(daily, location):
    grouped = defaultdict(lambda: defaultdict(list))
    dates = daily.get("time") or []

    for index, iso_date in enumerate(dates):
        year, month, _ = map(int, iso_date.split("-"))
        key = (year, month)
        for variable in OPEN_METEO_DAILY_VARIABLES:
            values = daily.get(variable) or []
            value = values[index] if index < len(values) else None
            grouped[key][variable].append(value)

    rows = []
    for (year, month), values in sorted(grouped.items()):
        rainfall = finite_sum(values["precipitation_sum"])
        evapotranspiration = finite_sum(values["et0_fao_evapotranspiration"])
        solar_mj_m2_day = finite_mean(values["shortwave_radiation_sum"])
        soil_moisture_fraction = finite_mean(values["soil_moisture_0_to_100cm_mean"])

        rows.append({
            "Date": date(year, month, 1).isoformat(),
            "Year": year,
            "Month": month,
            "MonthName": calendar.month_name[month],
            "Province": location["province"],
            "District": location["district"],
            "Rainfall_mm": round_or_none(rainfall, 2),
            "Temp_Max_C": round_or_none(finite_mean(values["temperature_2m_max"]), 2),
            "Temp_Min_C": round_or_none(finite_mean(values["temperature_2m_min"]), 2),
            "Humidity_pct": round_or_none(finite_mean(values["relative_humidity_2m_mean"]), 2),
            "Evapotranspiration_mm": round_or_none(evapotranspiration, 2),
            "WindSpeed_mps": round_or_none(finite_mean(values["wind_speed_10m_mean"]), 2),
            "SolarRadiation_Wm2": round_or_none((solar_mj_m2_day * 1_000_000 / 86_400) if solar_mj_m2_day is not None else None, 2),
            "SoilMoisture_pct": round_or_none((soil_moisture_fraction * 100) if soil_moisture_fraction is not None else None, 2),
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
        })

    return rows


def z_score(value, mean, stddev):
    if value is None or mean is None or stddev is None or stddev == 0:
        return None
    return (value - mean) / stddev


def classify_drought(spi):
    if spi is None:
        return None
    if spi <= -1.5:
        return "Severe"
    if spi <= -1.0:
        return "Moderate"
    if spi <= -0.5:
        return "Mild"
    return "No Drought"


def add_drought_indicators(df):
    if df.empty:
        return df

    work = df.copy()
    rainfall_stats = (
        work.groupby(["District", "Month"])["Rainfall_mm"]
        .agg(["mean", "std"])
        .reset_index()
        .rename(columns={"mean": "rainfall_month_mean", "std": "rainfall_month_std"})
    )
    balance = pd.to_numeric(work["Rainfall_mm"], errors="coerce").fillna(0) - pd.to_numeric(
        work["Evapotranspiration_mm"], errors="coerce"
    ).fillna(0)
    work["_WaterBalance"] = balance
    balance_stats = (
        work.groupby(["District", "Month"])["_WaterBalance"]
        .agg(["mean", "std"])
        .reset_index()
        .rename(columns={"mean": "balance_month_mean", "std": "balance_month_std"})
    )

    work = work.merge(rainfall_stats, on=["District", "Month"], how="left")
    work = work.merge(balance_stats, on=["District", "Month"], how="left")

    work["SPI"] = work.apply(
        lambda row: round_or_none(z_score(row["Rainfall_mm"], row["rainfall_month_mean"], row["rainfall_month_std"]), 2),
        axis=1,
    )
    work["SPEI"] = work.apply(
        lambda row: round_or_none(z_score(row["_WaterBalance"], row["balance_month_mean"], row["balance_month_std"]), 2),
        axis=1,
    )
    work["PDSI"] = work["SPEI"].apply(lambda value: round_or_none(value * 1.6, 2) if value is not None else None)
    work["DroughtSeverity"] = work["SPI"].apply(classify_drought)

    return work[OUTPUT_COLUMNS]


def write_output(rows, output_path):
    df = pd.DataFrame(rows, columns=OUTPUT_COLUMNS)
    df = add_drought_indicators(df)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    return df


def build_dataset(args):
    locations = load_district_locations(args.boundaries)
    if args.limit_districts:
        locations = locations[:args.limit_districts]

    LOGGER.info("Preparing %s district locations from %s", len(locations), args.boundaries)
    rows = []
    failed_locations = []
    start_date = f"{args.start_year}-01-01"
    end_date = f"{args.end_year}-12-31"

    for index, location in enumerate(locations, start=1):
        LOGGER.info(
            "[%s/%s] Fetching Open-Meteo archive for %s, %s",
            index,
            len(locations),
            location["district"],
            location["province"],
        )
        cache_path = cache_path_for_location(args.cache_dir, location, start_date, end_date)
        cache_exists = cache_path.exists() and not args.refresh_cache
        if args.cached_only and not cache_exists:
            failed_locations.append({
                "province": location["province"],
                "district": location["district"],
                "latitude": location["latitude"],
                "longitude": location["longitude"],
                "error": "Not fetched because --cached-only was used.",
            })
            continue

        if args.max_new_requests and not cache_exists and args.max_new_requests <= 0:
            failed_locations.append({
                "province": location["province"],
                "district": location["district"],
                "latitude": location["latitude"],
                "longitude": location["longitude"],
                "error": "Not fetched because --max-new-requests limit was reached.",
            })
            continue

        should_count_new_request = not cache_exists and bool(args.max_new_requests)
        if should_count_new_request:
            args.max_new_requests -= 1

        try:
            daily = load_or_fetch_open_meteo(location, start_date, end_date, args)
        except Exception as error:
            LOGGER.error(
                "Unable to fetch %s, %s: %s",
                location["district"],
                location["province"],
                error,
            )
            failed_locations.append({
                "province": location["province"],
                "district": location["district"],
                "latitude": location["latitude"],
                "longitude": location["longitude"],
                "error": str(error),
            })
            if args.stop_on_failure:
                raise
            continue
        rows.extend(build_monthly_rows(daily, location))
        if rows and args.checkpoint_every and index % args.checkpoint_every == 0:
            checkpoint_df = write_output(rows, args.output)
            LOGGER.info("Checkpoint wrote %s rows to %s", len(checkpoint_df), args.output)
        if args.sleep_seconds:
            time.sleep(args.sleep_seconds)

    df = write_output(rows, args.output)
    LOGGER.info("Wrote %s rows to %s", len(df), args.output)

    if failed_locations:
        failed_path = args.output.with_suffix(".failed.json")
        with open(failed_path, "w", encoding="utf-8") as handle:
            json.dump(failed_locations, handle, indent=2)
        LOGGER.warning("Skipped %s locations; details written to %s", len(failed_locations), failed_path)

    return df


def parse_args():
    parser = argparse.ArgumentParser(
        description="Build a portal-ready Zambia climate CSV from free public data sources."
    )
    parser.add_argument("--start-year", type=int, default=2015)
    parser.add_argument("--end-year", type=int, default=2025)
    parser.add_argument("--boundaries", type=Path, default=DEFAULT_BOUNDARIES_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--limit-districts", type=int, default=0, help="Use a small number for quick tests.")
    parser.add_argument("--sleep-seconds", type=float, default=1.0)
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("--retries", type=int, default=6)
    parser.add_argument("--backoff-seconds", type=float, default=8)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--refresh-cache", action="store_true")
    parser.add_argument("--stop-on-failure", action="store_true")
    parser.add_argument("--cached-only", action="store_true", help="Build CSV only from cached API responses.")
    parser.add_argument("--max-new-requests", type=int, default=0, help="Limit fresh API calls; cached districts still load.")
    parser.add_argument("--checkpoint-every", type=int, default=5, help="Write partial output after this many locations.")
    return parser.parse_args()


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    args = parse_args()
    if args.start_year > args.end_year:
        raise ValueError("--start-year must be before or equal to --end-year")
    build_dataset(args)


if __name__ == "__main__":
    main()
