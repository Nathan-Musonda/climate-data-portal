import argparse
import logging
from pathlib import Path

import pandas as pd


LOGGER = logging.getLogger(__name__)
BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = BASE_DIR / "data" / "processed" / "free_sources_zambia_climate_data.csv"
DEFAULT_OUTPUT = BASE_DIR / "data" / "processed" / "free_sources_zambia_climate_data_enriched.csv"
DEFAULT_WFP = BASE_DIR / "data" / "raw" / "wfp_food_prices_zambia.csv"


def normalize_name(value):
    return " ".join(str(value or "").strip().lower().split())


def load_wfp_food_prices(path, commodity=None):
    prices = pd.read_csv(path)
    prices["date"] = pd.to_datetime(prices["date"], errors="coerce")
    prices["price"] = pd.to_numeric(prices["price"], errors="coerce")
    prices = prices.dropna(subset=["date", "price"])

    if "currency" in prices.columns:
        prices = prices[prices["currency"].astype(str).str.upper() == "ZMW"]
    if commodity:
        prices = prices[prices["commodity"].astype(str).str.lower() == commodity.lower()]

    prices["Year"] = prices["date"].dt.year
    prices["Month"] = prices["date"].dt.month
    prices["province_key"] = prices["admin1"].map(normalize_name)
    prices["district_key"] = prices["admin2"].map(normalize_name)

    district_month = (
        prices.groupby(["Year", "Month", "province_key", "district_key"], dropna=False)["price"]
        .mean()
        .reset_index()
        .rename(columns={"price": "FoodPrice_ZMW_district"})
    )
    province_month = (
        prices.groupby(["Year", "Month", "province_key"], dropna=False)["price"]
        .mean()
        .reset_index()
        .rename(columns={"price": "FoodPrice_ZMW_province"})
    )
    return district_month, province_month


def enrich_food_prices(dataset, wfp_path, commodity=None):
    district_month, province_month = load_wfp_food_prices(wfp_path, commodity=commodity)
    work = dataset.copy()
    work["province_key"] = work["Province"].map(normalize_name)
    work["district_key"] = work["District"].map(normalize_name)

    work = work.merge(
        district_month,
        on=["Year", "Month", "province_key", "district_key"],
        how="left",
    )
    work = work.merge(
        province_month,
        on=["Year", "Month", "province_key"],
        how="left",
    )

    existing = pd.to_numeric(work.get("FoodPrice_ZMW"), errors="coerce")
    district_values = pd.to_numeric(work["FoodPrice_ZMW_district"], errors="coerce")
    province_values = pd.to_numeric(work["FoodPrice_ZMW_province"], errors="coerce")
    work["FoodPrice_ZMW"] = existing.fillna(district_values).fillna(province_values).round(2)
    work = work.drop(columns=[
        "province_key",
        "district_key",
        "FoodPrice_ZMW_district",
        "FoodPrice_ZMW_province",
    ])
    return work


def parse_args():
    parser = argparse.ArgumentParser(description="Enrich a portal CSV with downloaded free context datasets.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--wfp-food-prices", type=Path, default=DEFAULT_WFP)
    parser.add_argument("--commodity", default="Maize (white)")
    return parser.parse_args()


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    args = parse_args()
    dataset = pd.read_csv(args.input)
    LOGGER.info("Loaded %s portal rows from %s", len(dataset), args.input)

    if args.wfp_food_prices.exists():
        dataset = enrich_food_prices(dataset, args.wfp_food_prices, commodity=args.commodity)
        filled = pd.to_numeric(dataset["FoodPrice_ZMW"], errors="coerce").notna().sum()
        LOGGER.info("FoodPrice_ZMW populated for %s rows using %s", filled, args.wfp_food_prices)
    else:
        LOGGER.warning("WFP food price file not found: %s", args.wfp_food_prices)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    dataset.to_csv(args.output, index=False)
    LOGGER.info("Wrote enriched dataset to %s", args.output)


if __name__ == "__main__":
    main()
