from flask import Blueprint, request 
import csv
import io
import logging 
import time
import pandas as pd
from flask import Response
from utils.database import db_manager 
from utils.data_loader import load_data_from_db, get_filter_options_from_db 
from utils.aggregations import get_overview, rainfall_trend, temperature_trend, drought_summary, drought_trend, drought_indicator_trends, ndvi_trend, soil_moisture_trend, impact_trends, impact_driver_breakdown, summarize_population_affected 
from utils.live_weather import get_live_weather
from utils.monthly import (
    MONTH_SEQUENCE,
    apply_monthly_chart_metadata,
    build_empty_monthly_chart_payload,
    build_monthly_chart_payload as shared_build_monthly_chart_payload,
    expand_monthly_periods,
    month_label_from_number,
    prepare_monthly_frame,
    use_monthly_periods,
)
from utils.responses import success_response, error_response, empty_response 

logger = logging.getLogger(__name__) 
api_v1 = Blueprint('api_v1', __name__, url_prefix='/api/v1') 

def normalize_name(value):
    return " ".join(str(value or "").strip().lower().split())

def build_filters(include_year=True):
    filters = {}
    province = request.args.get('province')
    if province and province.lower() != 'all':
        filters['province'] = province
    district = request.args.get('district')
    if district and district.lower() != 'all':
        filters['district'] = district

    if include_year:
        year = request.args.get('year', type=int)
        if year:
            filters['year'] = year

    return filters

DROUGHT_SCORE_MAP = {
    "No Drought": 0,
    "Mild": 1,
    "Moderate": 2,
    "Severe": 3
}

DISTRICT_COMPARISON_METRICS = {
    "rainfall": {
        "column": "Rainfall_mm",
        "label": "Average Rainfall",
        "unit": "mm",
        "agg": "mean",
        "decimals": 1
    },
    "temperature": {
        "column": "Temp_Max_C",
        "label": "Average Max Temperature",
        "unit": "C",
        "agg": "mean",
        "decimals": 1
    },
    "soil_moisture": {
        "column": "SoilMoisture_pct",
        "label": "Average Soil Moisture",
        "unit": "%",
        "agg": "mean",
        "decimals": 1
    },
    "ndvi": {
        "column": "NDVI",
        "label": "Average NDVI",
        "unit": "",
        "agg": "mean",
        "decimals": 3
    },
    "population": {
        "column": "PopulationAffected",
        "label": "Population Affected",
        "unit": "people",
        "agg": "sum",
        "decimals": 0
    },
    "drought": {
        "column": "DroughtSeverity",
        "label": "Average Drought Score",
        "unit": "score",
        "agg": "score_mean",
        "decimals": 2
    }
}

DEFAULT_DISTRICT_COMPARISON_METRICS = [
    "rainfall",
    "temperature",
    "soil_moisture",
    "ndvi",
    "population",
    "drought"
]

EXPLORER_VARIABLES = {
    "Rainfall_mm": {
        "label": "Rainfall",
        "unit": "mm",
        "summary_label": "Average rainfall",
        "decimals": 1,
        "color": "#1565C0"
    },
    "Temp_Max_C": {
        "label": "Maximum Temperature",
        "unit": "C",
        "summary_label": "Average max temperature",
        "decimals": 1,
        "color": "#C62828"
    },
    "Temp_Min_C": {
        "label": "Minimum Temperature",
        "unit": "C",
        "summary_label": "Average min temperature",
        "decimals": 1,
        "color": "#EF6C00"
    },
    "SoilMoisture_pct": {
        "label": "Soil Moisture",
        "unit": "%",
        "summary_label": "Average soil moisture",
        "decimals": 1,
        "color": "#2E7D32"
    },
    "NDVI": {
        "label": "NDVI",
        "unit": "",
        "summary_label": "Average NDVI",
        "decimals": 3,
        "color": "#558B2F"
    },
    "SPI": {
        "label": "SPI",
        "unit": "",
        "summary_label": "Average SPI",
        "decimals": 2,
        "color": "#6A1B9A"
    },
    "SPEI": {
        "label": "SPEI",
        "unit": "",
        "summary_label": "Average SPEI",
        "decimals": 2,
        "color": "#8E24AA"
    },
    "PDSI": {
        "label": "PDSI",
        "unit": "",
        "summary_label": "Average PDSI",
        "decimals": 2,
        "color": "#5E35B1"
    }
}

SITE_SUMMARY_CACHE = {
    "value": None,
    "expires_at": 0
}
SITE_SUMMARY_TTL_SECONDS = 300


def list_district_comparison_metrics():
    return [
        {
            "key": key,
            "label": config["label"],
            "unit": config["unit"]
        }
        for key, config in DISTRICT_COMPARISON_METRICS.items()
    ]


def round_metric_value(metric_key, value):
    if value is None:
        return None

    config = DISTRICT_COMPARISON_METRICS.get(metric_key)
    if not config:
        return value

    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None

    decimals = config.get("decimals", 2)
    if decimals == 0:
        return int(round(numeric))
    return round(numeric, decimals)


def aggregate_metric_value(df, metric_key):
    if df is None or df.empty:
        return None

    config = DISTRICT_COMPARISON_METRICS.get(metric_key)
    if not config:
        return None

    column = config["column"]
    agg = config["agg"]

    if column not in df.columns:
        return None

    if agg == "mean":
        series = df[column].dropna()
        if series.empty:
            return None
        return round_metric_value(metric_key, series.mean())

    if agg == "sum":
        if column == "PopulationAffected":
            return round_metric_value(metric_key, summarize_population_affected(df))
        series = df[column].fillna(0)
        if series.empty:
            return None
        return round_metric_value(metric_key, series.sum())

    if agg == "score_mean":
        work = df[[column]].dropna().copy()
        if work.empty:
            return None
        work["drought_score"] = work[column].map(DROUGHT_SCORE_MAP)
        scored = work["drought_score"].dropna()
        if scored.empty:
            return None
        return round_metric_value(metric_key, scored.mean())

    return None


def get_dominant_drought_severity(values):
    series = pd.Series(values).dropna().astype(str).str.strip()
    if series.empty:
        return None

    counts = series.value_counts()
    max_count = counts.max()
    tied = [severity for severity, count in counts.items() if count == max_count]
    tied.sort(key=lambda severity: DROUGHT_SCORE_MAP.get(severity, -1), reverse=True)
    return tied[0] if tied else None


PROJECTION_METRICS = {
    "rainfall": {
        "column": "Rainfall_mm",
        "label": "Average Rainfall",
        "unit": "mm",
        "agg": "mean",
        "decimals": 1
    },
    "temperature": {
        "column": "Temp_Max_C",
        "label": "Average Max Temperature",
        "unit": "C",
        "agg": "mean",
        "decimals": 1
    },
    "drought": {
        "column": "DroughtSeverity",
        "label": "Average Drought Severity Score",
        "unit": "score",
        "agg": "score_mean",
        "decimals": 2
    },
    "population": {
        "column": "PopulationAffected",
        "label": "Population Affected",
        "unit": "people",
        "agg": "sum",
        "decimals": 0
    }
}

PROJECTION_SCENARIOS = {
    "baseline": {
        "label": "Historical trend",
        "description": "Extends the observed historical trend without additional scenario pressure."
    },
    "rcp45": {
        "label": "RCP 4.5 style",
        "description": "Moderate-emissions planning pathway with slower warming and impact growth."
    },
    "rcp85": {
        "label": "RCP 8.5 style",
        "description": "High-emissions stress pathway with stronger warming and impact pressure."
    }
}

SCENARIO_ADJUSTMENTS = {
    "baseline": {
        "rainfall": {"mode": "percent", "annual": 0.0, "spread": 0.06},
        "temperature": {"mode": "absolute", "annual": 0.0, "spread": 0.08},
        "drought": {"mode": "absolute", "annual": 0.0, "spread": 0.08},
        "population": {"mode": "percent", "annual": 0.0, "spread": 0.08}
    },
    "rcp45": {
        "rainfall": {"mode": "percent", "annual": -0.0015, "spread": 0.10},
        "temperature": {"mode": "absolute", "annual": 0.018, "spread": 0.12},
        "drought": {"mode": "absolute", "annual": 0.015, "spread": 0.14},
        "population": {"mode": "percent", "annual": 0.015, "spread": 0.15}
    },
    "rcp85": {
        "rainfall": {"mode": "percent", "annual": -0.003, "spread": 0.16},
        "temperature": {"mode": "absolute", "annual": 0.035, "spread": 0.18},
        "drought": {"mode": "absolute", "annual": 0.035, "spread": 0.22},
        "population": {"mode": "percent", "annual": 0.03, "spread": 0.24}
    }
}


def _linear_projection(points, horizon, decimals):
    clean_points = [
        (int(year), float(value))
        for year, value in points
        if year is not None and value is not None and pd.notna(value)
    ]
    clean_points.sort(key=lambda item: item[0])

    if not clean_points:
        return [], [], 0

    years = [point[0] for point in clean_points]
    values = [point[1] for point in clean_points]

    if len(clean_points) == 1:
        slope = 0.0
        intercept = values[0]
    else:
        mean_year = sum(years) / len(years)
        mean_value = sum(values) / len(values)
        denominator = sum((year - mean_year) ** 2 for year in years)
        slope = (
            sum((year - mean_year) * (value - mean_value) for year, value in clean_points) / denominator
            if denominator
            else 0.0
        )
        intercept = mean_value - (slope * mean_year)

    last_year = max(years)
    projection_years = [last_year + offset for offset in range(1, horizon + 1)]
    projected_values = [
        round(max(0.0, (slope * year) + intercept), decimals)
        for year in projection_years
    ]
    historical_values = [round(value, decimals) for value in values]

    return (
        [{"year": year, "value": value} for year, value in zip(years, historical_values)],
        [{"year": year, "value": value} for year, value in zip(projection_years, projected_values)],
        round(slope, decimals)
    )


def _scenario_value(metric_key, baseline_value, years_ahead, scenario_key):
    adjustment = SCENARIO_ADJUSTMENTS.get(scenario_key, SCENARIO_ADJUSTMENTS["baseline"]).get(metric_key)
    if not adjustment:
        return baseline_value

    if adjustment["mode"] == "percent":
        return baseline_value * ((1 + adjustment["annual"]) ** years_ahead)
    return baseline_value + (adjustment["annual"] * years_ahead)


def _build_scenario_projection(metric_key, projected, last_year, decimals, scenario_key):
    adjustment = SCENARIO_ADJUSTMENTS.get(scenario_key, SCENARIO_ADJUSTMENTS["baseline"]).get(metric_key, {})
    spread = float(adjustment.get("spread", 0.1))
    scenario_points = []

    for point in projected:
        year = int(point["year"])
        years_ahead = max(0, year - int(last_year))
        value = _scenario_value(metric_key, float(point["value"]), years_ahead, scenario_key)
        value = max(0.0, value)
        scenario_points.append({
            "year": year,
            "value": round(value, decimals),
            "low": round(max(0.0, value * (1 - spread)), decimals),
            "high": round(max(0.0, value * (1 + spread)), decimals)
        })

    return scenario_points


def _build_projection_series(df, metric_key, horizon, selected_scenario="rcp45"):
    config = PROJECTION_METRICS[metric_key]
    column = config["column"]
    decimals = config["decimals"]

    if column not in df.columns or "year" not in df.columns or df.empty:
        return {
            "metric": metric_key,
            "label": config["label"],
            "unit": config["unit"],
            "historical": [],
            "projected": [],
            "scenario_projected": [],
            "scenarios": {},
            "annual_change": None
        }

    projection_columns = ["year", column]
    if column == "PopulationAffected" and "district" in df.columns:
        projection_columns.append("district")
    work = df[projection_columns].dropna().copy()
    if work.empty:
        yearly_points = []
    elif config["agg"] == "sum":
        if column == "PopulationAffected":
            yearly = summarize_population_affected(work, ["year"])
            yearly_points = yearly[["year", column]].values.tolist() if not yearly.empty else []
        else:
            yearly = work.groupby("year")[column].sum().reset_index()
            yearly_points = yearly[["year", column]].values.tolist()
    elif config["agg"] == "score_mean":
        work["score"] = work[column].map(DROUGHT_SCORE_MAP)
        yearly = work.dropna(subset=["score"]).groupby("year")["score"].mean().reset_index()
        yearly_points = yearly[["year", "score"]].values.tolist()
    else:
        yearly = work.groupby("year")[column].mean().reset_index()
        yearly_points = yearly[["year", column]].values.tolist()

    historical, projected, annual_change = _linear_projection(yearly_points, horizon, decimals)
    last_year = historical[-1]["year"] if historical else None
    scenarios = {}
    if last_year is not None:
        for scenario_key in PROJECTION_SCENARIOS:
            scenarios[scenario_key] = _build_scenario_projection(
                metric_key,
                projected,
                last_year,
                decimals,
                scenario_key
            )

    return {
        "metric": metric_key,
        "label": config["label"],
        "unit": config["unit"],
        "historical": historical,
        "projected": projected,
        "scenario_projected": scenarios.get(selected_scenario, projected),
        "scenarios": scenarios,
        "annual_change": annual_change
    }


def get_monthly_notification_tone(drought_severity=None, population_affected=0, avg_temp=None, avg_rainfall=None, avg_ndvi=None):
    if drought_severity == "Severe" or int(population_affected or 0) >= 1000:
        return "danger"

    if drought_severity == "Moderate" or int(population_affected or 0) > 0:
        return "warning"

    if avg_temp is not None and float(avg_temp) >= 35:
        return "warning"

    if avg_rainfall is not None and float(avg_rainfall) >= 150:
        return "warning"

    if avg_ndvi is not None and float(avg_ndvi) >= 0.55 and drought_severity in {None, "No Drought", "Mild"}:
        return "success"

    return "info"


def build_missing_month_notification_item(month, year, district=None, province=None):
    month_label = month_label_from_number(month)
    district_name = str(district or "").strip()
    province_name = str(province or "").strip()
    title = f"{month_label} {year}" if year else month_label

    if district_name:
        body = f"No climate records were available for {district_name} in {month_label} {year}."
    elif province_name:
        body = f"No climate records were available for {province_name} in {month_label} {year}."
    else:
        body = f"No climate records were available in {month_label} {year}."

    return {
        "month": month,
        "month_label": month_label,
        "district": district_name or None,
        "province": province_name or None,
        "tone": "info",
        "meta": province_name or ("District update" if district_name else "Monthly overview"),
        "title": title,
        "body": body
    }


