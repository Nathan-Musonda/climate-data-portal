import argparse
import calendar
import json
import logging
import math
import sys
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

sys.path.append(str(Path(__file__).resolve().parents[1]))

from backend.config import Config


LOGGER = logging.getLogger(__name__)

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

DB_COLUMNS = [
    "date",
    "year",
    "month",
    "month_name",
    "province",
    "district",
    "data_source",
    "rainfall_mm",
    "temp_max_c",
    "temp_min_c",
    "humidity_pct",
    "evapotranspiration_mm",
    "wind_speed_mps",
    "solar_radiation_wm2",
    "soil_moisture_pct",
    "ndvi",
    "spi",
    "spei",
    "pdsi",
    "drought_severity",
    "crop_yield_kg_ha",
    "livestock_mortality_pct",
    "food_price_zmw",
    "lake_kariba_level_m",
    "hydropower_mw",
    "population_affected",
    "relief_interventions",
]

APP_TO_DB = dict(zip(OUTPUT_COLUMNS, DB_COLUMNS))

SOURCE_PRIORITY = {
    "ZMD": 10,
    "ZAMBIA_MET_DEPT": 10,
    "SADC": 20,
    "SADC_CSC": 20,
    "WORLD_BANK_CCKP": 30,
    "CHIRPS": 40,
    "NASA_POWER": 50,
    "OPEN_METEO": 60,
    "LEGACY_CSV": 70,
    "UNKNOWN": 90,
}

NASA_POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"

ZMD_ALIASES = {
    "station": "District",
    "district": "District",
    "province": "Province",
    "date": "Date",
    "maxtemp": "Temp_Max_C",
    "maxtemp": "Temp_Max_C",
    "tempmax": "Temp_Max_C",
    "tempmaxc": "Temp_Max_C",
    "tmax": "Temp_Max_C",
    "mintemp": "Temp_Min_C",
    "tempmin": "Temp_Min_C",
    "tempminc": "Temp_Min_C",
    "tmin": "Temp_Min_C",
    "rainfall": "Rainfall_mm",
    "rainfallmm": "Rainfall_mm",
    "precipitation": "Rainfall_mm",
    "humidity": "Humidity_pct",
    "humiditypct": "Humidity_pct",
}

PORTAL_ALIASES = {
    "date": "Date",
    "year": "Year",
    "month": "Month",
    "monthname": "MonthName",
    "province": "Province",
    "district": "District",
    "datasource": "DataSource",
    "datasource": "DataSource",
    "source": "DataSource",
    "rainfallmm": "Rainfall_mm",
    "tempmaxc": "Temp_Max_C",
    "tempminc": "Temp_Min_C",
    "humiditypct": "Humidity_pct",
    "evapotranspirationmm": "Evapotranspiration_mm",
    "windspeedmps": "WindSpeed_mps",
    "solarradiationwm2": "SolarRadiation_Wm2",
    "soilmoisturepct": "SoilMoisture_pct",
    "ndvi": "NDVI",
    "spi": "SPI",
    "spei": "SPEI",
    "pdsi": "PDSI",
    "droughtseverity": "DroughtSeverity",
    "cropyieldkgha": "CropYield_kg_ha",
    "livestockmortalitypct": "LivestockMortality_pct",
    "foodpricezmw": "FoodPrice_ZMW",
    "lakekaribalevelm": "LakeKariba_Level_m",
    "hydropowermw": "Hydropower_MW",
    "populationaffected": "PopulationAffected",
    "reliefinterventions": "ReliefInterventions",
}


def normalize_name(value):
    return "".join(ch for ch in str(value or "").lower() if ch.isalnum())


def source_rank(source):
    key = str(source or "Unknown").strip().upper().replace(" ", "_").replace("-", "_")
    return SOURCE_PRIORITY.get(key, SOURCE_PRIORITY["UNKNOWN"])


def coerce_float(value):
    if value is None or pd.isna(value):
        return None
    try:
        numeric = float(value)
        return numeric if math.isfinite(numeric) else None
    except (TypeError, ValueError):
        return None


def coerce_int(value):
    numeric = coerce_float(value)
    return int(numeric) if numeric is not None else None


def clean_text(value):
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return None
    return text


def rename_known_columns(df, aliases):
    rename_map = {}
    for column in df.columns:
        normalized = normalize_name(column)
        if normalized in aliases:
            rename_map[column] = aliases[normalized]
    return df.rename(columns=rename_map)


