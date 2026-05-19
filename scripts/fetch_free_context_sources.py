import argparse
import csv
import json
import logging
from pathlib import Path

import requests


LOGGER = logging.getLogger(__name__)
BASE_DIR = Path(__file__).resolve().parents[1]
RAW_DIR = BASE_DIR / "data" / "raw"


def request_json(method, url, *, params=None, json_body=None, timeout=60):
    response = requests.request(method, url, params=params, json=json_body, timeout=timeout)
    response.raise_for_status()
    return response.json()


def fetch_wfp_food_prices(output_dir):
    package_url = "https://data.humdata.org/api/3/action/package_show"
    package = request_json("GET", package_url, params={"id": "wfp-food-prices-for-zambia"})
    resources = package.get("result", {}).get("resources", [])
    csv_resource = next(
        (
            resource for resource in resources
            if str(resource.get("format", "")).lower() == "csv" and resource.get("url")
        ),
        None,
    )
    if not csv_resource:
        raise RuntimeError("No CSV resource found for WFP Zambia food prices on HDX.")

    output_path = output_dir / "wfp_food_prices_zambia.csv"
    LOGGER.info("Downloading WFP food prices from %s", csv_resource["url"])
    response = requests.get(csv_resource["url"], timeout=180)
    response.raise_for_status()
    output_path.write_bytes(response.content)
    return output_path


def fetch_reliefweb_events(output_dir, limit=100):
    url = "https://api.reliefweb.int/v1/reports"
    payload = {
        "query": {"value": "Zambia flood drought heatwave climate"},
        "filter": {"field": "country", "value": "Zambia"},
        "sort": ["date.created:desc"],
        "limit": limit,
        "fields": {
            "include": [
                "date.created",
                "title",
                "url",
                "source",
                "disaster_type",
                "primary_country",
            ]
        },
    }
    data = request_json("POST", url, json_body=payload)
    rows = []
    for item in data.get("data", []):
        fields = item.get("fields", {})
        created = fields.get("date", {}).get("created")
        disaster_types = fields.get("disaster_type") or []
        sources = fields.get("source") or []
        rows.append({
            "date": created[:10] if created else "",
            "title": fields.get("title", ""),
            "url": fields.get("url", ""),
            "disaster_types": "; ".join(sorted({entry.get("name", "") for entry in disaster_types if entry.get("name")})),
            "sources": "; ".join(sorted({entry.get("name", "") for entry in sources if entry.get("name")})),
        })

    output_path = output_dir / "reliefweb_zambia_climate_events.csv"
    with open(output_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["date", "title", "url", "disaster_types", "sources"])
        writer.writeheader()
        writer.writerows(rows)
    return output_path


def write_manifest(output_dir, outputs, errors):
    manifest = {
        "outputs": {key: str(path) for key, path in outputs.items()},
        "errors": errors,
        "sources": {
            "open_meteo": "https://open-meteo.com/en/docs/historical-weather-api",
            "wfp_hdx_food_prices": "https://data.humdata.org/dataset/wfp-food-prices-for-zambia",
            "reliefweb": "https://apidoc.reliefweb.int/",
            "modis_ndvi": "https://developers.google.com/earth-engine/datasets/catalog/MODIS_061_MOD13Q1",
            "world_bank_cckp": "https://worldbank.github.io/climateknowledgeportal/",
            "faostat": "https://www.fao.org/faostat/",
        },
    }
    output_path = output_dir / "free_source_manifest.json"
    output_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return output_path


def parse_args():
    parser = argparse.ArgumentParser(description="Fetch free context datasets for the Zambia climate portal.")
    parser.add_argument("--output-dir", type=Path, default=RAW_DIR)
    parser.add_argument("--skip-wfp", action="store_true")
    parser.add_argument("--skip-reliefweb", action="store_true")
    parser.add_argument("--reliefweb-limit", type=int, default=100)
    return parser.parse_args()


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {}
    errors = {}

    if not args.skip_wfp:
        try:
            outputs["wfp_food_prices"] = fetch_wfp_food_prices(args.output_dir)
        except Exception as error:
            LOGGER.error("WFP food price fetch failed: %s", error)
            errors["wfp_food_prices"] = str(error)

    if not args.skip_reliefweb:
        try:
            outputs["reliefweb_events"] = fetch_reliefweb_events(args.output_dir, limit=args.reliefweb_limit)
        except Exception as error:
            LOGGER.error("ReliefWeb fetch failed: %s", error)
            errors["reliefweb_events"] = str(error)

    outputs["manifest"] = write_manifest(args.output_dir, outputs, errors)
    LOGGER.info("Wrote source manifest to %s", outputs["manifest"])


if __name__ == "__main__":
    main()