def build_monthly_notification_items(df, year, district_filter=None, province_filter=None):
    if year is None:
        return []

    district_name = str(district_filter or "").strip()
    province_name = str(province_filter or "").strip()

    if df is None or df.empty or "month" not in df.columns:
        return [
            build_missing_month_notification_item(month, year, district=district_name, province=province_name)
            for month in MONTH_SEQUENCE
        ]

    work = df.copy()
    work = prepare_monthly_frame(work, "month")
    if work.empty:
        return [
            build_missing_month_notification_item(month, year, district=district_name, province=province_name)
            for month in MONTH_SEQUENCE
        ]

    if "district" in work.columns:
        work["district"] = work["district"].fillna("").astype(str).str.strip()
    else:
        work["district"] = ""

    if "province" in work.columns:
        work["province"] = work["province"].fillna("").astype(str).str.strip()
    else:
        work["province"] = ""

    if district_name and not province_name:
        province_candidates = work.loc[work["province"] != "", "province"].drop_duplicates().tolist()
        province_name = str(province_candidates[0]).strip() if province_candidates else ""

    population_lookup = {}
    if "PopulationAffected" in work.columns:
        population_rows = summarize_population_affected(work, ["month"])
        if isinstance(population_rows, pd.DataFrame) and not population_rows.empty:
            population_lookup = {
                int(row["month"]): int(row["PopulationAffected"] or 0)
                for _, row in population_rows.iterrows()
            }

    grouped = (
        work.groupby("month", dropna=False)
        .agg(
            avg_rainfall=("Rainfall_mm", "mean"),
            avg_temp_max=("Temp_Max_C", "mean"),
            avg_ndvi=("NDVI", "mean")
        )
        .reset_index()
    )
    grouped_lookup = {
        int(row["month"]): row
        for _, row in grouped.iterrows()
    }

    district_count_lookup = {}
    district_rows = work[work["district"] != ""]
    if not district_rows.empty:
        district_count_lookup = (
            district_rows.groupby("month")["district"]
            .nunique()
            .astype(int)
            .to_dict()
        )

    province_count_lookup = {}
    province_rows = work[work["province"] != ""]
    if not province_rows.empty:
        province_count_lookup = (
            province_rows.groupby("month")["province"]
            .nunique()
            .astype(int)
            .to_dict()
        )

    items = []
    for month in MONTH_SEQUENCE:
        month_df = work[work["month"] == month]
        if month_df.empty:
            items.append(
                build_missing_month_notification_item(
                    month,
                    year,
                    district=district_name,
                    province=province_name
                )
            )
            continue

        row = grouped_lookup.get(month)
        dominant_drought = get_dominant_drought_severity(month_df.get("DroughtSeverity"))
        population_affected = population_lookup.get(month, 0)
        district_count = int(district_count_lookup.get(month, 0))
        province_count = int(province_count_lookup.get(month, 0))

        avg_rainfall = round_metric_value("rainfall", row.get("avg_rainfall") if row is not None else None)
        avg_temp_max = round_metric_value("temperature", row.get("avg_temp_max") if row is not None else None)
        avg_ndvi = round_metric_value("ndvi", row.get("avg_ndvi") if row is not None else None)

        parts = []
        if not district_name:
            district_label = "district" if district_count == 1 else "districts"
            province_label = "province" if province_count == 1 else "provinces"
            if province_name and district_count:
                parts.append(f"{district_count} {district_label} reported")
            elif district_count and province_count:
                parts.append(f"{district_count} {district_label} across {province_count} {province_label} reported")
            elif district_count:
                parts.append(f"{district_count} {district_label} reported")
            elif province_count:
                parts.append(f"{province_count} {province_label} reported")
        if avg_rainfall is not None:
            parts.append(f"rainfall averaged {avg_rainfall} mm")
        if avg_temp_max is not None:
            parts.append(f"max temperature averaged {avg_temp_max} C")
        if dominant_drought:
            parts.append(f"dominant drought was {dominant_drought.lower()}")
        if avg_ndvi is not None:
            parts.append(f"NDVI averaged {avg_ndvi}")
        if population_affected:
            parts.append(f"{population_affected:,} people were recorded as affected")

        body_text = "; ".join(parts)
        body = (
            f"{body_text[:1].upper()}{body_text[1:]}."
            if body_text
            else "Climate records were available, but the tracked indicators were incomplete for this month."
        )

        items.append({
            "month": month,
            "month_label": month_label_from_number(month),
            "district": district_name or None,
            "province": province_name or None,
            "tone": get_monthly_notification_tone(
                drought_severity=dominant_drought,
                population_affected=population_affected,
                avg_temp=avg_temp_max,
                avg_rainfall=avg_rainfall,
                avg_ndvi=avg_ndvi
            ),
            "meta": province_name or ("District update" if district_name else "Monthly overview"),
            "title": f"{month_label_from_number(month)} {year}",
            "body": body
        })

    return items


def build_monthly_district_notification_items(df, year, district_filter=None):
    return build_monthly_notification_items(df, year, district_filter=district_filter)


def get_explorer_variable_options():
    return [
        {
            "key": key,
            "label": config["label"],
            "unit": config["unit"]
        }
        for key, config in EXPLORER_VARIABLES.items()
    ]


def parse_explorer_filters():
    return {
        "province": request.args.get('province', 'all').strip(),
        "district": request.args.get('district', 'all').strip(),
        "start_year": request.args.get('start_year', type=int),
        "end_year": request.args.get('end_year', type=int),
        "variable": request.args.get('variable', 'Rainfall_mm').strip()
    }


def format_explorer_number(value, decimals=2):
    if value is None or pd.isna(value):
        return None
    try:
        return round(float(value), decimals)
    except (TypeError, ValueError):
        return None


def build_empty_monthly_series_response(value_keys, extra=None):
    payload = build_empty_monthly_chart_payload(value_keys)
    if extra:
        payload.update(extra)
    return payload


def build_monthly_chart_payload(rows, value_keys, fill_values=None):
    return shared_build_monthly_chart_payload(rows, value_keys, fill_values=fill_values)


def expand_monthly_periods_df(grouped, period_col="month"):
    return expand_monthly_periods(grouped, period_col)


def get_explorer_date_column(df):
    for candidate in ('date', 'Date'):
        if candidate in df.columns:
            return candidate
    return None


def filter_explorer_df(df, filters):
    if df is None or df.empty:
        return df

    work = df.copy()
    province = filters.get("province")
    district = filters.get("district")
    start_year = filters.get("start_year")
    end_year = filters.get("end_year")

    if province and province.lower() != 'all' and 'province' in work.columns:
        work = work[work['province'] == province]

    if district and district.lower() != 'all' and 'district' in work.columns:
        work = work[work['district'] == district]

    if 'year' in work.columns:
        if start_year is not None:
            work = work[work['year'] >= start_year]
        if end_year is not None:
            work = work[work['year'] <= end_year]

    return work


def build_explorer_trend(df, variable, force_monthly=False):
    config = EXPLORER_VARIABLES[variable]
    if df is None or variable not in df.columns or 'year' not in df.columns:
        if force_monthly:
            return build_empty_monthly_series_response(
                ["values"],
                extra={
                    "variable": variable,
                    "label": config["label"],
                    "unit": config["unit"],
                    "color": config["color"]
                }
            )
        return {
            "labels": [],
            "values": [],
            "period_type": "year",
            "variable": variable,
            "label": config["label"],
            "unit": config["unit"],
            "color": config["color"]
        }

    monthly = force_monthly or use_monthly_periods(df)
    period_col = 'month' if monthly else 'year'
    if monthly:
        source = prepare_monthly_frame(df[[period_col, variable]], period_col)
        source = source.dropna(subset=[variable]).copy()
    else:
        source = (
            df[[period_col, variable]]
            .assign(**{period_col: pd.to_numeric(df[period_col], errors='coerce')})
            .dropna(subset=[period_col, variable])
            .sort_values(period_col)
        )

    grouped = (
        source.groupby(period_col)[variable]
        .mean()
        .reset_index()
        .sort_values(period_col)
    ) if not source.empty else pd.DataFrame(columns=[period_col, variable])
    if monthly:
        grouped = expand_monthly_periods_df(grouped, period_col)

    if not grouped.empty and not monthly:
        labels = [str(int(year)) for year in grouped[period_col].tolist()]
        values = [format_explorer_number(value, config["decimals"]) for value in grouped[variable].tolist()]
    elif monthly:
        labels = grouped[period_col].tolist()
        values = [format_explorer_number(value, config["decimals"]) for value in grouped[variable].tolist()]
    else:
        labels = []
        values = []

    payload = {
        "labels": labels,
        "values": values,
        "period_type": "month" if monthly else "year",
        "variable": variable,
        "label": config["label"],
        "unit": config["unit"],
        "color": config["color"]
    }
    if monthly:
        return apply_monthly_chart_metadata(payload, source, period_col)
    return payload


def build_explorer_summary(df, variable):
    config = EXPLORER_VARIABLES[variable]
    if df is None or df.empty:
        return {
            "record_count": 0,
            "province_count": 0,
            "district_count": 0,
            "summary_label": config["summary_label"],
            "average_value": None,
            "minimum_value": None,
            "maximum_value": None,
            "most_common_drought_severity": None
        }

    series = df[variable].dropna() if variable in df.columns else None
    drought_mode = None
    if 'DroughtSeverity' in df.columns:
        drought_values = df['DroughtSeverity'].dropna()
        if not drought_values.empty:
            drought_mode = str(drought_values.mode().iloc[0])

    return {
        "record_count": int(len(df)),
        "province_count": int(df['province'].nunique()) if 'province' in df.columns else 0,
        "district_count": int(df['district'].nunique()) if 'district' in df.columns else 0,
        "summary_label": config["summary_label"],
        "average_value": format_explorer_number(series.mean(), config["decimals"]) if series is not None and not series.empty else None,
        "minimum_value": format_explorer_number(series.min(), config["decimals"]) if series is not None and not series.empty else None,
        "maximum_value": format_explorer_number(series.max(), config["decimals"]) if series is not None and not series.empty else None,
        "most_common_drought_severity": drought_mode
    }


def build_explorer_rows(df, limit=None):
    if df is None or df.empty:
        return []

    work = df.copy()
    date_col = get_explorer_date_column(work)
    if date_col:
        work[date_col] = work[date_col].astype(str)
        work = work.sort_values(date_col, ascending=False)
    elif 'year' in work.columns:
        sort_columns = ['year']
        if 'month' in work.columns:
            sort_columns.append('month')
        work = work.sort_values(sort_columns, ascending=False)

    rows = []
    row_source = work.head(limit) if limit is not None else work
    for _, row in row_source.iterrows():
        rows.append({
            "date": row.get(date_col) if date_col else None,
            "province": row.get('province'),
            "district": row.get('district'),
            "year": int(row['year']) if row.get('year') is not None and str(row.get('year')).strip() != '' else None,
            "month": int(row['month']) if row.get('month') is not None and str(row.get('month')).strip() != '' else None,
            "Rainfall_mm": format_explorer_number(row.get('Rainfall_mm'), 1),
            "Temp_Max_C": format_explorer_number(row.get('Temp_Max_C'), 1),
            "Temp_Min_C": format_explorer_number(row.get('Temp_Min_C'), 1),
            "SoilMoisture_pct": format_explorer_number(row.get('SoilMoisture_pct'), 1),
            "NDVI": format_explorer_number(row.get('NDVI'), 3),
            "SPI": format_explorer_number(row.get('SPI'), 2),
            "SPEI": format_explorer_number(row.get('SPEI'), 2),
            "PDSI": format_explorer_number(row.get('PDSI'), 2),
            "DroughtSeverity": row.get('DroughtSeverity')
        })
    return rows


def build_rankings_for_metric(df_year, metric):
    if df_year is None or df_year.empty or 'province' not in df_year.columns:
        return []

    work = df_year.copy()

    if metric == 'rainfall' and 'Rainfall_mm' in work.columns:
        grouped = work.groupby('province')['Rainfall_mm'].mean().reset_index(name='value')
    elif metric == 'temperature' and 'Temp_Max_C' in work.columns:
        grouped = work.groupby('province')['Temp_Max_C'].mean().reset_index(name='value')
    elif metric == 'ndvi' and 'NDVI' in work.columns:
        grouped = work.groupby('province')['NDVI'].mean().reset_index(name='value')
    elif metric == 'drought' and 'DroughtSeverity' in work.columns:
        work['drought_score'] = work['DroughtSeverity'].map(DROUGHT_SCORE_MAP).fillna(0)
        grouped = work.groupby('province')['drought_score'].mean().reset_index(name='value')
    else:
        return []

    grouped = grouped.sort_values('value', ascending=False).head(1)
    return [
        {
            "province": row['province'],
            "value": round(float(row['value']), 2)
        }
        for _, row in grouped.iterrows()
    ]


def get_top_province_metric_for_year(year, metric):
    if year is None:
        return []

    metric = (metric or '').strip().lower()
    query = None

    if metric == 'rainfall':
        query = (
            "SELECT province, ROUND(AVG(rainfall_mm)::numeric, 2) AS value "
            "FROM climate_records "
            "WHERE year = %s AND province IS NOT NULL AND rainfall_mm IS NOT NULL "
            "GROUP BY province "
            "ORDER BY AVG(rainfall_mm) DESC "
            "LIMIT 1"
        )
    elif metric == 'temperature':
        query = (
            "SELECT province, ROUND(AVG(temp_max_c)::numeric, 2) AS value "
            "FROM climate_records "
            "WHERE year = %s AND province IS NOT NULL AND temp_max_c IS NOT NULL "
            "GROUP BY province "
            "ORDER BY AVG(temp_max_c) DESC "
            "LIMIT 1"
        )
    elif metric == 'ndvi':
        query = (
            "SELECT province, ROUND(AVG(ndvi)::numeric, 2) AS value "
            "FROM climate_records "
            "WHERE year = %s AND province IS NOT NULL AND ndvi IS NOT NULL "
            "GROUP BY province "
            "ORDER BY AVG(ndvi) DESC "
            "LIMIT 1"
        )
    elif metric == 'drought':
        query = (
            "SELECT province, ROUND(AVG(CASE drought_severity "
            "WHEN 'No Drought' THEN 0 "
            "WHEN 'Mild' THEN 1 "
            "WHEN 'Moderate' THEN 2 "
            "WHEN 'Severe' THEN 3 "
            "ELSE 0 END)::numeric, 2) AS value "
            "FROM climate_records "
            "WHERE year = %s AND province IS NOT NULL AND drought_severity IS NOT NULL "
            "GROUP BY province "
            "ORDER BY AVG(CASE drought_severity "
            "WHEN 'No Drought' THEN 0 "
            "WHEN 'Mild' THEN 1 "
            "WHEN 'Moderate' THEN 2 "
            "WHEN 'Severe' THEN 3 "
            "ELSE 0 END) DESC "
            "LIMIT 1"
        )
    else:
        return []

    rows = db_manager.execute_query(query, [year]) or []
    return [
        {
            "province": row['province'],
            "value": float(row['value']) if row.get('value') is not None else None
        }
        for row in rows
        if row.get('province')
    ]


def format_site_summary_value(value, decimals=1):
    try:
        return f"{float(value):.{decimals}f}"
    except (TypeError, ValueError):
        return None


def build_site_update_item(kind, category, title, date_label, body, tone="info", ticker_message=None):
    return {
        "kind": kind,
        "category": category,
        "title": title,
        "date_label": date_label,
        "body": body,
        "tone": tone,
        "ticker_message": ticker_message or body
    }


def build_live_weather_payload(weather):
    if not weather:
        return {
            "source": "Live weather",
            "climate_updates": [],
            "ticker_items": []
        }

    location_label = weather.get("location_name") or "your current area"
    observed_label = weather.get("observed_at_label") or "Latest weather update"
    weather_main = str(weather.get("weather_main") or "").strip()
    weather_description = str(
        weather.get("weather_description") or weather_main or "current conditions"
    ).strip()
    description_label = weather_description.capitalize()
    temperature_c = format_site_summary_value(weather.get("temperature_c"), 1)
    feels_like_c = format_site_summary_value(weather.get("feels_like_c"), 1)
    humidity_pct = format_site_summary_value(weather.get("humidity_pct"), 0)
    pressure_hpa = format_site_summary_value(weather.get("pressure_hpa"), 0)
    wind_speed_mps = format_site_summary_value(weather.get("wind_speed_mps"), 1)
    cloudiness_pct = format_site_summary_value(weather.get("cloudiness_pct"), 0)
    visibility_km = format_site_summary_value(
        (float(weather["visibility_m"]) / 1000)
        if weather.get("visibility_m") is not None else None,
        1
    )

    temperature_value = weather.get("temperature_c")
    temperature_status = "current temperature"
    try:
        if temperature_value is not None:
            numeric_temperature = float(temperature_value)
            if numeric_temperature >= 35:
                temperature_status = "very hot"
            elif numeric_temperature >= 30:
                temperature_status = "hot"
            elif numeric_temperature >= 24:
                temperature_status = "warm"
            elif numeric_temperature >= 15:
                temperature_status = "mild"
            else:
                temperature_status = "cool"
    except (TypeError, ValueError):
        numeric_temperature = None

    weather_status = description_label.lower()
    if weather_main.lower() in {"rain", "drizzle", "thunderstorm"}:
        weather_status = f"{weather_status}; rainfall is likely right now"
    elif weather_main.lower() in {"clear"}:
        weather_status = f"{weather_status}; no rain signal right now"
    elif weather_main.lower() in {"clouds"}:
        weather_status = f"{weather_status}; cloudy conditions right now"

    tone = "warning" if numeric_temperature is not None and numeric_temperature >= 35 else "info"
    if weather_main.lower() in {"thunderstorm", "tornado"}:
        tone = "danger"
    elif weather_main.lower() in {"rain", "drizzle", "snow"}:
        tone = "warning"

    headline_fragments = []
    if temperature_c is not None:
        headline_fragments.append(f"{temperature_c} C")
    if feels_like_c is not None:
        headline_fragments.append(f"feels like {feels_like_c} C")
    headline_text = ", ".join(headline_fragments) if headline_fragments else description_label

    climate_updates = [
        build_site_update_item(
            kind="live-weather-current",
            category="Live Weather",
            title=f"Current weather for {location_label}",
            date_label=observed_label,
            body=(
                f"Current conditions at the viewer location show {weather_status}. "
                f"Current temperature is {temperature_c or 'N/A'} C"
                + (f" and it feels like {feels_like_c} C." if feels_like_c is not None else ".")
            ),
            tone=tone,
            ticker_message=(
                f"Today near {location_label}: {temperature_status}, {weather_status}, {headline_text}"
            )
        )
    ]

    atmosphere_parts = []
    if humidity_pct is not None:
        atmosphere_parts.append(f"humidity {humidity_pct}%")
    if wind_speed_mps is not None:
        atmosphere_parts.append(f"wind {wind_speed_mps} m/s")
    if cloudiness_pct is not None:
        atmosphere_parts.append(f"cloud cover {cloudiness_pct}%")
    if pressure_hpa is not None:
        atmosphere_parts.append(f"pressure {pressure_hpa} hPa")
    if visibility_km is not None:
        atmosphere_parts.append(f"visibility {visibility_km} km")

    if atmosphere_parts:
        climate_updates.append(
            build_site_update_item(
                kind="live-weather-atmosphere",
                category="Live Weather",
                title=f"Humidity and wind near {location_label}",
                date_label=observed_label,
                body=(
                    "Current weather details show "
                    + ", ".join(atmosphere_parts)
                    + "."
                ),
                tone="info",
                ticker_message=(
                    f"Current conditions near {location_label}: " + ", ".join(atmosphere_parts)
                )
            )
        )

    return {
        "source": weather.get("source") or "Live weather",
        "location_name": location_label,
        "coordinates": weather.get("coordinates") or {},
        "observed_at_unix": weather.get("observed_at_unix"),
        "observed_at_label": observed_label,
        "weather_main": weather_main or None,
        "weather_description": weather_description or None,
        "temperature_c": weather.get("temperature_c"),
        "feels_like_c": weather.get("feels_like_c"),
        "humidity_pct": weather.get("humidity_pct"),
        "pressure_hpa": weather.get("pressure_hpa"),
        "wind_speed_mps": weather.get("wind_speed_mps"),
        "cloudiness_pct": weather.get("cloudiness_pct"),
        "visibility_m": weather.get("visibility_m"),
        "climate_updates": climate_updates,
        "ticker_items": [
            update["ticker_message"]
            for update in climate_updates
            if update.get("ticker_message")
        ]
    }