def finalize_frame(df, source_name):
    work = df.copy()
    for column in OUTPUT_COLUMNS:
        if column not in work.columns:
            work[column] = None

    work["Date"] = pd.to_datetime(work["Date"], errors="coerce")
    work = work.dropna(subset=["Date", "Province", "District"]).copy()
    work["Year"] = work["Date"].dt.year
    work["Month"] = work["Date"].dt.month
    work["MonthName"] = work["Date"].dt.month.apply(lambda value: calendar.month_name[int(value)])
    work["Date"] = work["Date"].dt.date.astype(str)
    work["DataSource"] = work["DataSource"].apply(clean_text).fillna(source_name)
    work["Province"] = work["Province"].apply(clean_text)
    work["District"] = work["District"].apply(clean_text)

    numeric_columns = [
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
        "CropYield_kg_ha",
        "LivestockMortality_pct",
        "FoodPrice_ZMW",
        "LakeKariba_Level_m",
        "Hydropower_MW",
    ]
    for column in numeric_columns:
        work[column] = pd.to_numeric(work[column], errors="coerce")

    for column in ["PopulationAffected", "ReliefInterventions"]:
        work[column] = work[column].apply(coerce_int)

    work["DroughtSeverity"] = work["DroughtSeverity"].apply(clean_text)
    return work[OUTPUT_COLUMNS]


def clean_portal_csv(path, source_name="Legacy CSV"):
    LOGGER.info("Loading portal CSV: %s", path)
    df = pd.read_csv(path)
    df = rename_known_columns(df, PORTAL_ALIASES)
    return finalize_frame(df, source_name)


def clean_zmd_csv(path, source_name="ZMD", province=None):
    LOGGER.info("Loading ZMD CSV: %s", path)
    df = pd.read_csv(path)
    df = rename_known_columns(df, {**PORTAL_ALIASES, **ZMD_ALIASES})
    if province and "Province" not in df.columns:
        df["Province"] = province
    return finalize_frame(df, source_name)


def nasa_parameters_to_frame(payload, province, district, source_name="NASA_POWER"):
    parameters = payload.get("properties", {}).get("parameter", {})
    date_keys = sorted({
        key
        for series in parameters.values()
        if isinstance(series, dict)
        for key in series.keys()
    })
    rows = []
    for key in date_keys:
        date = pd.to_datetime(key, format="%Y%m%d", errors="coerce")
        if pd.isna(date):
            continue
        rows.append({
            "Date": date,
            "Province": province,
            "District": district,
            "DataSource": source_name,
            "Temp_Max_C": parameters.get("T2M_MAX", {}).get(key),
            "Temp_Min_C": parameters.get("T2M_MIN", {}).get(key),
            "Rainfall_mm": parameters.get("PRECTOTCORR", {}).get(key),
        })
    return finalize_frame(pd.DataFrame(rows), source_name)


def clean_nasa_json(path, province, district):
    if not province or not district:
        raise ValueError("--nasa-province and --nasa-district are required for NASA JSON imports.")
    LOGGER.info("Loading NASA POWER JSON: %s", path)
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return nasa_parameters_to_frame(payload, province, district)


def fetch_nasa_power(latitude, longitude, start_date, end_date):
    params = {
        "parameters": "T2M_MAX,T2M_MIN,PRECTOTCORR",
        "community": "AG",
        "longitude": longitude,
        "latitude": latitude,
        "start": pd.to_datetime(start_date).strftime("%Y%m%d"),
        "end": pd.to_datetime(end_date).strftime("%Y%m%d"),
        "format": "JSON",
    }
    request_url = f"{NASA_POWER_URL}?{urlencode(params)}"
    LOGGER.info("Fetching NASA POWER data for %s,%s", latitude, longitude)
    with urlopen(request_url, timeout=180) as response:
        return json.loads(response.read().decode("utf-8"))


def clean_nasa_api(args):
    if not args.nasa_province or not args.nasa_district:
        raise ValueError("--nasa-province and --nasa-district are required for NASA API imports.")
    payload = fetch_nasa_power(args.nasa_latitude, args.nasa_longitude, args.start_date, args.end_date)
    return nasa_parameters_to_frame(payload, args.nasa_province, args.nasa_district)


def combine_sources(frames):
    if not frames:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    combined = pd.concat(frames, ignore_index=True)
    combined["_priority"] = combined["DataSource"].apply(source_rank)
    combined = combined.sort_values(["Date", "Province", "District", "_priority"])
    combined = combined.drop_duplicates(subset=["Date", "Province", "District"], keep="first")
    return combined.drop(columns=["_priority"])[OUTPUT_COLUMNS]


