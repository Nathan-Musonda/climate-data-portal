import math
from typing import Mapping

import numpy as np
import pandas as pd


MONTH_SEQUENCE = list(range(1, 13))
MONTH_LABELS = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr",
    5: "May", 6: "Jun", 7: "Jul", 8: "Aug",
    9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec"
}
CANONICAL_MONTH_LABELS = [MONTH_LABELS[month] for month in MONTH_SEQUENCE]


def coerce_month_number(value):
    if value is None or pd.isna(value):
        return None

    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return None

    if not math.isfinite(numeric_value) or not numeric_value.is_integer():
        return None

    month_number = int(numeric_value)
    return month_number if 1 <= month_number <= 12 else None


def month_label_from_number(value):
    month_number = coerce_month_number(value)
    if month_number is None:
        return str(value)
    return MONTH_LABELS[month_number]


def normalize_month_values(values):
    series = pd.to_numeric(values, errors="coerce")
    return series.where(series.between(1, 12))


def use_monthly_periods(df, year_col="year", month_col="month"):
    if df is None or df.empty or month_col not in df.columns or year_col not in df.columns:
        return False

    years = pd.to_numeric(df[year_col], errors="coerce").dropna()
    if years.empty:
        return False

    return years.astype(int).nunique() == 1


def build_monthly_period_frame(period_col="month"):
    return pd.DataFrame({period_col: MONTH_SEQUENCE})


def prepare_monthly_frame(df, period_col="month"):
    if df is None or df.empty or period_col not in df.columns:
        columns = list(df.columns) if isinstance(df, pd.DataFrame) else [period_col]
        return pd.DataFrame(columns=columns)

    work = df.copy()
    work[period_col] = normalize_month_values(work[period_col])
    work = work.dropna(subset=[period_col]).copy()
    if work.empty:
        return work

    work[period_col] = work[period_col].astype(int)
    return work.sort_values(period_col)


def extract_available_months(frame, period_col="month"):
    if frame is None or frame.empty or period_col not in frame.columns:
        return []

    month_values = normalize_month_values(frame[period_col]).dropna()
    if month_values.empty:
        return []

    return sorted(month_values.astype(int).unique().tolist())


def build_monthly_period_metadata(frame, period_col="month"):
    available_months = extract_available_months(frame, period_col)
    missing_months = [month for month in MONTH_SEQUENCE if month not in available_months]
    return {
        "labels": CANONICAL_MONTH_LABELS.copy(),
        "month_numbers": MONTH_SEQUENCE.copy(),
        "month_labels": CANONICAL_MONTH_LABELS.copy(),
        "available_months": available_months,
        "available_month_labels": [MONTH_LABELS[month] for month in available_months],
        "missing_months": missing_months,
        "missing_month_labels": [MONTH_LABELS[month] for month in missing_months],
        "observed_month_count": len(available_months),
        "is_complete_period": len(available_months) == len(MONTH_SEQUENCE)
    }


def expand_monthly_periods(grouped, period_col="month"):
    month_frame = build_monthly_period_frame(period_col)
    if grouped is None:
        return month_frame
    if grouped.empty:
        if period_col in grouped.columns:
            return month_frame.merge(grouped, on=period_col, how="left").sort_values(period_col)
        return month_frame
    if period_col not in grouped.columns:
        return grouped

    work = prepare_monthly_frame(grouped, period_col)
    if work.empty:
        return month_frame.merge(grouped.iloc[0:0], on=period_col, how="left").sort_values(period_col)

    return month_frame.merge(work, on=period_col, how="left").sort_values(period_col)


def _to_records(rows):
    if rows is None:
        return []
    if isinstance(rows, pd.DataFrame):
        return rows.to_dict(orient="records")
    return [dict(row) for row in rows]


def _to_json_safe(value):
    if value is None:
        return None
    if pd.isna(value):
        return None
    if isinstance(value, np.generic):
        return value.item()
    return value


def normalize_monthly_rows(rows, value_keys, fill_values=None, month_key="month"):
    keys = list(value_keys or [])
    fill_map = fill_values.copy() if isinstance(fill_values, Mapping) else {
        key: fill_values for key in keys
    }

    records = _to_records(rows)
    observed_rows = {}
    for record in records:
        month_number = coerce_month_number(record.get(month_key))
        if month_number is None:
            continue

        observed_rows[month_number] = {
            key: _to_json_safe(value)
            for key, value in record.items()
            if key != month_key and key != "label"
        }

    normalized_rows = []
    for month_number in MONTH_SEQUENCE:
        source = observed_rows.get(month_number, {})
        row = {
            month_key: month_number,
            "label": MONTH_LABELS[month_number]
        }

        for key, value in source.items():
            row[key] = value

        for key in keys:
            value = source.get(key)
            if value is None:
                value = fill_map.get(key)
            row[key] = _to_json_safe(value)

        normalized_rows.append(row)

    metadata = build_monthly_period_metadata(pd.DataFrame({month_key: sorted(observed_rows.keys())}), month_key)
    metadata["rows"] = normalized_rows
    return metadata


def build_monthly_series_payload(rows, value_keys, fill_values=None, month_key="month"):
    keys = list(value_keys or [])
    normalized = normalize_monthly_rows(rows, keys, fill_values=fill_values, month_key=month_key)
    payload = {key: value for key, value in normalized.items() if key != "rows"}

    for key in keys:
        payload[key] = [row.get(key) for row in normalized["rows"]]

    return payload


def build_empty_monthly_payload(value_keys, fill_values=None, month_key="month"):
    return build_monthly_series_payload([], value_keys, fill_values=fill_values, month_key=month_key)


def apply_monthly_chart_metadata(payload=None, frame=None, period_col="month", years_key="years"):
    metadata = build_monthly_period_metadata(frame, period_col)
    canonical_labels = metadata["labels"].copy()
    chart_payload = dict(payload or {})
    chart_payload["period_type"] = "month"
    chart_payload["labels"] = canonical_labels
    chart_payload[years_key] = canonical_labels.copy()
    chart_payload.update(metadata)
    return chart_payload


def build_monthly_chart_payload(rows, value_keys, fill_values=None, month_key="month"):
    keys = list(value_keys or [])
    normalized = normalize_monthly_rows(rows, keys, fill_values=fill_values, month_key=month_key)
    observed_frame = pd.DataFrame({month_key: normalized["available_months"]})
    payload = {
        key: [row.get(key) for row in normalized["rows"]]
        for key in keys
    }
    return apply_monthly_chart_metadata(payload, observed_frame, month_key), normalized["rows"]


def build_empty_monthly_chart_payload(value_keys, fill_values=None, month_key="month"):
    payload, _ = build_monthly_chart_payload([], value_keys, fill_values=fill_values, month_key=month_key)
    return payload