def merge_live_weather_into_site_summary(summary_payload, live_weather_payload):
    merged_payload = dict(summary_payload or {})
    merged_payload["climate_updates"] = list(
        live_weather_payload.get("climate_updates") or []
    ) + list(merged_payload.get("climate_updates") or [])
    merged_payload["ticker_items"] = list(
        live_weather_payload.get("ticker_items") or []
    ) + list(merged_payload.get("ticker_items") or [])
    merged_payload["live_weather"] = live_weather_payload
    return merged_payload


def build_site_signal_updates(latest_year, latest_year_summary):
    if latest_year is None or not latest_year_summary:
        return []

    signal_configs = [
        {
            "key": "drought",
            "category": "Drought Watch",
            "decimals": 2,
            "tone": lambda value: "danger" if value >= 2 else "warning" if value >= 1 else "info",
            "priority": lambda value: 400 if value >= 2 else 320 if value >= 1 else 250,
            "title": lambda province, year, value: f"{province} shows the highest drought pressure in {year}",
            "body": lambda province, year, value: (
                f"{province} recorded the highest province-level drought score in {year} at {value}, "
                "making it the strongest drought signal in the latest available year."
            ),
            "ticker": lambda province, year, value: (
                f"{year} drought watch: {province} recorded the highest province-level drought score at {value}"
            )
        },
        {
            "key": "temperature",
            "category": "Heat Signal",
            "decimals": 1,
            "tone": lambda value: "warning" if value >= 35 else "info",
            "priority": lambda value: 300 if value >= 35 else 220,
            "title": lambda province, year, value: f"{province} leads maximum temperature in {year}",
            "body": lambda province, year, value: (
                f"{province} recorded the highest average maximum temperature in {year} at {value} C, "
                "marking it as the warmest province-level signal in the current dataset."
            ),
            "ticker": lambda province, year, value: (
                f"{year} heat signal: {province} recorded the highest average maximum temperature at {value} C"
            )
        },
        {
            "key": "rainfall",
            "category": "Rainfall Signal",
            "decimals": 1,
            "tone": lambda value: "info",
            "priority": lambda value: 280 if value >= 150 else 200,
            "title": lambda province, year, value: f"{province} leads rainfall averages in {year}",
            "body": lambda province, year, value: (
                f"{province} recorded the highest average rainfall in {year} at {value} mm, "
                "making it the wettest province-level signal in the current dataset."
            ),
            "ticker": lambda province, year, value: (
                f"{year} rainfall signal: {province} recorded the highest average rainfall at {value} mm"
            )
        },
        {
            "key": "ndvi",
            "category": "Vegetation Health",
            "decimals": 3,
            "tone": lambda value: "success" if value >= 0.55 else "info",
            "priority": lambda value: 180 if value >= 0.55 else 120,
            "title": lambda province, year, value: f"{province} shows the strongest vegetation signal in {year}",
            "body": lambda province, year, value: (
                f"{province} recorded the highest NDVI in {year} at {value}, "
                "pointing to the strongest vegetation health signal in the latest available year."
            ),
            "ticker": lambda province, year, value: (
                f"{year} vegetation signal: {province} recorded the highest NDVI at {value}"
            )
        }
    ]

    signal_updates = []

    for config in signal_configs:
        metric_rows = latest_year_summary.get(config["key"]) or []
        metric_row = metric_rows[0] if metric_rows else None
        province = str(metric_row.get("province") if metric_row else "").strip()
        if not province:
            continue

        raw_value = metric_row.get("value")
        formatted_value = format_site_summary_value(raw_value, config["decimals"])
        if formatted_value is None:
            continue

        numeric_value = float(raw_value)
        signal_updates.append({
            "sort_priority": config["priority"](numeric_value),
            "item": build_site_update_item(
                kind=config["key"],
                category=config["category"],
                title=config["title"](province, latest_year, formatted_value),
                date_label=f"Latest year climate signal: {latest_year}",
                body=config["body"](province, latest_year, formatted_value),
                tone=config["tone"](numeric_value),
                ticker_message=config["ticker"](province, latest_year, formatted_value)
            )
        })

    signal_updates.sort(key=lambda update: update["sort_priority"], reverse=True)
    return [update["item"] for update in signal_updates]


def get_site_update_top_label(frame, field):
    if frame is None or frame.empty or field not in frame.columns:
        return None, 0

    values = frame[field].dropna().astype(str).str.strip()
    values = values[values != ""]
    if values.empty:
        return None, 0

    counts = values.value_counts()
    return counts.index[0], int(counts.iloc[0])


def get_site_update_peak_month_label(frame):
    if frame is None or frame.empty or 'month' not in frame.columns:
        return None

    months = pd.to_numeric(frame['month'], errors='coerce').dropna()
    if months.empty:
        return None

    month_counts = months.astype(int).value_counts()
    peak_month = int(month_counts.index[0])
    return month_label_from_number(peak_month)


def get_site_update_top_population_location(frame):
    if frame is None or frame.empty or 'district' not in frame.columns or 'PopulationAffected' not in frame.columns:
        return None

    work = frame.copy()
    work['district'] = work['district'].fillna('').astype(str).str.strip()
    work = work[work['district'] != '']
    if work.empty:
        return None

    grouped = summarize_population_affected(work, ['district'])
    if grouped.empty:
        return None

    grouped = grouped.sort_values(['PopulationAffected', 'district'], ascending=[False, True]).reset_index(drop=True)
    lead_row = grouped.iloc[0]
    district = str(lead_row['district']).strip()
    population_affected = int(lead_row['PopulationAffected'] or 0)
    province = None

    if 'province' in work.columns:
        province_values = work.loc[work['district'] == district, 'province'].dropna().astype(str).str.strip()
        province_values = province_values[province_values != '']
        if not province_values.empty:
            province = province_values.mode().iloc[0]

    return {
        "district": district,
        "province": province,
        "population_affected": population_affected
    }


def build_site_event_updates(latest_year, latest_year_df):
    if latest_year is None or latest_year_df is None or latest_year_df.empty:
        return []

    work = latest_year_df.copy()
    for column in ['Rainfall_mm', 'Temp_Max_C', 'PopulationAffected', 'month']:
        if column in work.columns:
            work[column] = pd.to_numeric(work[column], errors='coerce')

    event_updates = []

    rainfall_threshold = None
    rainfall_values = work['Rainfall_mm'].dropna() if 'Rainfall_mm' in work.columns else pd.Series(dtype=float)
    if not rainfall_values.empty:
        rainfall_threshold = float(rainfall_values.quantile(0.90))

    temperature_threshold = None
    temperature_values = work['Temp_Max_C'].dropna() if 'Temp_Max_C' in work.columns else pd.Series(dtype=float)
    if not temperature_values.empty:
        temperature_threshold = float(temperature_values.quantile(0.90))

    if rainfall_threshold is not None:
        flood_df = work[work['Rainfall_mm'] >= rainfall_threshold]
        flood_event_count = int(len(flood_df))
        if flood_event_count > 0:
            lead_province, lead_count = get_site_update_top_label(flood_df, 'province')
            peak_month = get_site_update_peak_month_label(flood_df)
            extreme_rainfall_count = int((work['Rainfall_mm'] >= 150).sum()) if 'Rainfall_mm' in work.columns else 0
            max_rainfall = format_site_summary_value(work['Rainfall_mm'].max(), 1)
            rainfall_threshold_value = format_site_summary_value(rainfall_threshold, 1)

            body_parts = [
                f"The {latest_year} dataset flags {flood_event_count:,} flood-risk rainfall records at or above {rainfall_threshold_value} mm."
            ]
            if lead_province:
                body_parts.append(f"{lead_province} leads with {lead_count:,} flagged records.")
            if peak_month:
                body_parts.append(f"Flood-risk rainfall peaks in {peak_month}.")
            if extreme_rainfall_count > 0:
                body_parts.append(
                    f"{extreme_rainfall_count:,} records also reached the extreme rainfall mark of 150 mm or higher."
                )
            if max_rainfall is not None:
                body_parts.append(f"The maximum recorded rainfall reached {max_rainfall} mm.")

            event_updates.append({
                "sort_priority": 370 if extreme_rainfall_count > 0 else 300,
                "item": build_site_update_item(
                    kind="flood-risk-events",
                    category="Flood Watch",
                    title=(
                        f"{lead_province} leads flood-risk rainfall in {latest_year}"
                        if lead_province else f"Flood-risk rainfall detected in {latest_year}"
                    ),
                    date_label=f"Latest year event summary: {latest_year}",
                    body=" ".join(body_parts),
                    tone="danger" if extreme_rainfall_count > 0 else "warning",
                    ticker_message=(
                        f"{latest_year} flood watch: {flood_event_count:,} rainfall records reached the flood-risk threshold"
                    )
                )
            })

    if temperature_threshold is not None:
        heat_df = work[work['Temp_Max_C'] >= temperature_threshold]
        heat_event_count = int(len(heat_df))
        if heat_event_count > 0:
            lead_province, lead_count = get_site_update_top_label(heat_df, 'province')
            peak_month = get_site_update_peak_month_label(heat_df)
            max_temperature = format_site_summary_value(work['Temp_Max_C'].max(), 1)
            temperature_threshold_value = format_site_summary_value(temperature_threshold, 1)

            body_parts = [
                f"The {latest_year} dataset flags {heat_event_count:,} heat-event records at or above {temperature_threshold_value} C."
            ]
            if lead_province:
                body_parts.append(f"{lead_province} has the highest concentration with {lead_count:,} records.")
            if peak_month:
                body_parts.append(f"Heat-event activity peaks in {peak_month}.")
            if max_temperature is not None:
                body_parts.append(f"The highest recorded maximum temperature reached {max_temperature} C.")

            max_temperature_numeric = float(max_temperature) if max_temperature is not None else 0
            event_updates.append({
                "sort_priority": 360 if max_temperature_numeric >= 40 else 290,
                "item": build_site_update_item(
                    kind="heat-events",
                    category="Heat Events",
                    title=(
                        f"{lead_province} leads heat-event activity in {latest_year}"
                        if lead_province else f"Heat-event activity detected in {latest_year}"
                    ),
                    date_label=f"Latest year event summary: {latest_year}",
                    body=" ".join(body_parts),
                    tone="danger" if max_temperature_numeric >= 40 else "warning",
                    ticker_message=(
                        f"{latest_year} heat events: {heat_event_count:,} records reached the heat-event threshold"
                    )
                )
            })

    if 'DroughtSeverity' in work.columns:
        drought_labels = work['DroughtSeverity'].fillna('').astype(str).str.strip().str.lower()
        severe_drought_df = work[drought_labels == 'severe']
        severe_drought_count = int(len(severe_drought_df))
        if severe_drought_count > 0:
            lead_province, lead_count = get_site_update_top_label(severe_drought_df, 'province')
            peak_month = get_site_update_peak_month_label(severe_drought_df)

            body_parts = [
                f"The {latest_year} dataset contains {severe_drought_count:,} severe-drought records."
            ]
            if lead_province:
                body_parts.append(f"{lead_province} carries the largest concentration with {lead_count:,} records.")
            if peak_month:
                body_parts.append(f"Severe-drought activity peaks in {peak_month}.")

            event_updates.append({
                "sort_priority": 380,
                "item": build_site_update_item(
                    kind="severe-drought-events",
                    category="Severe Drought",
                    title=(
                        f"{lead_province} leads severe-drought records in {latest_year}"
                        if lead_province else f"Severe drought records detected in {latest_year}"
                    ),
                    date_label=f"Latest year event summary: {latest_year}",
                    body=" ".join(body_parts),
                    tone="danger",
                    ticker_message=(
                        f"{latest_year} severe drought: {severe_drought_count:,} records were flagged as severe"
                    )
                )
            })

    total_population_affected = summarize_population_affected(work)
    if total_population_affected > 0:
        lead_location = get_site_update_top_population_location(work)
        population_by_month = summarize_population_affected(work, ['month']) if 'month' in work.columns else pd.DataFrame()
        peak_population_month = None
        if not population_by_month.empty:
            population_by_month = population_by_month.dropna(subset=['month', 'PopulationAffected'])
            if not population_by_month.empty:
                peak_row = population_by_month.sort_values(['PopulationAffected', 'month'], ascending=[False, True]).iloc[0]
                peak_population_month = month_label_from_number(peak_row['month'])

        body_parts = [
            f"The {latest_year} dataset records {int(total_population_affected):,} people affected across districts."
        ]
        if lead_location:
            location_label = (
                f"{lead_location['district']} ({lead_location['province']})"
                if lead_location.get('province') else lead_location['district']
            )
            body_parts.append(
                f"{location_label} reports the largest district total at {lead_location['population_affected']:,} people."
            )
        if peak_population_month:
            body_parts.append(f"Population impact is highest in {peak_population_month}.")

        event_updates.append({
            "sort_priority": 340 if total_population_affected >= 10000 else 270,
            "item": build_site_update_item(
                kind="impact-events",
                category="Impact Watch",
                title=f"Population impact is visible across the {latest_year} dataset",
                date_label=f"Latest year event summary: {latest_year}",
                body=" ".join(body_parts),
                tone="warning" if total_population_affected >= 1000 else "info",
                ticker_message=(
                    f"{latest_year} impact watch: {int(total_population_affected):,} people affected are recorded in the dataset"
                )
            )
        })

    event_updates.sort(key=lambda update: update["sort_priority"], reverse=True)
    return [update["item"] for update in event_updates]


def get_district_climate_summaries_for_year(year):
    if year is None:
        return []

    query = (
        "SELECT district, province, "
        "ROUND(AVG(rainfall_mm)::numeric, 1) AS avg_rainfall, "
        "ROUND(AVG(temp_max_c)::numeric, 1) AS avg_temp_max, "
        "ROUND(AVG(ndvi)::numeric, 3) AS avg_ndvi, "
        "ROUND(AVG(CASE drought_severity "
        "WHEN 'No Drought' THEN 0 "
        "WHEN 'Mild' THEN 1 "
        "WHEN 'Moderate' THEN 2 "
        "WHEN 'Severe' THEN 3 "
        "ELSE 0 END)::numeric, 2) AS avg_drought_score "
        "FROM climate_records "
        "WHERE year = %s AND district IS NOT NULL AND TRIM(district) <> '' "
        "GROUP BY district, province "
        "ORDER BY district"
    )

    rows = db_manager.execute_query(query, [year]) or []
    district_summaries = []

    for row in rows:
        district = str(row.get("district") or "").strip()
        if not district:
            continue

        province = str(row.get("province") or "").strip() or None
        district_summaries.append({
            "district": district,
            "province": province,
            "avg_rainfall": float(row["avg_rainfall"]) if row.get("avg_rainfall") is not None else None,
            "avg_temp_max": float(row["avg_temp_max"]) if row.get("avg_temp_max") is not None else None,
            "avg_ndvi": float(row["avg_ndvi"]) if row.get("avg_ndvi") is not None else None,
            "avg_drought_score": float(row["avg_drought_score"]) if row.get("avg_drought_score") is not None else None
        })

    return district_summaries