def ensure_data_source_column(cursor):
    cursor.execute("""
        ALTER TABLE climate_records
        ADD COLUMN IF NOT EXISTS data_source VARCHAR(100) NOT NULL DEFAULT 'Unknown'
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_data_source ON climate_records(data_source)")


def row_to_record(row):
    values = []
    for column in OUTPUT_COLUMNS:
        value = row.get(column)
        if value is None or pd.isna(value):
            values.append(None)
        else:
            values.append(value)
    return tuple(values)


def upsert_frame(df):
    if df.empty:
        return 0

    records = [row_to_record(row) for _, row in df.iterrows()]
    insert_columns = ", ".join(DB_COLUMNS)
    placeholders = "%s"
    update_columns = [column for column in DB_COLUMNS if column not in {"date", "province", "district"}]

    priority_case_existing = "CASE UPPER(REPLACE(REPLACE(climate_records.data_source, ' ', '_'), '-', '_')) " + " ".join(
        f"WHEN '{source}' THEN {priority}" for source, priority in SOURCE_PRIORITY.items()
    ) + " ELSE 90 END"
    priority_case_incoming = "CASE UPPER(REPLACE(REPLACE(EXCLUDED.data_source, ' ', '_'), '-', '_')) " + " ".join(
        f"WHEN '{source}' THEN {priority}" for source, priority in SOURCE_PRIORITY.items()
    ) + " ELSE 90 END"

    assignments = []
    for column in update_columns:
        if column in {"year", "month", "month_name", "data_source"}:
            assignments.append(
                f"{column} = CASE WHEN {priority_case_incoming} <= {priority_case_existing} "
                f"THEN EXCLUDED.{column} ELSE climate_records.{column} END"
            )
        else:
            assignments.append(
                f"{column} = CASE WHEN {priority_case_incoming} <= {priority_case_existing} "
                f"THEN COALESCE(EXCLUDED.{column}, climate_records.{column}) "
                f"ELSE COALESCE(climate_records.{column}, EXCLUDED.{column}) END"
            )
    assignments.append("updated_at = CURRENT_TIMESTAMP")

    query = f"""
        INSERT INTO climate_records ({insert_columns})
        VALUES {placeholders}
        ON CONFLICT (date, province, district) DO UPDATE SET
            {", ".join(assignments)}
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
            ensure_data_source_column(cursor)
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


def parse_args():
    parser = argparse.ArgumentParser(
        description="Integrate ZMD, NASA POWER, and portal-ready climate data into climate_records."
    )
    parser.add_argument("--portal-csv", action="append", type=Path, default=[], help="Portal-ready CSV to include. Can be passed more than once.")
    parser.add_argument("--zmd-csv", action="append", type=Path, default=[], help="ZMD CSV/Excel-export CSV to include. Can be passed more than once.")
    parser.add_argument("--zmd-province", default=None, help="Province to use when a ZMD CSV has no Province column.")
    parser.add_argument("--nasa-json", action="append", type=Path, default=[], help="NASA POWER JSON response file to include. Can be passed more than once.")
    parser.add_argument("--nasa-province", default=None, help="Province for NASA point data.")
    parser.add_argument("--nasa-district", default=None, help="District for NASA point data.")
    parser.add_argument("--fetch-nasa", action="store_true", help="Fetch NASA POWER data using the latitude/longitude and date arguments.")
    parser.add_argument("--nasa-latitude", type=float, default=None)
    parser.add_argument("--nasa-longitude", type=float, default=None)
    parser.add_argument("--start-date", default="2015-01-01")
    parser.add_argument("--end-date", default="2025-12-31")
    parser.add_argument("--output-cleaned", type=Path, default=Config.DATA_DIR / "integrated_climate_data.csv")
    parser.add_argument("--skip-db", action="store_true", help="Write the cleaned CSV but do not upsert PostgreSQL.")
    return parser.parse_args()


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = parse_args()

    frames = []
    for path in args.portal_csv:
        frames.append(clean_portal_csv(path))
    for path in args.zmd_csv:
        frames.append(clean_zmd_csv(path, province=args.zmd_province))
    for path in args.nasa_json:
        frames.append(clean_nasa_json(path, args.nasa_province, args.nasa_district))
    if args.fetch_nasa:
        if args.nasa_latitude is None or args.nasa_longitude is None:
            raise ValueError("--nasa-latitude and --nasa-longitude are required with --fetch-nasa.")
        frames.append(clean_nasa_api(args))

    combined = combine_sources(frames)
    args.output_cleaned.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(args.output_cleaned, index=False)
    LOGGER.info("Wrote %s cleaned records to %s", len(combined), args.output_cleaned)

    if args.skip_db:
        LOGGER.info("Skipped database upsert because --skip-db was used.")
        return

    upserted = upsert_frame(combined)
    LOGGER.info("Upserted %s records into climate_records.", upserted)


if __name__ == "__main__":
    main()
