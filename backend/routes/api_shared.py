import pandas as pd
from flask import Blueprint, request

from backend.utils.database import db_manager
from backend.utils.monthly import (
    apply_monthly_chart_metadata,
    build_empty_monthly_chart_payload,
    expand_monthly_periods,
    prepare_monthly_frame,
    use_monthly_periods,
)


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

    month = request.args.get('month', type=int)
    if month and 1 <= month <= 12:
        filters['month'] = month

    return filters


DROUGHT_SCORE_MAP = {
    "No Drought": 0,
    "Mild": 1,
    "Moderate": 2,
    "Severe": 3,
    "Extreme": 4
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
    if value is None:
        return None
    try:
        return round(float(value), decimals)
    except (TypeError, ValueError):
        return None


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


def build_empty_monthly_series_response(value_keys, extra=None):
    payload = build_empty_monthly_chart_payload(value_keys)
    if extra:
        payload.update(extra)
    return payload


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
        grouped = expand_monthly_periods(grouped, period_col)

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
            "DroughtSeverity": row.get('DroughtSeverity')
        })
    return rows


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


def build_metric_values(df, metric):
    if df is None or df.empty or 'district' not in df.columns:
        return {}

    metric = (metric or '').strip().lower()

    if metric == 'rainfall':
        grouped = df.groupby('district')['Rainfall_mm'].mean()
    elif metric == 'temperature':
        grouped = df.groupby('district')['Temp_Max_C'].mean()
    elif metric == 'drought':
        work = df.copy()
        work['drought_score'] = work['DroughtSeverity'].map(DROUGHT_SCORE_MAP).fillna(0)
        grouped = work.groupby('district')['drought_score'].mean()
    else:
        raise ValueError("Invalid metric")

    return {
        normalize_name(district): round(float(value), 3)
        for district, value in grouped.dropna().items()
        if str(district).strip()
    }