def normalize_site_summary_date(value):
    if value is None:
        return None

    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date()


def format_site_summary_date(value):
    normalized = normalize_site_summary_date(value)
    return normalized.isoformat() if normalized is not None else None


def get_latest_daily_district_records():
    query = (
        "SELECT DISTINCT ON (district) "
        "district, "
        "NULLIF(TRIM(province), '') AS province, "
        "date, "
        "rainfall_mm, "
        "temp_max_c, "
        "ndvi, "
        "drought_severity, "
        "population_affected "
        "FROM climate_records "
        "WHERE district IS NOT NULL "
        "AND TRIM(district) <> '' "
        "AND date IS NOT NULL "
        "ORDER BY district, date DESC, year DESC NULLS LAST, month DESC NULLS LAST"
    )

    rows = db_manager.execute_query(query) or []
    daily_records = []

    for row in rows:
        district = str(row.get("district") or "").strip()
        if not district:
            continue

        daily_records.append({
            "district": district,
            "province": str(row.get("province") or "").strip() or None,
            "date": row.get("date"),
            "rainfall_mm": float(row["rainfall_mm"]) if row.get("rainfall_mm") is not None else None,
            "temp_max_c": float(row["temp_max_c"]) if row.get("temp_max_c") is not None else None,
            "ndvi": float(row["ndvi"]) if row.get("ndvi") is not None else None,
            "drought_severity": str(row.get("drought_severity") or "").strip() or None,
            "population_affected": int(row["population_affected"]) if row.get("population_affected") is not None else None
        })

    return daily_records


def get_latest_monthly_district_records():
    query = (
        "WITH monthly_district_records AS ("
        "    SELECT district, "
        "           NULLIF(TRIM(province), '') AS province, "
        "           year, "
        "           month, "
        "           ROUND(AVG(rainfall_mm)::numeric, 1) AS avg_rainfall, "
        "           ROUND(AVG(temp_max_c)::numeric, 1) AS avg_temp_max, "
        "           ROUND(AVG(ndvi)::numeric, 3) AS avg_ndvi, "
        "           ROUND(AVG(CASE drought_severity "
        "               WHEN 'No Drought' THEN 0 "
        "               WHEN 'Mild' THEN 1 "
        "               WHEN 'Moderate' THEN 2 "
        "               WHEN 'Severe' THEN 3 "
        "               ELSE 0 END)::numeric, 2) AS avg_drought_score, "
        "           MAX(population_affected) AS population_affected "
        "    FROM climate_records "
        "    WHERE district IS NOT NULL "
        "      AND TRIM(district) <> '' "
        "      AND year IS NOT NULL "
        "      AND month IS NOT NULL "
        "    GROUP BY district, province, year, month"
        "), latest_monthly_records AS ("
        "    SELECT DISTINCT ON (district) "
        "           district, province, year, month, avg_rainfall, avg_temp_max, avg_ndvi, avg_drought_score, population_affected "
        "    FROM monthly_district_records "
        "    ORDER BY district, year DESC NULLS LAST, month DESC NULLS LAST"
        ") "
        "SELECT district, province, year, month, avg_rainfall, avg_temp_max, avg_ndvi, avg_drought_score, population_affected "
        "FROM latest_monthly_records "
        "ORDER BY district"
    )

    rows = db_manager.execute_query(query) or []
    monthly_records = []

    for row in rows:
        district = str(row.get("district") or "").strip()
        if not district:
            continue

        monthly_records.append({
            "district": district,
            "province": str(row.get("province") or "").strip() or None,
            "year": int(row["year"]) if row.get("year") is not None else None,
            "month": int(row["month"]) if row.get("month") is not None else None,
            "avg_rainfall": float(row["avg_rainfall"]) if row.get("avg_rainfall") is not None else None,
            "avg_temp_max": float(row["avg_temp_max"]) if row.get("avg_temp_max") is not None else None,
            "avg_ndvi": float(row["avg_ndvi"]) if row.get("avg_ndvi") is not None else None,
            "avg_drought_score": float(row["avg_drought_score"]) if row.get("avg_drought_score") is not None else None,
            "population_affected": int(row["population_affected"]) if row.get("population_affected") is not None else None
        })

    return monthly_records


def get_district_site_update_tone(avg_drought_score=None, avg_temp=None, avg_ndvi=None, drought_severity=None, population_affected=0):
    try:
        drought_score = None
        if avg_drought_score is not None:
            drought_score = float(avg_drought_score)
        elif drought_severity is not None:
            drought_score = float(DROUGHT_SCORE_MAP.get(str(drought_severity).strip(), 0))

        if drought_score is not None and drought_score >= 2:
            return "danger"
        if int(population_affected or 0) >= 1000:
            return "danger"
        if drought_score is not None and drought_score >= 1:
            return "warning"
        if int(population_affected or 0) > 0:
            return "warning"
        if avg_temp is not None and float(avg_temp) >= 35:
            return "warning"
        if avg_ndvi is not None and float(avg_ndvi) >= 0.55:
            return "success"
    except (TypeError, ValueError):
        return "info"
    return "info"


def build_latest_daily_district_update_items(daily_records):
    district_updates = []

    for record in (daily_records or []):
        district = str(record.get("district") or "").strip()
        observed_date_label = format_site_summary_date(record.get("date"))
        if not district or not observed_date_label:
            continue

        province = str(record.get("province") or "").strip()
        location_label = f"{district} ({province})" if province else district
        rainfall_value = format_site_summary_value(record.get("rainfall_mm"), 1)
        temp_value = format_site_summary_value(record.get("temp_max_c"), 1)
        ndvi_value = format_site_summary_value(record.get("ndvi"), 3)
        drought_severity = str(record.get("drought_severity") or "").strip()
        population_affected = int(record.get("population_affected") or 0)

        metric_parts = []
        ticker_parts = []

        if rainfall_value is not None:
            metric_parts.append(f"rainfall of {rainfall_value} mm")
            ticker_parts.append(f"rain {rainfall_value} mm")
        if temp_value is not None:
            metric_parts.append(f"max temperature of {temp_value} C")
            ticker_parts.append(f"temp {temp_value} C")
        if drought_severity:
            metric_parts.append(f"drought severity of {drought_severity}")
            ticker_parts.append(f"drought {drought_severity}")
        if ndvi_value is not None:
            metric_parts.append(f"NDVI of {ndvi_value}")
            ticker_parts.append(f"NDVI {ndvi_value}")
        if population_affected > 0:
            metric_parts.append(f"population affected of {population_affected:,}")
            ticker_parts.append(f"impact {population_affected:,}")

        if not metric_parts:
            continue

        district_updates.append(
            build_site_update_item(
                kind="district-daily-update",
                category="District Daily Update",
                title=f"{district} latest daily climate record",
                date_label=f"Latest daily record: {observed_date_label}",
                body=f"On {observed_date_label}, {location_label} recorded " + ", ".join(metric_parts) + ".",
                tone=get_district_site_update_tone(
                    avg_temp=record.get("temp_max_c"),
                    avg_ndvi=record.get("ndvi"),
                    drought_severity=drought_severity,
                    population_affected=population_affected
                ),
                ticker_message=f"Daily district record {observed_date_label}: {location_label}, " + ", ".join(ticker_parts)
            )
        )

    return district_updates


def _district_location_label(record):
    district = str(record.get("district") or "").strip()
    province = str(record.get("province") or "").strip()
    return f"{district} ({province})" if district and province else district


def build_latest_daily_condition_ticker_items(daily_records):
    records = []
    for record in (daily_records or []):
        observed_date = normalize_site_summary_date(record.get("date"))
        if observed_date is None:
            continue
        records.append({**record, "_observed_date": observed_date})

    if not records:
        return []

    latest_date = max(record["_observed_date"] for record in records)
    latest_records_for_same_day = [
        record for record in records
        if record["_observed_date"] == latest_date
    ]
    comparison_records = latest_records_for_same_day if len(latest_records_for_same_day) >= 3 else records
    comparison_scope_label = (
        latest_date.isoformat()
        if len(latest_records_for_same_day) >= 3
        else "latest available district records"
    )
    ticker_items = []

    temperature_records = [
        record for record in comparison_records
        if record.get("temp_max_c") is not None
    ]
    if temperature_records:
        hottest = max(temperature_records, key=lambda record: float(record.get("temp_max_c")))
        coolest = min(temperature_records, key=lambda record: float(record.get("temp_max_c")))
        hottest_temp = format_site_summary_value(hottest.get("temp_max_c"), 1)
        coolest_temp = format_site_summary_value(coolest.get("temp_max_c"), 1)
        hottest_label = _district_location_label(hottest)
        coolest_label = _district_location_label(coolest)
        hot_word = "very hot" if float(hottest.get("temp_max_c")) >= 35 else "hot" if float(hottest.get("temp_max_c")) >= 30 else "warmest"
        cool_word = "cool" if float(coolest.get("temp_max_c")) < 24 else "least hot"
        ticker_items.append(
            f"Latest daily indication ({comparison_scope_label}): {hottest_label} is {hot_word} at {hottest_temp} C on {hottest['_observed_date'].isoformat()}"
        )
        ticker_items.append(
            f"Latest daily indication ({comparison_scope_label}): {coolest_label} is {cool_word} at {coolest_temp} C on {coolest['_observed_date'].isoformat()}"
        )

    rainfall_records = [
        record for record in comparison_records
        if record.get("rainfall_mm") is not None
    ]
    if rainfall_records:
        wettest = max(rainfall_records, key=lambda record: float(record.get("rainfall_mm")))
        wettest_rain = format_site_summary_value(wettest.get("rainfall_mm"), 1)
        wettest_label = _district_location_label(wettest)
        rain_word = "heavy rainfall" if float(wettest.get("rainfall_mm")) >= 50 else "rainfall" if float(wettest.get("rainfall_mm")) > 0 else "no recorded rain"
        ticker_items.append(
            f"Latest daily indication ({comparison_scope_label}): {wettest_label} has {rain_word} at {wettest_rain} mm on {wettest['_observed_date'].isoformat()}"
        )

    drought_records = [
        record for record in comparison_records
        if str(record.get("drought_severity") or "").strip()
    ]
    if drought_records:
        drought_record = max(
            drought_records,
            key=lambda record: DROUGHT_SCORE_MAP.get(str(record.get("drought_severity") or "").strip(), 0)
        )
        drought_label = _district_location_label(drought_record)
        drought_severity = str(drought_record.get("drought_severity") or "").strip()
        if drought_severity and drought_severity.lower() not in {"no drought", "none", "normal"}:
            ticker_items.append(
                f"Latest daily indication ({comparison_scope_label}): {drought_label} shows {drought_severity.lower()} drought conditions on {drought_record['_observed_date'].isoformat()}"
            )

    return ticker_items


def build_latest_monthly_district_update_items(monthly_records):
    district_updates = []

    for record in (monthly_records or []):
        district = str(record.get("district") or "").strip()
        year = record.get("year")
        month = record.get("month")
        month_label = month_label_from_number(month) if month is not None else None
        if not district or year is None or month is None or not month_label:
            continue

        province = str(record.get("province") or "").strip()
        location_label = f"{district} ({province})" if province else district
        date_label = f"{month_label} {year}"
        rainfall_value = format_site_summary_value(record.get("avg_rainfall"), 1)
        temp_value = format_site_summary_value(record.get("avg_temp_max"), 1)
        drought_value = format_site_summary_value(record.get("avg_drought_score"), 2)
        ndvi_value = format_site_summary_value(record.get("avg_ndvi"), 3)
        population_affected = int(record.get("population_affected") or 0)

        metric_parts = []
        ticker_parts = []

        if rainfall_value is not None:
            metric_parts.append(f"rainfall averaged {rainfall_value} mm")
            ticker_parts.append(f"rain {rainfall_value} mm")
        if temp_value is not None:
            metric_parts.append(f"max temperature averaged {temp_value} C")
            ticker_parts.append(f"temp {temp_value} C")
        if drought_value is not None:
            metric_parts.append(f"drought score averaged {drought_value}")
            ticker_parts.append(f"drought {drought_value}")
        if ndvi_value is not None:
            metric_parts.append(f"NDVI averaged {ndvi_value}")
            ticker_parts.append(f"NDVI {ndvi_value}")
        if population_affected > 0:
            metric_parts.append(f"population affected of {population_affected:,}")
            ticker_parts.append(f"impact {population_affected:,}")

        if not metric_parts:
            continue

        district_updates.append(
            build_site_update_item(
                kind="district-monthly-update",
                category="District Monthly Update",
                title=f"{district} latest monthly climate record",
                date_label=f"Latest monthly record: {date_label}",
                body=f"For {date_label}, {location_label} recorded " + ", ".join(metric_parts) + ".",
                tone=get_district_site_update_tone(
                    avg_drought_score=record.get("avg_drought_score"),
                    avg_temp=record.get("avg_temp_max"),
                    avg_ndvi=record.get("avg_ndvi"),
                    population_affected=population_affected
                ),
                ticker_message=f"Monthly district record {date_label}: {location_label}, " + ", ".join(ticker_parts)
            )
        )

    return district_updates


def build_district_site_update_items(latest_year, district_summaries):
    if latest_year is None:
        return []

    district_updates = []
    for summary in (district_summaries or []):
        district = str(summary.get("district") or "").strip()
        if not district:
            continue

        province = str(summary.get("province") or "").strip()
        rainfall_value = format_site_summary_value(summary.get("avg_rainfall"), 1)
        temp_value = format_site_summary_value(summary.get("avg_temp_max"), 1)
        drought_value = format_site_summary_value(summary.get("avg_drought_score"), 2)
        ndvi_value = format_site_summary_value(summary.get("avg_ndvi"), 3)

        metric_parts = []
        ticker_parts = []

        if rainfall_value is not None:
            metric_parts.append(f"rainfall averaged {rainfall_value} mm")
            ticker_parts.append(f"rain {rainfall_value} mm")
        if temp_value is not None:
            metric_parts.append(f"max temperature averaged {temp_value} C")
            ticker_parts.append(f"temp {temp_value} C")
        if drought_value is not None:
            metric_parts.append(f"drought score averaged {drought_value}")
            ticker_parts.append(f"drought {drought_value}")
        if ndvi_value is not None:
            metric_parts.append(f"NDVI averaged {ndvi_value}")
            ticker_parts.append(f"NDVI {ndvi_value}")

        if not metric_parts:
            continue

        location_label = f"{district} ({province})" if province else district
        body_text = "; ".join(metric_parts)
        body = f"In {latest_year}, {location_label} recorded {body_text}."
        ticker_message = f"{latest_year} {location_label}: {', '.join(ticker_parts)}"

        district_updates.append({
            **build_site_update_item(
                kind="district-update",
                category="District Update",
                title=f"{district} district update for {latest_year}",
                date_label=province or f"District dataset update: {latest_year}",
                body=body,
                tone=get_district_site_update_tone(
                    avg_drought_score=summary.get("avg_drought_score"),
                    avg_temp=summary.get("avg_temp_max"),
                    avg_ndvi=summary.get("avg_ndvi")
                ),
                ticker_message=ticker_message
            ),
            "district": district,
            "province": province or None,
            "metrics": {
                "avg_rainfall": summary.get("avg_rainfall"),
                "avg_temp_max": summary.get("avg_temp_max"),
                "avg_drought_score": summary.get("avg_drought_score"),
                "avg_ndvi": summary.get("avg_ndvi")
            }
        })

    return district_updates


def build_site_summary_updates(
    total_records,
    provinces,
    district_count,
    years,
    yearly_summaries,
    district_summaries=None,
    latest_year_df=None,
    latest_daily_district_records=None,
    latest_monthly_district_records=None
):
    normalized_years = []
    for year in (years or []):
        try:
            normalized_years.append(int(year))
        except (TypeError, ValueError):
            continue
    normalized_years = sorted(set(normalized_years))
    earliest_year = normalized_years[0] if normalized_years else None
    latest_year = normalized_years[-1] if normalized_years else None
    province_count = len(provinces or [])

    if earliest_year is not None and latest_year is not None:
        coverage_update = build_site_update_item(
            kind="coverage",
            category="Data Coverage",
            title=f"Dataset Coverage Confirmed Through {latest_year}",
            date_label=f"Coverage years: {earliest_year}-{latest_year}",
            body=(
                f"The portal is currently using {int(total_records or 0):,} records across "
                f"{int(district_count or 0):,} districts in {province_count:,} provinces from "
                f"{earliest_year} to {latest_year}."
            ),
            tone="success",
            ticker_message=(
                f"Coverage update: {int(total_records or 0):,} records across "
                f"{int(district_count or 0):,} districts from {earliest_year} to {latest_year}"
            )
        )
    else:
        coverage_update = build_site_update_item(
            kind="coverage",
            category="Data Coverage",
            title="Dataset Coverage Available",
            date_label="Coverage years unavailable",
            body="The portal could not confirm the current dataset coverage automatically.",
            tone="info",
            ticker_message="Dataset coverage could not be confirmed automatically."
        )

    latest_year_summary = None
    if latest_year is not None:
        for summary in (yearly_summaries or []):
            try:
                if int(summary.get("year")) == latest_year:
                    latest_year_summary = summary
                    break
            except (TypeError, ValueError):
                continue

    signal_updates = build_site_signal_updates(latest_year, latest_year_summary)
    event_updates = build_site_event_updates(latest_year, latest_year_df)
    district_updates = build_district_site_update_items(latest_year, district_summaries)
    daily_district_updates = build_latest_daily_district_update_items(latest_daily_district_records)
    daily_condition_ticker_items = build_latest_daily_condition_ticker_items(latest_daily_district_records)
    monthly_district_updates = build_latest_monthly_district_update_items(latest_monthly_district_records)
    district_feed_update = None
    if latest_year is not None and district_updates:
        sample_districts = ", ".join(update["district"] for update in district_updates[:3])
        district_feed_update = build_site_update_item(
            kind="district-feed",
            category="District Feed",
            title=f"Live district updates generated for {len(district_updates):,} districts",
            date_label=f"Latest year district coverage: {latest_year}",
            body=(
                f"The latest {latest_year} climate update feed now uses real district-level data for "
                f"{len(district_updates):,} districts. The ticker cycles through every district update, "
                f"including {sample_districts} and the rest of the current dataset."
            ),
            tone="success",
            ticker_message=(
                f"District feed ready: {len(district_updates):,} district updates generated from {latest_year}"
            )
        )
    elif latest_year is not None:
        district_feed_update = build_site_update_item(
            kind="district-feed",
            category="District Feed",
            title="District updates unavailable",
            date_label=f"Latest year district coverage: {latest_year}",
            body="The portal could not generate district-level updates from the latest available year.",
            tone="info",
            ticker_message=f"District feed could not be generated for {latest_year}"
        )

    daily_district_feed_update = None
    if latest_year is not None and daily_district_updates:
        daily_district_feed_update = build_site_update_item(
            kind="district-daily-feed",
            category="District Daily Feed",
            title=f"Latest daily district feed covers {len(daily_district_updates):,} districts",
            date_label=f"Latest daily district coverage through {latest_year}",
            body=(
                f"The live district feed now includes the most recent daily climate records for "
                f"{len(daily_district_updates):,} districts."
            ),
            tone="success",
            ticker_message=f"Daily district feed ready: {len(daily_district_updates):,} latest daily district updates"
        )
    elif latest_year is not None:
        daily_district_feed_update = build_site_update_item(
            kind="district-daily-feed",
            category="District Daily Feed",
            title="Daily district updates unavailable",
            date_label=f"Latest daily district coverage through {latest_year}",
            body="The portal could not generate daily district updates from the latest available records.",
            tone="info",
            ticker_message=f"Daily district feed could not be generated through {latest_year}"
        )

    monthly_district_feed_update = None
    if latest_year is not None and monthly_district_updates:
        monthly_district_feed_update = build_site_update_item(
            kind="district-monthly-feed",
            category="District Monthly Feed",
            title=f"Latest monthly district feed covers {len(monthly_district_updates):,} districts",
            date_label=f"Latest monthly district coverage through {latest_year}",
            body=(
                f"The live district feed now includes the latest monthly climate summaries for "
                f"{len(monthly_district_updates):,} districts."
            ),
            tone="success",
            ticker_message=f"Monthly district feed ready: {len(monthly_district_updates):,} latest monthly district updates"
        )
    elif latest_year is not None:
        monthly_district_feed_update = build_site_update_item(
            kind="district-monthly-feed",
            category="District Monthly Feed",
            title="Monthly district updates unavailable",
            date_label=f"Latest monthly district coverage through {latest_year}",
            body="The portal could not generate monthly district updates from the latest available records.",
            tone="info",
            ticker_message=f"Monthly district feed could not be generated through {latest_year}"
        )

    climate_updates = [coverage_update]
    if district_feed_update:
        climate_updates.append(district_feed_update)
    if daily_district_feed_update:
        climate_updates.append(daily_district_feed_update)
    if monthly_district_feed_update:
        climate_updates.append(monthly_district_feed_update)
    climate_updates.extend(district_updates)
    climate_updates.extend(daily_district_updates)
    climate_updates.extend(monthly_district_updates)
    climate_updates.extend(event_updates)
    climate_updates.extend(signal_updates)

    ticker_items = [coverage_update["ticker_message"]]
    if province_count or district_count:
        ticker_items.append(
            f"Current dataset scope: {province_count:,} provinces and {int(district_count or 0):,} districts"
        )
    if district_feed_update and district_feed_update.get("ticker_message"):
        ticker_items.append(district_feed_update["ticker_message"])
    if daily_district_feed_update and daily_district_feed_update.get("ticker_message"):
        ticker_items.append(daily_district_feed_update["ticker_message"])
    if monthly_district_feed_update and monthly_district_feed_update.get("ticker_message"):
        ticker_items.append(monthly_district_feed_update["ticker_message"])
    ticker_items.extend(daily_condition_ticker_items)
    ticker_items.extend([
        update["ticker_message"]
        for update in daily_district_updates
        if update.get("ticker_message")
    ])
    ticker_items.extend([
        update["ticker_message"]
        for update in monthly_district_updates
        if update.get("ticker_message")
    ])
    ticker_items.extend([
        update["ticker_message"]
        for update in event_updates
        if update.get("ticker_message")
    ])
    ticker_items.extend([
        update["ticker_message"]
        for update in district_updates
        if update.get("ticker_message")
    ])
    ticker_items.extend([
        update["ticker_message"]
        for update in signal_updates
        if update.get("ticker_message")
    ])

    return {
        "climate_updates": climate_updates,
        "ticker_items": ticker_items,
        "district_updates": district_updates
    }

def build_metric_values(df, metric):
    if df is None or df.empty or 'district' not in df.columns:
        return {}

    metric = (metric or '').strip().lower()

    if metric == 'rainfall':
        grouped = df.groupby('district')['Rainfall_mm'].mean()
    elif metric == 'temperature':
        grouped = df.groupby('district')['Temp_Max_C'].mean()
    elif metric == 'ndvi':
        grouped = df.groupby('district')['NDVI'].mean()
    elif metric == 'population':
        grouped_df = summarize_population_affected(df, ['district'])
        grouped = grouped_df.set_index('district')['PopulationAffected'] if not grouped_df.empty else pd.Series(dtype=float)
    elif metric == 'drought':
        severity_map = {
            'No Drought': 0,
            'Mild': 1,
            'Moderate': 2,
            'Severe': 3
        }
        work = df.copy()
        work['drought_score'] = work['DroughtSeverity'].map(severity_map).fillna(0)
        grouped = work.groupby('district')['drought_score'].mean()
    else:
        raise ValueError("Invalid metric")

    return {
        normalize_name(district): round(float(value), 3)
        for district, value in grouped.dropna().items()
        if str(district).strip()
    }

@api_v1.route('/health', methods=['GET']) 
def health(): 
    try: 
        result = db_manager.execute_query("SELECT 1 as test") 
        db_status = "connected" if result else "disconnected" 
        count_result = db_manager.execute_query("SELECT COUNT(*) as count FROM climate_records") 
        record_count = count_result[0]['count'] if count_result else 0 
        return success_response({"status": "healthy", "database": db_status, "records_loaded": record_count}) 
    except Exception as e: 
        return error_response(str(e), 500) 

@api_v1.route('/provinces', methods=['GET']) 
def get_provinces(): 
    try: 
        options = get_filter_options_from_db() 
        return success_response(options.get('provinces', [])) 
    except Exception as e: 
        return error_response(str(e), 500) 

@api_v1.route('/years', methods=['GET']) 
def get_years(): 
    try: 
        options = get_filter_options_from_db() 
        return success_response(options.get('years', [])) 
    except Exception as e: 
        return error_response(str(e), 500) 


@api_v1.route('/year-coverage', methods=['GET'])
def get_year_coverage():
    try:
        rows = db_manager.execute_query(
            "SELECT year, COUNT(DISTINCT month) AS month_count, COUNT(*) AS record_count "
            "FROM climate_records "
            "WHERE year IS NOT NULL "
            "GROUP BY year "
            "ORDER BY year"
        ) or []
        coverage = []
        for row in rows:
            year = row.get('year')
            if year is None:
                continue
            month_count = int(row.get('month_count') or 0)
            coverage.append({
                "year": int(year),
                "month_count": month_count,
                "record_count": int(row.get('record_count') or 0),
                "is_complete": month_count >= 12
            })

        years = [item["year"] for item in coverage]
        complete_years = [item["year"] for item in coverage if item["is_complete"]]
        latest_year = max(years) if years else None
        latest_complete_year = max(complete_years) if complete_years else latest_year
        return success_response({
            "years": years,
            "coverage": coverage,
            "latest_year": latest_year,
            "latest_complete_year": latest_complete_year,
            "default_year": latest_complete_year
        })
    except Exception as e:
        return error_response(str(e), 500)

@api_v1.route('/districts', methods=['GET'])
def get_districts():
    try:
        options = get_filter_options_from_db()
        return success_response(options.get('districts', []))
    except Exception as e:
        return error_response(str(e), 500)

@api_v1.route('/district-directory', methods=['GET'])
def get_district_directory():
    try:
        rows = db_manager.execute_query(
            "SELECT DISTINCT district, province FROM climate_records "
            "WHERE district IS NOT NULL AND province IS NOT NULL "
            "ORDER BY province, district"
        )
        if not rows:
            return success_response([])

        return success_response([
            {
                "district": row['district'],
                "province": row['province']
            }
            for row in rows
        ])
    except Exception as e:
        return error_response(str(e), 500)

@api_v1.route('/overview', methods=['GET']) 
def get_overview_endpoint(): 
    try: 
        df = load_data_from_db(build_filters(include_year=True)) 
        if df is None or df.empty: 
            return success_response({"total_records": 0}) 
        stats = get_overview(df) 
        return success_response(stats) 
    except Exception as e: 
        return error_response(str(e), 500) 

@api_v1.route('/rainfall-trend', methods=['GET']) 
def get_rainfall_trend(): 
    try: 
        filters = build_filters(include_year=True)
        df = load_data_from_db(filters) 
        if df is None or df.empty: 
            if filters.get('year'):
                return success_response(build_empty_monthly_series_response([
                    "avg_rainfall",
                    "min_rainfall",
                    "max_rainfall"
                ]))
            return success_response({"years": [], "avg_rainfall": []}) 
        trend = rainfall_trend(df) 
        return success_response(trend) 
    except Exception as e: 
        return error_response(str(e), 500) 

@api_v1.route('/rainfall-distribution', methods=['GET'])
def get_rainfall_distribution():
    try:
        df = load_data_from_db(build_filters(include_year=True))
        if df is None or df.empty or 'Rainfall_mm' not in df.columns:
            return success_response({
                "values": [],
                "bins": [],
                "counts": [],
                "min": None,
                "max": None
            })

        values = [float(value) for value in df['Rainfall_mm'].dropna().tolist()]
        if not values:
            return success_response({
                "values": [],
                "bins": [],
                "counts": [],
                "min": None,
                "max": None
            })

        min_value = min(values)
        max_value = max(values)
        bin_count = 8

        if max_value == min_value:
            bins = [round(min_value, 2)]
            counts = [len(values)]
        else:
            step = (max_value - min_value) / bin_count
            edges = [min_value + (step * i) for i in range(bin_count + 1)]
            bins = []
            counts = []

            for index in range(bin_count):
                start = edges[index]
                end = edges[index + 1]
                if index == bin_count - 1:
                    count = sum(1 for value in values if start <= value <= end)
                else:
                    count = sum(1 for value in values if start <= value < end)
                bins.append(f"{start:.1f}-{end:.1f}")
                counts.append(count)

        return success_response({
            "values": [round(value, 2) for value in values],
            "bins": bins,
            "counts": counts,
            "min": round(min_value, 2),
            "max": round(max_value, 2)
        })
    except Exception as e:
        return error_response(str(e), 500)

@api_v1.route('/temperature-trend', methods=['GET']) 
def get_temperature_trend(): 
    try: 
        filters = build_filters(include_year=True)
        df = load_data_from_db(filters) 
        if df is None or df.empty: 
            if filters.get('year'):
                return success_response(build_empty_monthly_series_response([
                    "avg_max_temp",
                    "avg_min_temp"
                ]))
            return success_response({"years": [], "avg_max_temp": [], "avg_min_temp": []}) 
        trend = temperature_trend(df) 
        return success_response(trend) 
    except Exception as e: 
        return error_response(str(e), 500) 


@api_v1.route('/temperature-distribution', methods=['GET'])
def get_temperature_distribution():
    try:
        df = load_data_from_db(build_filters(include_year=True))
        if df is None or df.empty or 'Temp_Max_C' not in df.columns:
            return success_response({
                "values": [],
                "bins": [],
                "counts": [],
                "min": None,
                "max": None
            })

        values = [float(value) for value in df['Temp_Max_C'].dropna().tolist()]
        if not values:
            return success_response({
                "values": [],
                "bins": [],
                "counts": [],
                "min": None,
                "max": None
            })

        min_value = min(values)
        max_value = max(values)
        bin_count = 8

        if max_value == min_value:
            bins = [round(min_value, 2)]
            counts = [len(values)]
        else:
            step = (max_value - min_value) / bin_count
            edges = [min_value + (step * i) for i in range(bin_count + 1)]
            bins = []
            counts = []

            for index in range(bin_count):
                start = edges[index]
                end = edges[index + 1]
                if index == bin_count - 1:
                    count = sum(1 for value in values if start <= value <= end)
                else:
                    count = sum(1 for value in values if start <= value < end)
                bins.append(f"{start:.1f}-{end:.1f}")
                counts.append(count)

        return success_response({
            "values": [round(value, 2) for value in values],
            "bins": bins,
            "counts": counts,
            "min": round(min_value, 2),
            "max": round(max_value, 2)
        })
    except Exception as e:
        return error_response(str(e), 500)

@api_v1.route('/drought-summary', methods=['GET']) 
def get_drought_summary(): 
    try: 
        df = load_data_from_db(build_filters(include_year=True)) 
        if df is None or df.empty: 
            return success_response([]) 
        summary = drought_summary(df) 
        return success_response(summary) 
    except Exception as e: 
        return error_response(str(e), 500) 


@api_v1.route('/drought-trend', methods=['GET'])
def get_drought_trend():
    try:
        filters = build_filters(include_year=True)
        df = load_data_from_db(filters)
        if df is None or df.empty:
            if filters.get('year'):
                return success_response(build_empty_monthly_series_response([
                    "avg_drought_score",
                    "severe_pct",
                    "moderate_pct"
                ]))
            return success_response({"years": [], "avg_drought_score": [], "severe_pct": [], "moderate_pct": []})
        trend = drought_trend(df)
        return success_response(trend)
    except Exception as e:
        return error_response(str(e), 500)


@api_v1.route('/drought-indicators-trend', methods=['GET'])
def get_drought_indicators_trend():
    try:
        filters = build_filters(include_year=True)
        df = load_data_from_db(filters)
        if df is None or df.empty:
            if filters.get('year'):
                return success_response(build_empty_monthly_series_response([
                    "avg_spi",
                    "avg_spei",
                    "avg_pdsi"
                ]))
            return success_response({"years": [], "avg_spi": [], "avg_spei": [], "avg_pdsi": []})
        trend = drought_indicator_trends(df)
        return success_response(trend)
    except Exception as e:
        return error_response(str(e), 500)

@api_v1.route('/ndvi-trend', methods=['GET'])
def get_ndvi_trend():
    try:
        filters = build_filters(include_year=True)
        df = load_data_from_db(filters)
        if df is None or df.empty:
            if filters.get('year'):
                return success_response(build_empty_monthly_series_response(["avg_ndvi"]))
            return success_response({"years": [], "avg_ndvi": []})
        trend = ndvi_trend(df)
        return success_response(trend)
    except Exception as e:
        return error_response(str(e), 500)


@api_v1.route('/soil-moisture-trend', methods=['GET'])
def get_soil_moisture_trend():
    try:
        filters = build_filters(include_year=True)
        df = load_data_from_db(filters)
        if df is None or df.empty:
            if filters.get('year'):
                return success_response(build_empty_monthly_series_response(["avg_soil_moisture"]))
            return success_response({"years": [], "avg_soil_moisture": []})
        trend = soil_moisture_trend(df)
        return success_response(trend)
    except Exception as e:
        return error_response(str(e), 500)

@api_v1.route('/impact-trends', methods=['GET'])
def get_impact_trends():
    try:
        filters = build_filters(include_year=True)
        df = load_data_from_db(filters)
        if df is None or df.empty:
            if filters.get('year'):
                return success_response(build_empty_monthly_series_response([
                    "crop_yield",
                    "population_affected",
                    "hydropower_mw",
                    "lake_kariba_level",
                    "food_price_zmw"
                ]))
            return success_response({
                "years": [],
                "crop_yield": [],
                "population_affected": [],
                "hydropower_mw": [],
                "lake_kariba_level": [],
                "food_price_zmw": []
            })
        trends = impact_trends(df)
        return success_response(trends)
    except Exception as e:
        return error_response(str(e), 500)

@api_v1.route('/impact-driver-breakdown', methods=['GET'])
def get_impact_driver_breakdown():
    try:
        df = load_data_from_db(build_filters(include_year=True))
        if df is None or df.empty:
            return success_response({
                "total_population_affected": 0,
                "total_records_with_population": 0,
                "variables": [],
                "method": "Population affected is assigned to the climate variable with the strongest normalized stress signal in each record."
            })

        breakdown = impact_driver_breakdown(df)
        return success_response(breakdown)
    except Exception as e:
        return error_response(str(e), 500)

@api_v1.route('/population-affected-districts', methods=['GET'])
def get_population_affected_districts():
    try:
        filters = build_filters(include_year=True)
        df = load_data_from_db(filters)
        year = filters.get('year')
        province = filters.get('province')
        district = filters.get('district')

        if df is None or df.empty:
            return success_response({
                "year": year,
                "province": province,
                "district": district,
                "total_population_affected": 0,
                "total_districts": 0,
                "districts": []
            })

        if 'district' not in df.columns or 'PopulationAffected' not in df.columns:
            return success_response({
                "year": year,
                "province": province,
                "district": district,
                "total_population_affected": 0,
                "total_districts": 0,
                "districts": []
            })

        grouped = summarize_population_affected(df, ['district'])
        grouped = grouped[grouped['district'].astype(str).str.strip() != '']
        grouped = grouped.sort_values(['PopulationAffected', 'district'], ascending=[False, True])

        districts = [
            {
                "district": row['district'],
                "population_affected": int(row['PopulationAffected'])
            }
            for _, row in grouped.iterrows()
        ]

        return success_response({
            "year": year,
            "province": province,
            "district": district,
            "total_population_affected": summarize_population_affected(df),
            "total_districts": int(len(districts)),
            "districts": districts
        })
    except Exception as e:
        return error_response(str(e), 500)


@api_v1.route('/district-monthly-notifications', methods=['GET'])
def get_district_monthly_notifications():
    try:
        filters = build_filters(include_year=True)
        selected_year = filters.get('year')
        selected_province = filters.get('province')
        selected_district = filters.get('district')

        df = load_data_from_db(filters, columns=[
            'year',
            'month',
            'district',
            'province',
            'Rainfall_mm',
            'Temp_Max_C',
            'NDVI',
            'DroughtSeverity',
            'PopulationAffected'
        ])

        if df is None or df.empty:
            empty_items = [
                build_missing_month_notification_item(
                    month,
                    selected_year,
                    district=selected_district,
                    province=selected_province
                )
                for month in MONTH_SEQUENCE
            ] if selected_year else []
            return success_response({
                "year": selected_year,
                "province": selected_province,
                "district": selected_district,
                "district_count": 0,
                "month_count": len(empty_items) if empty_items else 0,
                "item_count": len(empty_items),
                "items": empty_items
            })

        if selected_year is None and 'year' in df.columns and not df['year'].dropna().empty:
            selected_year = int(df['year'].dropna().astype(int).max())
            df = df[df['year'] == selected_year]

        items = build_monthly_notification_items(
            df,
            selected_year,
            district_filter=selected_district,
            province_filter=selected_province
        )

        district_count = int(df['district'].dropna().astype(str).str.strip().replace('', pd.NA).dropna().nunique()) if 'district' in df.columns else 0
        month_count = len({
            int(item['month'])
            for item in items
            if item.get('month') is not None
        }) if items else (12 if selected_district and selected_year else 0)

        return success_response({
            "year": selected_year,
            "province": selected_province,
            "district": selected_district,
            "district_count": district_count,
            "month_count": month_count,
            "item_count": len(items),
            "items": items
        })
    except Exception as e:
        logger.error(f"District monthly notifications error: {e}", exc_info=True)
        return error_response(str(e), 500)


@api_v1.route('/district-summary', methods=['GET'])
def get_district_summary():
    try:
        district = request.args.get('district', '').strip()
        year = request.args.get('year', type=int)
        if not district:
            return error_response("district is required", 400)

        filters = {'district': district}
        if year:
            filters['year'] = year

        df = load_data_from_db(filters, columns=[
            'district', 'year', 'province', 'Rainfall_mm', 'Temp_Max_C',
            'Temp_Min_C', 'NDVI', 'SoilMoisture_pct', 'DroughtSeverity'
        ])
        if df is None or df.empty:
            return success_response({})

        province = None
        if 'province' in df.columns and not df['province'].dropna().empty:
            province = str(df['province'].dropna().iloc[0])

        drought_mode = None
        if 'DroughtSeverity' in df.columns and not df['DroughtSeverity'].dropna().empty:
            drought_mode = str(df['DroughtSeverity'].mode().iloc[0])

        return success_response({
            "district": district,
            "province": province,
            "year": year,
            "avg_rainfall": round(float(df['Rainfall_mm'].mean()), 2) if 'Rainfall_mm' in df.columns and not df['Rainfall_mm'].dropna().empty else None,
            "avg_temp_max": round(float(df['Temp_Max_C'].mean()), 2) if 'Temp_Max_C' in df.columns and not df['Temp_Max_C'].dropna().empty else None,
            "avg_temp_min": round(float(df['Temp_Min_C'].mean()), 2) if 'Temp_Min_C' in df.columns and not df['Temp_Min_C'].dropna().empty else None,
            "avg_ndvi": round(float(df['NDVI'].mean()), 3) if 'NDVI' in df.columns and not df['NDVI'].dropna().empty else None,
            "avg_soil_moisture": round(float(df['SoilMoisture_pct'].mean()), 2) if 'SoilMoisture_pct' in df.columns and not df['SoilMoisture_pct'].dropna().empty else None,
            "drought_severity": drought_mode
        })
    except Exception as e:
        return error_response(str(e), 500)

@api_v1.route('/map-district-metric', methods=['GET'])
def get_map_district_metric():
    try:
        metric = request.args.get('metric', 'drought').strip().lower()
        year = request.args.get('year', type=int)

        filters = {}
        if year:
            filters['year'] = year

        metric_columns = {
            'rainfall': ['district', 'Rainfall_mm'],
            'temperature': ['district', 'Temp_Max_C'],
            'drought': ['district', 'DroughtSeverity'],
            'population': ['district', 'PopulationAffected'],
            'ndvi': ['district', 'NDVI']
        }
        df = load_data_from_db(filters, columns=metric_columns.get(metric, ['district']))
        if df is None or df.empty:
            return success_response({
                "metric": metric,
                "year": year,
                "values": {},
                "display_names": {}
            })

        if 'district' not in df.columns:
            return error_response("district column not found", 400)

        try:
            values = build_metric_values(df, metric)
        except ValueError:
            return error_response("Invalid metric. Choose from: rainfall, temperature, drought, population, ndvi", 400)

        display_names = {
            normalize_name(district): str(district)
            for district in df['district'].dropna().astype(str).unique().tolist()
            if district.strip()
        }

        return success_response({
            "metric": metric,
            "year": year,
            "values": values,
            "display_names": display_names
        })
    except Exception as e:
        return error_response(str(e), 500)

@api_v1.route('/extreme-events', methods=['GET'])
def get_extreme_events():
    try:
        filters = build_filters(include_year=True)
        df = load_data_from_db(filters, columns=[
            'year', 'month', 'province', 'district', 'Rainfall_mm', 'Temp_Max_C',
            'DroughtSeverity', 'PopulationAffected'
        ])
        empty_monthly = build_empty_monthly_chart_payload([
            "heat_events",
            "heavy_rainfall_events",
            "severe_drought_events",
            "population_affected"
        ])

        if df is None or df.empty:
            return success_response({
                "year": filters.get('year'),
                "province": filters.get('province'),
                "summary": {
                    "heat_event_count": 0,
                    "heavy_rainfall_count": 0,
                    "severe_drought_count": 0,
                    "total_population_affected": 0,
                    "max_temperature": None,
                    "max_rainfall": None
                },
                "monthly": empty_monthly,
                "hotspots": [],
                "insights": []
            })

        if 'month' not in df.columns:
            return error_response("Month column not found in data", 400)

        df = prepare_monthly_frame(df, "month")
        if df.empty:
            return success_response({
                "year": filters.get('year'),
                "province": filters.get('province'),
                "summary": {
                    "heat_event_count": 0,
                    "heavy_rainfall_count": 0,
                    "severe_drought_count": 0,
                    "total_population_affected": 0,
                    "max_temperature": None,
                    "max_rainfall": None
                },
                "monthly": empty_monthly,
                "hotspots": [],
                "insights": []
            })

        rainfall_threshold = None
        temp_threshold = None
        if 'Rainfall_mm' in df.columns and not df['Rainfall_mm'].dropna().empty:
            rainfall_threshold = float(df['Rainfall_mm'].quantile(0.90))
        if 'Temp_Max_C' in df.columns and not df['Temp_Max_C'].dropna().empty:
            temp_threshold = float(df['Temp_Max_C'].quantile(0.90))

        observed_month_rows = []
        for month in sorted(df['month'].dropna().astype(int).unique().tolist()):
            month_df = df[df['month'] == month]
            heavy_count = int((month_df['Rainfall_mm'] >= rainfall_threshold).sum()) if rainfall_threshold is not None and 'Rainfall_mm' in month_df.columns else 0
            heat_count = int((month_df['Temp_Max_C'] >= temp_threshold).sum()) if temp_threshold is not None and 'Temp_Max_C' in month_df.columns else 0
            severe_count = int(month_df['DroughtSeverity'].astype(str).str.lower().eq('severe').sum()) if 'DroughtSeverity' in month_df.columns else 0
            pop_sum = summarize_population_affected(month_df)
            observed_month_rows.append({
                "month": month,
                "heavy_rainfall_events": heavy_count,
                "heat_events": heat_count,
                "severe_drought_events": severe_count,
                "population_affected": pop_sum
            })

        monthly_payload, monthly_rows = build_monthly_chart_payload(
            observed_month_rows,
            [
                "heat_events",
                "heavy_rainfall_events",
                "severe_drought_events",
                "population_affected"
            ]
        )
        monthly_heat = monthly_payload["heat_events"]
        monthly_rain = monthly_payload["heavy_rainfall_events"]
        monthly_drought = monthly_payload["severe_drought_events"]
        monthly_population = monthly_payload["population_affected"]

        yearly_filters = {'year': filters.get('year')} if filters.get('year') else {}
        hotspot_df = load_data_from_db(yearly_filters, columns=[
            'province', 'Rainfall_mm', 'Temp_Max_C', 'DroughtSeverity'
        ]) if 'province' in df.columns else df
        if hotspot_df is None or hotspot_df.empty:
            hotspot_df = df

        hotspots = []
        if 'province' in hotspot_df.columns:
            if 'Rainfall_mm' in hotspot_df.columns and rainfall_threshold is not None:
                rain_rank = hotspot_df[hotspot_df['Rainfall_mm'] >= rainfall_threshold].groupby('province').size().sort_values(ascending=False)
                for province, count in rain_rank.head(3).items():
                    hotspots.append({"type": "Heavy rainfall", "province": province, "value": int(count)})

            if 'Temp_Max_C' in hotspot_df.columns and temp_threshold is not None:
                heat_rank = hotspot_df[hotspot_df['Temp_Max_C'] >= temp_threshold].groupby('province').size().sort_values(ascending=False)
                for province, count in heat_rank.head(3).items():
                    hotspots.append({"type": "Heat events", "province": province, "value": int(count)})

            if 'DroughtSeverity' in hotspot_df.columns:
                drought_rank = hotspot_df[hotspot_df['DroughtSeverity'].astype(str).str.lower() == 'severe'].groupby('province').size().sort_values(ascending=False)
                for province, count in drought_rank.head(3).items():
                    hotspots.append({"type": "Severe drought", "province": province, "value": int(count)})

        heat_rows = [row for row in monthly_rows if (row['heat_events'] or 0) > 0]
        rain_rows = [row for row in monthly_rows if (row['heavy_rainfall_events'] or 0) > 0]
        drought_rows = [row for row in monthly_rows if (row['severe_drought_events'] or 0) > 0]
        max_heat_month = max(heat_rows, key=lambda row: row['heat_events']) if heat_rows else None
        max_rain_month = max(rain_rows, key=lambda row: row['heavy_rainfall_events']) if rain_rows else None
        max_drought_month = max(drought_rows, key=lambda row: row['severe_drought_events']) if drought_rows else None

        insights = []
        if max_heat_month:
            insights.append(f"Highest heat-event activity was in {max_heat_month['label']} ({max_heat_month['heat_events']} records).")
        if max_rain_month:
            insights.append(f"Heavy-rainfall events peaked in {max_rain_month['label']} ({max_rain_month['heavy_rainfall_events']} records).")
        if max_drought_month:
            insights.append(f"Severe drought records were highest in {max_drought_month['label']} ({max_drought_month['severe_drought_events']} records).")

        return success_response({
            "year": filters.get('year'),
            "province": filters.get('province'),
            "thresholds": {
                "rainfall_threshold_90p": round(rainfall_threshold, 2) if rainfall_threshold is not None else None,
                "temperature_threshold_90p": round(temp_threshold, 2) if temp_threshold is not None else None
            },
            "summary": {
                "heat_event_count": int(sum(value for value in monthly_heat if value is not None)),
                "heavy_rainfall_count": int(sum(value for value in monthly_rain if value is not None)),
                "severe_drought_count": int(sum(value for value in monthly_drought if value is not None)),
                "total_population_affected": summarize_population_affected(df),
                "max_temperature": round(float(df['Temp_Max_C'].max()), 2) if 'Temp_Max_C' in df.columns and not df['Temp_Max_C'].dropna().empty else None,
                "max_rainfall": round(float(df['Rainfall_mm'].max()), 2) if 'Rainfall_mm' in df.columns and not df['Rainfall_mm'].dropna().empty else None
            },
            "monthly": monthly_payload,
            "hotspots": hotspots,
            "insights": insights
        })
    except Exception as e:
        return error_response(str(e), 500)


@api_v1.route('/flood-events', methods=['GET'])
def get_flood_events():
    try:
        filters = build_filters(include_year=True)
        df = load_data_from_db(filters, columns=[
            'year', 'month', 'province', 'district', 'Rainfall_mm',
            'SPI', 'SoilMoisture_pct', 'PopulationAffected'
        ])
        empty_extreme_rainfall = build_empty_monthly_chart_payload([
            "high_rainfall_events",
            "very_high_rainfall_events",
            "extreme_rainfall_events"
        ])
        empty_extreme_rainfall["top_rainfall_values"] = []
        empty_monthly_pattern = build_empty_monthly_chart_payload([
            "flood_events",
            "population_affected",
            "average_rainfall"
        ])

        if df is None or df.empty:
            return success_response({
                "year": filters.get('year'),
                "province": filters.get('province'),
                "thresholds": {
                    "rainfall_threshold_90p": None,
                    "high_rainfall_mm": 50,
                    "very_high_rainfall_mm": 100,
                    "extreme_rainfall_mm": 150
                },
                "summary": {
                    "flood_event_count": 0,
                    "high_rainfall_count": 0,
                    "very_high_rainfall_count": 0,
                    "extreme_rainfall_count": 0,
                    "total_population_affected": 0,
                    "max_rainfall": None,
                    "peak_month": None,
                    "avg_spi": None,
                    "avg_soil_moisture": None
                },
                "extreme_rainfall": empty_extreme_rainfall,
                "rainfall_trend": {
                    "labels": [],
                    "average_rainfall": []
                },
                "spi_trend": {
                    "labels": [],
                    "average_spi": []
                },
                "soil_moisture_trend": {
                    "labels": [],
                    "average_soil_moisture": []
                },
                "province_rainfall": {
                    "labels": [],
                    "values": []
                },
                "monthly_pattern": empty_monthly_pattern,
                "hotspots": [],
                "insights": []
            })

        if 'month' not in df.columns:
            return error_response("Month column not found in data", 400)

        df = prepare_monthly_frame(df, "month")
        if df.empty:
            return success_response({
                "year": filters.get('year'),
                "province": filters.get('province'),
                "thresholds": {
                    "rainfall_threshold_90p": None,
                    "high_rainfall_mm": 50,
                    "very_high_rainfall_mm": 100,
                    "extreme_rainfall_mm": 150
                },
                "summary": {
                    "flood_event_count": 0,
                    "high_rainfall_count": 0,
                    "very_high_rainfall_count": 0,
                    "extreme_rainfall_count": 0,
                    "total_population_affected": 0,
                    "max_rainfall": None,
                    "peak_month": None,
                    "avg_spi": None,
                    "avg_soil_moisture": None
                },
                "extreme_rainfall": empty_extreme_rainfall,
                "rainfall_trend": {
                    "labels": [],
                    "average_rainfall": []
                },
                "spi_trend": {
                    "labels": [],
                    "average_spi": []
                },
                "soil_moisture_trend": {
                    "labels": [],
                    "average_soil_moisture": []
                },
                "province_rainfall": {
                    "labels": [],
                    "values": []
                },
                "monthly_pattern": empty_monthly_pattern,
                "hotspots": [],
                "insights": []
            })

        high_threshold = 50
        very_high_threshold = 100
        extreme_threshold = 150
        rainfall_threshold = None
        if 'Rainfall_mm' in df.columns and not df['Rainfall_mm'].dropna().empty:
            rainfall_threshold = float(df['Rainfall_mm'].quantile(0.90))

        observed_month_rows = []
        for month in sorted(df['month'].dropna().astype(int).unique().tolist()):
            month_df = df[df['month'] == month]
            flood_count = int((month_df['Rainfall_mm'] >= rainfall_threshold).sum()) if rainfall_threshold is not None and 'Rainfall_mm' in month_df.columns else 0
            high_count = int((month_df['Rainfall_mm'] >= high_threshold).sum()) if 'Rainfall_mm' in month_df.columns else 0
            very_high_count = int((month_df['Rainfall_mm'] >= very_high_threshold).sum()) if 'Rainfall_mm' in month_df.columns else 0
            extreme_count = int((month_df['Rainfall_mm'] >= extreme_threshold).sum()) if 'Rainfall_mm' in month_df.columns else 0
            pop_sum = summarize_population_affected(month_df)
            avg_rainfall = float(month_df['Rainfall_mm'].mean()) if 'Rainfall_mm' in month_df.columns and not month_df['Rainfall_mm'].dropna().empty else None
            avg_spi = float(month_df['SPI'].mean()) if 'SPI' in month_df.columns and not month_df['SPI'].dropna().empty else None
            avg_soil_moisture = float(month_df['SoilMoisture_pct'].mean()) if 'SoilMoisture_pct' in month_df.columns and not month_df['SoilMoisture_pct'].dropna().empty else None
            observed_month_rows.append({
                "month": month,
                "flood_events": flood_count,
                "high_rainfall_events": high_count,
                "very_high_rainfall_events": very_high_count,
                "extreme_rainfall_events": extreme_count,
                "population_affected": pop_sum,
                "average_rainfall": round(avg_rainfall, 2) if avg_rainfall is not None else None,
                "average_spi": round(avg_spi, 2) if avg_spi is not None else None,
                "average_soil_moisture": round(avg_soil_moisture, 2) if avg_soil_moisture is not None else None
            })

        extreme_rainfall_payload, _ = build_monthly_chart_payload(
            observed_month_rows,
            [
                "high_rainfall_events",
                "very_high_rainfall_events",
                "extreme_rainfall_events"
            ]
        )
        monthly_pattern_payload, monthly_rows = build_monthly_chart_payload(
            observed_month_rows,
            [
                "flood_events",
                "population_affected",
                "average_rainfall"
            ]
        )
        monthly_flood = monthly_pattern_payload["flood_events"]
        monthly_high = extreme_rainfall_payload["high_rainfall_events"]
        monthly_very_high = extreme_rainfall_payload["very_high_rainfall_events"]
        monthly_extreme = extreme_rainfall_payload["extreme_rainfall_events"]
        monthly_population = monthly_pattern_payload["population_affected"]
        monthly_avg_rainfall = monthly_pattern_payload["average_rainfall"]

        yearly_rainfall = []
        if 'year' in df.columns and 'Rainfall_mm' in df.columns:
            grouped = (
                df.groupby('year')['Rainfall_mm']
                .mean()
                .reset_index()
                .sort_values('year')
            )
            yearly_rainfall = [
                {
                    "label": str(int(row['year'])),
                    "value": round(float(row['Rainfall_mm']), 2)
                }
                for _, row in grouped.iterrows()
            ]

        spi_trend = []
        if 'year' in df.columns and 'SPI' in df.columns:
            grouped = (
                df.groupby('year')['SPI']
                .mean()
                .reset_index()
                .sort_values('year')
            )
            spi_trend = [
                {
                    "label": str(int(row['year'])),
                    "value": round(float(row['SPI']), 2)
                }
                for _, row in grouped.iterrows()
                if row['SPI'] is not None
            ]

        soil_moisture_trend = []
        if 'year' in df.columns and 'SoilMoisture_pct' in df.columns:
            grouped = (
                df.groupby('year')['SoilMoisture_pct']
                .mean()
                .reset_index()
                .sort_values('year')
            )
            soil_moisture_trend = [
                {
                    "label": str(int(row['year'])),
                    "value": round(float(row['SoilMoisture_pct']), 2)
                }
                for _, row in grouped.iterrows()
                if row['SoilMoisture_pct'] is not None
            ]

        province_rainfall = []
        if 'province' in df.columns and 'Rainfall_mm' in df.columns:
            grouped = (
                df.groupby('province')['Rainfall_mm']
                .mean()
                .reset_index()
                .sort_values('Rainfall_mm', ascending=False)
            )
            province_rainfall = [
                {
                    "label": row['province'],
                    "value": round(float(row['Rainfall_mm']), 2)
                }
                for _, row in grouped.head(8).iterrows()
            ]

        top_rainfall_values = []
        if 'province' in df.columns and 'Rainfall_mm' in df.columns:
            top_rows = (
                df[['province', 'Rainfall_mm']]
                .dropna(subset=['Rainfall_mm'])
                .copy()
            )
            if not top_rows.empty:
                top_rows['province'] = top_rows['province'].fillna('').astype(str).str.strip()
                top_rows = top_rows[top_rows['province'] != '']
                top_rows = (
                    top_rows.groupby('province', as_index=False)['Rainfall_mm']
                    .max()
                    .sort_values(['Rainfall_mm', 'province'], ascending=[False, True])
                    .head(8)
                )
                top_rainfall_values = [
                    {
                        "location": row['province'],
                        "province": row['province'],
                        "value": round(float(row['Rainfall_mm']), 2)
                    }
                    for _, row in top_rows.iterrows()
                ]

        hotspots = []
        if 'province' in df.columns and rainfall_threshold is not None:
            rain_rank = (
                df[df['Rainfall_mm'] >= rainfall_threshold]
                .groupby('province')
                .size()
                .sort_values(ascending=False)
            )
            for province, count in rain_rank.head(5).items():
                hotspots.append({"province": province, "flood_events": int(count)})

        flood_rows = [row for row in monthly_rows if (row['flood_events'] or 0) > 0]
        peak_month = max(flood_rows, key=lambda row: row['flood_events']) if flood_rows else None
        insights = []
        if rainfall_threshold is not None:
            insights.append(
                f"Flood signals are based on rainfall values at or above {round(rainfall_threshold, 2)} mm, which is the 90th percentile for the selected data."
            )
        insights.append(
            f"Simple wet-condition thresholds are also tracked as high rainfall ({high_threshold}+ mm), very high rainfall ({very_high_threshold}+ mm), and extreme rainfall ({extreme_threshold}+ mm)."
        )
        if peak_month:
            insights.append(
                f"Flood-related rainfall activity peaked in {peak_month['label']} with {peak_month['flood_events']} high-rainfall records."
            )
        if hotspots:
            lead = hotspots[0]
            insights.append(
                f"{lead['province']} recorded the highest concentration of flood-like rainfall events in the active view."
            )
        if 'SPI' in df.columns and not df['SPI'].dropna().empty:
            wet_spi_share = float((df['SPI'] > 1).mean() * 100)
            insights.append(
                f"{round(wet_spi_share, 1)}% of available SPI records are above 1, indicating wetter-than-normal conditions."
            )
        if 'SoilMoisture_pct' in df.columns and not df['SoilMoisture_pct'].dropna().empty:
            insights.append(
                f"Average soil moisture in the filtered data is {round(float(df['SoilMoisture_pct'].mean()), 1)}%, which helps indicate how saturated the ground may be."
            )

        return success_response({
            "year": filters.get('year'),
            "province": filters.get('province'),
            "thresholds": {
                "rainfall_threshold_90p": round(rainfall_threshold, 2) if rainfall_threshold is not None else None,
                "high_rainfall_mm": high_threshold,
                "very_high_rainfall_mm": very_high_threshold,
                "extreme_rainfall_mm": extreme_threshold
            },
            "summary": {
                "flood_event_count": int(sum(value for value in monthly_flood if value is not None)),
                "high_rainfall_count": int(sum(value for value in monthly_high if value is not None)),
                "very_high_rainfall_count": int(sum(value for value in monthly_very_high if value is not None)),
                "extreme_rainfall_count": int(sum(value for value in monthly_extreme if value is not None)),
                "total_population_affected": summarize_population_affected(df),
                "max_rainfall": round(float(df['Rainfall_mm'].max()), 2) if 'Rainfall_mm' in df.columns and not df['Rainfall_mm'].dropna().empty else None,
                "peak_month": peak_month['label'] if peak_month else None,
                "avg_spi": round(float(df['SPI'].mean()), 2) if 'SPI' in df.columns and not df['SPI'].dropna().empty else None,
                "avg_soil_moisture": round(float(df['SoilMoisture_pct'].mean()), 2) if 'SoilMoisture_pct' in df.columns and not df['SoilMoisture_pct'].dropna().empty else None
            },
            "extreme_rainfall": {
                **extreme_rainfall_payload,
                "top_rainfall_values": top_rainfall_values
            },
            "rainfall_trend": {
                "labels": [item['label'] for item in yearly_rainfall],
                "average_rainfall": [item['value'] for item in yearly_rainfall]
            },
            "spi_trend": {
                "labels": [item['label'] for item in spi_trend],
                "average_spi": [item['value'] for item in spi_trend]
            },
            "soil_moisture_trend": {
                "labels": [item['label'] for item in soil_moisture_trend],
                "average_soil_moisture": [item['value'] for item in soil_moisture_trend]
            },
            "province_rainfall": {
                "labels": [item['label'] for item in province_rainfall],
                "values": [item['value'] for item in province_rainfall]
            },
            "monthly_pattern": monthly_pattern_payload,
            "hotspots": hotspots,
            "insights": insights
        })
    except Exception as e:
        logger.error(f"Flood events error: {e}", exc_info=True)
        return error_response(str(e), 500)


@api_v1.route('/district-comparison', methods=['GET'])
def get_district_comparison():
    try:
        df = load_data_from_db(columns=[
            'district', 'province', 'year', 'Rainfall_mm', 'Temp_Max_C',
            'SoilMoisture_pct', 'NDVI', 'PopulationAffected', 'DroughtSeverity'
        ])
        if df is None or df.empty:
            return success_response({
                "year": None,
                "available_years": [],
                "available_metrics": list_district_comparison_metrics(),
                "selected_metrics": DEFAULT_DISTRICT_COMPARISON_METRICS,
                "focus_metric": "rainfall",
                "focus_metric_label": DISTRICT_COMPARISON_METRICS["rainfall"]["label"],
                "focus_metric_unit": DISTRICT_COMPARISON_METRICS["rainfall"]["unit"],
                "districts": [],
                "comparison": {"labels": [], "values": []},
                "trend": {"years": [], "series": []},
                "table": [],
                "insights": []
            })

        if 'district' not in df.columns or 'year' not in df.columns:
            return error_response("District comparison requires district and year columns", 400)

        available_years = sorted(df['year'].dropna().astype(int).unique().tolist())
        selected_year = request.args.get('year', type=int) or (max(available_years) if available_years else None)

        metrics_param = request.args.get('metrics', '')
        selected_metrics = [
            metric.strip().lower()
            for metric in metrics_param.split(',')
            if metric.strip().lower() in DISTRICT_COMPARISON_METRICS
        ]
        if not selected_metrics:
            selected_metrics = DEFAULT_DISTRICT_COMPARISON_METRICS.copy()

        focus_metric = request.args.get('focus_metric', 'rainfall').strip().lower()
        if focus_metric not in DISTRICT_COMPARISON_METRICS:
            focus_metric = 'rainfall'
        if focus_metric not in selected_metrics:
            selected_metrics = [focus_metric] + [metric for metric in selected_metrics if metric != focus_metric]

        district_lookup = {
            normalize_name(district): str(district)
            for district in df['district'].dropna().astype(str).tolist()
            if district.strip()
        }

        requested_districts = [
            district.strip()
            for district in request.args.get('districts', '').split(',')
            if district.strip()
        ]

        selected_districts = []
        for district in requested_districts:
            matched = district_lookup.get(normalize_name(district))
            if matched and matched not in selected_districts:
                selected_districts.append(matched)

        selected_districts = selected_districts[:4]

        province_lookup = {}
        if 'province' in df.columns:
            province_lookup = (
                df[['district', 'province']]
                .dropna(subset=['district', 'province'])
                .drop_duplicates(subset=['district'])
                .set_index('district')['province']
                .astype(str)
                .to_dict()
            )

        df_year = df[df['year'] == selected_year] if selected_year is not None else df.iloc[0:0]
        df_selected_year = df_year[df_year['district'].isin(selected_districts)] if not df_year.empty else df_year
        df_selected_all_years = df[df['district'].isin(selected_districts)]

        table_rows = []
        for district in selected_districts:
            district_df = df_selected_year[df_selected_year['district'] == district]
            metric_values = {
                metric_key: aggregate_metric_value(district_df, metric_key)
                for metric_key in selected_metrics
            }
            table_rows.append({
                "district": district,
                "province": province_lookup.get(district),
                "metrics": metric_values
            })

        comparison_values = [row['metrics'].get(focus_metric) for row in table_rows]

        trend_series = []
        for district in selected_districts:
            district_history = df_selected_all_years[df_selected_all_years['district'] == district]
            year_map = {}
            for year in available_years:
                year_value = aggregate_metric_value(district_history[district_history['year'] == year], focus_metric)
                year_map[year] = year_value

            trend_series.append({
                "district": district,
                "province": province_lookup.get(district),
                "values": [year_map.get(year) for year in available_years]
            })

        valid_focus_rows = [
            row for row in table_rows
            if row['metrics'].get(focus_metric) is not None
        ]
        insights = []
        if valid_focus_rows:
            leader = max(valid_focus_rows, key=lambda row: row['metrics'][focus_metric])
            trailer = min(valid_focus_rows, key=lambda row: row['metrics'][focus_metric])
            gap = round_metric_value(
                focus_metric,
                leader['metrics'][focus_metric] - trailer['metrics'][focus_metric]
            )
            metric_label = DISTRICT_COMPARISON_METRICS[focus_metric]['label']
            metric_unit = DISTRICT_COMPARISON_METRICS[focus_metric]['unit']
            unit_suffix = f" {metric_unit}".rstrip()
            insights.append(
                f"{leader['district']} has the highest {metric_label.lower()} in {selected_year} at "
                f"{leader['metrics'][focus_metric]}{unit_suffix}."
            )
            insights.append(
                f"The gap between the highest and lowest selected districts is {gap}{unit_suffix} for {metric_label.lower()}."
            )

        if 'ndvi' in selected_metrics:
            ndvi_rows = [row for row in table_rows if row['metrics'].get('ndvi') is not None]
            if ndvi_rows:
                greenest = max(ndvi_rows, key=lambda row: row['metrics']['ndvi'])
                insights.append(
                    f"{greenest['district']} shows the strongest vegetation signal among the selected districts "
                    f"with an NDVI of {greenest['metrics']['ndvi']}."
                )

        return success_response({
            "year": selected_year,
            "available_years": available_years,
            "available_metrics": list_district_comparison_metrics(),
            "selected_metrics": selected_metrics,
            "focus_metric": focus_metric,
            "focus_metric_label": DISTRICT_COMPARISON_METRICS[focus_metric]["label"],
            "focus_metric_unit": DISTRICT_COMPARISON_METRICS[focus_metric]["unit"],
            "districts": selected_districts,
            "comparison": {
                "labels": [row['district'] for row in table_rows],
                "values": comparison_values
            },
            "trend": {
                "years": available_years,
                "series": trend_series
            },
            "table": table_rows,
            "insights": insights
        })
    except Exception as e:
        logger.error(f"District comparison error: {e}", exc_info=True)
        return error_response(str(e), 500)


@api_v1.route('/explorer', methods=['GET'])
def get_explorer_data():
    try:
        filters = parse_explorer_filters()
        variable = filters["variable"]
        force_monthly = (
            filters.get("start_year") is not None and
            filters.get("start_year") == filters.get("end_year")
        )
        if variable not in EXPLORER_VARIABLES:
            return error_response("Invalid variable selected", 400)

        df = load_data_from_db(columns=[
            'date', 'province', 'district', 'year', 'month', 'Rainfall_mm',
            'Temp_Max_C', 'Temp_Min_C', 'SoilMoisture_pct', 'NDVI',
            'SPI', 'SPEI', 'PDSI', 'DroughtSeverity'
        ])
        if df is None or df.empty:
            return success_response({
                "filters": filters,
                "variables": get_explorer_variable_options(),
                "chart": build_explorer_trend(df, variable, force_monthly=force_monthly),
                "summary": build_explorer_summary(df, variable),
                "table": {"rows": [], "shown_rows": 0, "total_rows": 0}
            })

        filtered_df = filter_explorer_df(df, filters)
        rows = build_explorer_rows(filtered_df)
        return success_response({
            "filters": filters,
            "variables": get_explorer_variable_options(),
            "chart": build_explorer_trend(filtered_df, variable, force_monthly=force_monthly),
            "summary": build_explorer_summary(filtered_df, variable),
            "table": {
                "rows": rows,
                "shown_rows": len(rows),
                "total_rows": int(len(filtered_df))
            }
        })
    except Exception as e:
        logger.error(f"Explorer API error: {e}", exc_info=True)
        return error_response(str(e), 500)


@api_v1.route('/explorer/export', methods=['GET'])
def export_explorer_data():
    try:
        filters = parse_explorer_filters()
        variable = filters["variable"]
        if variable not in EXPLORER_VARIABLES:
            return error_response("Invalid variable selected", 400)

        df = load_data_from_db(columns=[
            'date', 'province', 'district', 'year', 'month', 'Rainfall_mm',
            'Temp_Max_C', 'Temp_Min_C', 'SoilMoisture_pct', 'NDVI',
            'SPI', 'SPEI', 'PDSI', 'DroughtSeverity'
        ])
        if df is None or df.empty:
            return error_response("No data available for export", 404)

        filtered_df = filter_explorer_df(df, filters)
        if filtered_df.empty:
            return error_response("No data found for the selected filters", 404)

        date_col = get_explorer_date_column(filtered_df)
        export_columns = [
            date_col,
            'province',
            'district',
            'year',
            'month',
            'Rainfall_mm',
            'Temp_Max_C',
            'Temp_Min_C',
            'SoilMoisture_pct',
            'NDVI',
            'SPI',
            'SPEI',
            'PDSI',
            'DroughtSeverity'
        ]
        export_columns = [column for column in export_columns if column and column in filtered_df.columns]
        export_df = filtered_df[export_columns].copy()

        if date_col and date_col in export_df.columns:
            export_df = export_df.sort_values(date_col, ascending=False)
        elif 'year' in export_df.columns:
            sort_columns = ['year']
            if 'month' in export_df.columns:
                sort_columns.append('month')
            export_df = export_df.sort_values(sort_columns, ascending=False)

        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(export_df.columns.tolist())
        for row in export_df.itertuples(index=False, name=None):
            writer.writerow(row)

        province_label = filters['province'] if filters['province'] and filters['province'].lower() != 'all' else 'all-provinces'
        district_label = filters['district'] if filters['district'] and filters['district'].lower() != 'all' else 'all-districts'
        start_label = filters['start_year'] if filters['start_year'] is not None else 'start'
        end_label = filters['end_year'] if filters['end_year'] is not None else 'end'
        filename = f"climate-explorer-{province_label}-{district_label}-{start_label}-{end_label}.csv".replace(' ', '-')

        return Response(
            buffer.getvalue(),
            mimetype='text/csv',
            headers={"Content-Disposition": f'attachment; filename=\"{filename}\"'}
        )
    except Exception as e:
        logger.error(f"Explorer export error: {e}", exc_info=True)
        return error_response(str(e), 500)


@api_v1.route('/site-summary', methods=['GET'])
def get_site_summary():
    try:
        now = time.time()
        if SITE_SUMMARY_CACHE["value"] is not None and SITE_SUMMARY_CACHE["expires_at"] > now:
            payload = SITE_SUMMARY_CACHE["value"]
        else:
            options = get_filter_options_from_db()
            provinces = sorted(options.get('provinces', []))
            years = sorted(options.get('years', []))
            district_count = len(options.get('districts', []))
            latest_year = max(years) if years else None
            recent_years = sorted(years, reverse=True)[:3]
            district_summaries = get_district_climate_summaries_for_year(latest_year)
            latest_daily_district_records = get_latest_daily_district_records()
            latest_monthly_district_records = get_latest_monthly_district_records()
            latest_year_df = load_data_from_db(
                {'year': latest_year},
                columns=[
                    'year',
                    'month',
                    'province',
                    'district',
                    'Rainfall_mm',
                    'Temp_Max_C',
                    'DroughtSeverity',
                    'PopulationAffected'
                ]
            ) if latest_year is not None else pd.DataFrame()

            count_result = db_manager.execute_query(
                "SELECT COUNT(*) AS total_records FROM climate_records"
            ) or []
            total_records = int(count_result[0]['total_records']) if count_result else 0

            yearly_summaries = []
            for year in recent_years:
                yearly_summaries.append({
                    "year": year,
                    "rainfall": get_top_province_metric_for_year(year, 'rainfall'),
                    "temperature": get_top_province_metric_for_year(year, 'temperature'),
                    "drought": get_top_province_metric_for_year(year, 'drought'),
                    "ndvi": get_top_province_metric_for_year(year, 'ndvi')
                })

            update_payload = build_site_summary_updates(
                total_records=total_records,
                provinces=provinces,
                district_count=district_count,
                years=years,
                yearly_summaries=yearly_summaries,
                district_summaries=district_summaries,
                latest_year_df=latest_year_df,
                latest_daily_district_records=latest_daily_district_records,
                latest_monthly_district_records=latest_monthly_district_records
            )

            payload = {
                "total_records": total_records,
                "provinces": provinces,
                "province_count": len(provinces),
                "district_count": district_count,
                "years": years,
                "latest_year": latest_year,
                "yearly_summaries": yearly_summaries,
                "climate_updates": update_payload["climate_updates"],
                "ticker_items": update_payload["ticker_items"],
                "district_updates": update_payload["district_updates"]
            }
            SITE_SUMMARY_CACHE["value"] = payload
            SITE_SUMMARY_CACHE["expires_at"] = now + SITE_SUMMARY_TTL_SECONDS

        latitude = request.args.get('lat', type=float)
        longitude = request.args.get('lon', type=float)

        if latitude is None and longitude is None:
            return success_response(payload)

        if latitude is None or longitude is None:
            logger.warning("Site summary requested with incomplete live weather coordinates.")
            return success_response(payload)

        try:
            weather = get_live_weather(latitude, longitude)
            live_weather_payload = build_live_weather_payload(weather)
            return success_response(
                merge_live_weather_into_site_summary(payload, live_weather_payload)
            )
        except ValueError as error:
            logger.warning(f"Invalid live weather coordinates for site summary: {error}")
        except RuntimeError as error:
            logger.warning(f"Live weather unavailable for site summary: {error}")

        return success_response(payload)
    except Exception as e:
        logger.error(f"Site summary error: {e}", exc_info=True)
        return error_response(str(e), 500)


@api_v1.route('/live-weather', methods=['GET'])
def get_live_weather_updates():
    try:
        latitude = request.args.get('lat', type=float)
        longitude = request.args.get('lon', type=float)

        if latitude is None or longitude is None:
            return error_response(
                "lat and lon query parameters are required for live weather.",
                400
            )

        weather = get_live_weather(latitude, longitude)
        return success_response(build_live_weather_payload(weather))
    except ValueError as error:
        return error_response(str(error), 400)
    except RuntimeError as error:
        logger.warning(f"Live weather unavailable: {error}")
        return error_response(str(error), 503)
    except Exception as error:
        logger.error(f"Live weather error: {error}", exc_info=True)
        return error_response("Unable to load live weather right now.", 500)


@api_v1.route('/projections', methods=['GET'])
def get_projections():
    try:
        filters = build_filters(include_year=False)
        horizon = request.args.get('horizon', default=5, type=int)
        target_year = request.args.get('target_year', type=int)
        scenario = request.args.get('scenario', default='rcp45').strip().lower()
        if scenario not in PROJECTION_SCENARIOS:
            scenario = 'rcp45'

        df = load_data_from_db(filters, columns=[
            'year',
            'province',
            'district',
            'Rainfall_mm',
            'Temp_Max_C',
            'DroughtSeverity',
            'PopulationAffected'
        ])

        if df is None or df.empty:
            return success_response({
                "scope": filters,
                "horizon": max(1, min(horizon or 5, 100)),
                "target_year": target_year,
                "selected_scenario": scenario,
                "scenario_options": PROJECTION_SCENARIOS,
                "series": [],
                "notes": [
                    "No historical records were available for the selected filters."
                ]
            })

        years = sorted([int(year) for year in df['year'].dropna().unique().tolist()]) if 'year' in df.columns else []
        last_year = max(years) if years else None
        if target_year and last_year:
            horizon = max(1, min(int(target_year) - int(last_year), 100))
        else:
            horizon = max(1, min(horizon or 5, 100))
            target_year = (last_year + horizon) if last_year else None

        series = [
            _build_projection_series(df, metric_key, horizon, selected_scenario=scenario)
            for metric_key in ["rainfall", "temperature", "drought", "population"]
        ]

        return success_response({
            "scope": filters,
            "historical_years": years,
            "horizon": horizon,
            "target_year": target_year,
            "selected_scenario": scenario,
            "scenario_options": PROJECTION_SCENARIOS,
            "series": series,
            "notes": [
                "Scenario bands combine observed historical trends with RCP-style planning assumptions for moderate and high emissions pathways.",
                "These are exploratory decision-support estimates, not official meteorological or IPCC model outputs."
            ]
        })
    except Exception as error:
        logger.error(f"Projection endpoint error: {error}", exc_info=True)
        return error_response("Unable to build projections right now.", 500)


@api_v1.route('/docs', methods=['GET']) 
def api_documentation(): 
    docs = {"api_version": "1.0.0", "base_url": "/api/v1", "endpoints": { 
        "GET /health": "Health check", "GET /provinces": "List provinces",
        "GET /districts": "List districts",
        "GET /years": "List years", "GET /overview": "Summary statistics", 
        "GET /rainfall-trend": "Rainfall trend", "GET /temperature-trend": "Temperature trend", 
        "GET /rainfall-distribution": "Rainfall histogram bins and distribution values",
        "GET /drought-trend": "Drought score trend over years or months",
        "GET /drought-indicators-trend": "SPI, SPEI, and PDSI trend over years or months",
        "GET /temperature-distribution": "Temperature histogram bins and distribution values",
        "GET /drought-summary": "Drought summary",
        "GET /ndvi-trend": "NDVI trend",
        "GET /soil-moisture-trend": "Soil moisture trend",
        "GET /impact-trends": "Impact trends",
        "GET /extreme-events": "Extreme climate event signals and monthly event activity",
        "GET /flood-events": "Flood-focused rainfall event analysis and monthly exposure patterns",
        "GET /district-comparison": "Compare multiple districts across several variables and a focus trend",
        "GET /explorer": "Climate Data Explorer filters, trend, summary statistics, and raw table rows",
        "GET /explorer/export": "Download Climate Data Explorer results as CSV",
        "GET /site-summary": "Cached footer and ticker summary payload for shared page chrome, with optional lat/lon to merge live weather",
        "GET /live-weather": "Live current conditions for the viewer latitude and longitude",
        "GET /projections": "RCP-style scenario projections for rainfall, temperature, drought pressure, and affected population",
        "GET /district-summary": "District climate summary for map side panel",
        "GET /map-district-metric": "District-level values for choropleth map shading",
        "GET /population-affected-districts": "Districts with affected population totals",
        "GET /district-monthly-notifications": "Month-by-month notification summaries for the selected scope in a year",
        "GET /rankings/rainfall": "Rainfall rankings", 
        "GET /rankings/temperature": "Temperature rankings", 
        "GET /rankings/drought": "Drought severity rankings", 
        "GET /rankings/population": "Population affected rankings", 
        "GET /rankings/ndvi": "Vegetation health rankings" 
    }} 
    return success_response(docs) 

@api_v1.route('/rankings/<metric>', methods=['GET']) 
def province_rankings(metric): 
    try: 
        year = request.args.get('year', 2024, type=int) 
        scope = request.args.get('scope', 'province').strip().lower()
        group_field = 'district' if scope == 'district' else 'province'
        metric_columns = {
            'rainfall': [group_field, 'year', 'Rainfall_mm'],
            'temperature': [group_field, 'year', 'Temp_Max_C'],
            'drought': [group_field, 'year', 'DroughtSeverity'],
            'population': [group_field, 'year', 'PopulationAffected'],
            'ndvi': [group_field, 'year', 'NDVI']
        }
        df = load_data_from_db(columns=metric_columns.get(metric, [group_field, 'year'])) 
        if df is None or df.empty: 
            return empty_response("No data available") 
        df_year = df[df['year'] == year] 
        if df_year.empty: 
            return empty_response(f"No data found for year {year}") 
        if group_field not in df_year.columns:
            return error_response(f"Grouping field '{group_field}' not found in data", 400)
        rankings = [] 
        
        if metric == 'rainfall': 
            grouped = df_year.groupby(group_field)['Rainfall_mm'].mean().reset_index()
            grouped.columns = ['province', 'value'] 
            grouped = grouped.sort_values('value', ascending=False) 
            metric_name = "Average Rainfall (mm)" 
            
        elif metric == 'temperature': 
            grouped = df_year.groupby(group_field)['Temp_Max_C'].mean().reset_index() 
            grouped.columns = ['province', 'value'] 
            grouped = grouped.sort_values('value', ascending=False) 
            metric_name = "Average Maximum Temperature (C)" 
            
        elif metric == 'drought': 
            severity_order = {'Severe': 3, 'Moderate': 2, 'Mild': 1, 'No Drought': 0} 
            df_year = df_year.copy()
            df_year['drought_score'] = df_year['DroughtSeverity'].map(severity_order).fillna(0) 
            grouped = df_year.groupby(group_field)['drought_score'].mean().reset_index() 
            grouped.columns = ['province', 'value'] 
            grouped = grouped.sort_values('value', ascending=False) 
            metric_name = "Drought Severity Score (0-3)" 
            
        elif metric == 'population': 
            grouped = summarize_population_affected(df_year, [group_field]) 
            grouped.columns = ['province', 'value'] 
            grouped = grouped.sort_values('value', ascending=False) 
            metric_name = "Total Population Affected" 
            
        elif metric == 'ndvi': 
            grouped = df_year.groupby(group_field)['NDVI'].mean().reset_index() 
            grouped.columns = ['province', 'value'] 
            grouped = grouped.sort_values('value', ascending=False) 
            metric_name = "Average NDVI (Vegetation Health)" 
            
        else: 
            return error_response("Invalid metric. Choose from: rainfall, temperature, drought, population, ndvi", 400) 
        
        for idx, row in grouped.iterrows(): 
            rankings.append({"rank": len(rankings) + 1, "province": row['province'], "value": round(row['value'], 2)}) 
        return success_response({
            "metric": metric,
            "metric_name": metric_name,
            "year": year,
            "scope": scope,
            "total_items": len(rankings),
            "total_provinces": len(rankings),
            "rankings": rankings
        }) 
    except Exception as e: 
        return error_response(str(e), 500)
