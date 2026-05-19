# utils/aggregations.py
import logging

import numpy as np
import pandas as pd

from utils.monthly import (
    MONTH_LABELS,
    apply_monthly_chart_metadata,
    build_monthly_period_frame as shared_build_monthly_period_frame,
    build_monthly_period_metadata as shared_build_monthly_period_metadata,
    expand_monthly_periods as shared_expand_monthly_periods,
    extract_available_months as shared_extract_available_months,
    month_label_from_number,
    normalize_month_values,
    prepare_monthly_frame,
    use_monthly_periods as shared_use_monthly_periods,
)


def safe_float(value, decimals=2):
    if value is None or pd.isna(value):
        return None
    try:
        return round(float(value), decimals)
    except (ValueError, TypeError):
        return None


logger = logging.getLogger(__name__)
DROUGHT_SCORE_MAP = {
    "No Drought": 0,
    "Mild": 1,
    "Moderate": 2,
    "Severe": 3
}

def safe_round(value, decimals=2):
    if value is None or pd.isna(value):
        return None
    try:
        return round(float(value), decimals)
    except (ValueError, TypeError):
        return None

def safe_int(value):
    if value is None or pd.isna(value):
        return None
    try:
        return int(round(float(value)))
    except (ValueError, TypeError):
        return None

def use_monthly_periods(df):
    return shared_use_monthly_periods(df)

def build_period_labels(values, monthly=False):
    if monthly:
        return [month_label_from_number(val) for val in values]
    return [str(val) for val in values]

def normalize_period_values(values, monthly=False):
    if monthly:
        return normalize_month_values(values)
    return pd.to_numeric(values, errors="coerce")

def build_monthly_period_frame(period_col="month"):
    return shared_build_monthly_period_frame(period_col)

def extract_available_months(frame, period_col="month"):
    return shared_extract_available_months(frame, period_col)

def build_monthly_period_metadata(frame, period_col="month"):
    return shared_build_monthly_period_metadata(frame, period_col)

def prepare_period_frame(df, period_col="year", monthly=False):
    if monthly:
        return prepare_monthly_frame(df, period_col)

    if df is None or df.empty or period_col not in df.columns:
        columns = list(df.columns) if isinstance(df, pd.DataFrame) else [period_col]
        return pd.DataFrame(columns=columns)

    work = df.copy()
    work[period_col] = normalize_period_values(work[period_col], monthly=monthly)
    work = work.dropna(subset=[period_col]).copy()
    if work.empty:
        return work

    numeric_values = work[period_col]
    if monthly or (numeric_values % 1 == 0).all():
        work[period_col] = numeric_values.astype(int)
    return work

def finalize_period_payload(payload, source_frame, monthly=False, period_col="month"):
    if monthly:
        return apply_monthly_chart_metadata(payload, source_frame, period_col)
    payload["labels"] = payload.get("years", [])
    return payload

def expand_monthly_periods(grouped, period_col="month"):
    return shared_expand_monthly_periods(grouped, period_col)


def summarize_population_affected(df, group_fields=None, location_field="district"):
    """Use per-location maxima to avoid over-counting repeated daily records."""
    if df is None or df.empty or "PopulationAffected" not in df.columns:
        if group_fields:
            return pd.DataFrame(columns=[*group_fields, "PopulationAffected"])
        return 0

    work = df.copy()
    work["PopulationAffected"] = pd.to_numeric(work["PopulationAffected"], errors="coerce").fillna(0)

    grouping = list(group_fields or [])
    if location_field and location_field in work.columns and location_field not in grouping:
        work = work[work[location_field].notna() & work[location_field].astype(str).str.strip().ne("")]
        grouping_with_location = [*grouping, location_field]
        maxima = (
            work.groupby(grouping_with_location, dropna=False)["PopulationAffected"]
            .max()
            .reset_index()
        )
        if grouping:
            return (
                maxima.groupby(grouping, dropna=False)["PopulationAffected"]
                .sum()
                .reset_index()
                .sort_values(grouping)
            )
        return int(round(float(maxima["PopulationAffected"].sum()))) if not maxima.empty else 0

    if grouping:
        grouped = (
            work.groupby(grouping, dropna=False)["PopulationAffected"]
            .max()
            .reset_index()
            .sort_values(grouping)
        )
        return grouped

    return int(round(float(work["PopulationAffected"].max()))) if not work.empty else 0

def get_overview(df):
    """Get overview statistics"""
    if df is None or df.empty:
        return {
            "total_records": 0,
            "total_provinces": 0,
            "total_districts": 0,
            "avg_rainfall": 0,
            "avg_temp_max": 0,
            "avg_temp_min": 0,
            "avg_humidity": 0,
            "avg_ndvi": 0,
            "avg_soil_moisture": 0
        }
    
    result = {
        "total_records": int(len(df)),
        "total_provinces": int(df["province"].nunique()) if "province" in df.columns else 0,
        "total_districts": int(df["district"].nunique()) if "district" in df.columns else 0,
    }
    
    if "Rainfall_mm" in df.columns:
        result["avg_rainfall"] = safe_round(df["Rainfall_mm"].mean())
        result["max_rainfall"] = safe_round(df["Rainfall_mm"].max())
        result["min_rainfall"] = safe_round(df["Rainfall_mm"].min())
    
    if "Temp_Max_C" in df.columns:
        result["avg_temp_max"] = safe_round(df["Temp_Max_C"].mean())
    
    if "Temp_Min_C" in df.columns:
        result["avg_temp_min"] = safe_round(df["Temp_Min_C"].mean())
    
    if "Humidity_pct" in df.columns:
        result["avg_humidity"] = safe_round(df["Humidity_pct"].mean())
    
    if "NDVI" in df.columns:
        result["avg_ndvi"] = safe_round(df["NDVI"].mean(), 3)
    
    if "SoilMoisture_pct" in df.columns:
        result["avg_soil_moisture"] = safe_round(df["SoilMoisture_pct"].mean())
    
    return result

def rainfall_trend(df):
    """Get rainfall trend by year"""
    if df is None or df.empty:
        return {"years": [], "avg_rainfall": [], "min_rainfall": [], "max_rainfall": []}
    
    if "Rainfall_mm" not in df.columns or "year" not in df.columns:
        logger.warning(f"Missing columns. Rainfall_mm: {'Rainfall_mm' in df.columns}, year: {'year' in df.columns}")
        return {"years": [], "avg_rainfall": [], "min_rainfall": [], "max_rainfall": []}
    
    try:
        monthly = use_monthly_periods(df)
        period_col = "month" if monthly else "year"
        work = prepare_period_frame(df, period_col, monthly)
        grouped = work.groupby(period_col)["Rainfall_mm"].agg(['mean', 'min', 'max']).reset_index() if not work.empty else pd.DataFrame(columns=[period_col, "mean", "min", "max"])
        grouped = grouped.sort_values(period_col)
        if monthly:
            grouped = expand_monthly_periods(grouped, period_col)

        payload = {
            "years": build_period_labels(grouped[period_col].tolist(), monthly),
            "avg_rainfall": [safe_round(val) for val in grouped['mean'].tolist()],
            "min_rainfall": [safe_round(val) for val in grouped['min'].tolist()],
            "max_rainfall": [safe_round(val) for val in grouped['max'].tolist()],
            "period_type": "month" if monthly else "year"
        }
        coverage_frame = work.dropna(subset=["Rainfall_mm"]) if "Rainfall_mm" in work.columns else work.iloc[0:0]
        return finalize_period_payload(payload, coverage_frame, monthly, period_col)
    except Exception as e:
        logger.error(f"Error in rainfall_trend: {e}")
        return {"years": [], "avg_rainfall": [], "min_rainfall": [], "max_rainfall": []}

def temperature_trend(df):
    """Get temperature trends by year"""
    if df is None or df.empty:
        return {"years": [], "avg_max_temp": [], "avg_min_temp": []}
    
    if "year" not in df.columns:
        return {"years": [], "avg_max_temp": [], "avg_min_temp": []}
    
    result = {"years": []}
    monthly = use_monthly_periods(df)
    period_col = "month" if monthly else "year"
    work = prepare_period_frame(df, period_col, monthly)
    
    if "Temp_Max_C" in work.columns:
        grouped = work.groupby(period_col)["Temp_Max_C"].mean().reset_index() if not work.empty else pd.DataFrame(columns=[period_col, "Temp_Max_C"])
        grouped = grouped.sort_values(period_col)
        if monthly:
            grouped = expand_monthly_periods(grouped, period_col)
        result["years"] = build_period_labels(grouped[period_col].tolist(), monthly)
        result["avg_max_temp"] = [safe_round(val) for val in grouped["Temp_Max_C"].tolist()]
    
    if "Temp_Min_C" in work.columns:
        grouped = work.groupby(period_col)["Temp_Min_C"].mean().reset_index() if not work.empty else pd.DataFrame(columns=[period_col, "Temp_Min_C"])
        grouped = grouped.sort_values(period_col)
        if monthly:
            grouped = expand_monthly_periods(grouped, period_col)
        if not result["years"]:
            result["years"] = build_period_labels(grouped[period_col].tolist(), monthly)
        result["avg_min_temp"] = [safe_round(val) for val in grouped["Temp_Min_C"].tolist()]
    
    result["period_type"] = "month" if monthly else "year"
    coverage_columns = [column for column in ["Temp_Max_C", "Temp_Min_C"] if column in work.columns]
    coverage_frame = work.dropna(subset=coverage_columns, how="all") if coverage_columns else work.iloc[0:0]
    return finalize_period_payload(result, coverage_frame, monthly, period_col)

def drought_summary(df):
    """Get drought severity distribution"""
    if df is None or df.empty or "DroughtSeverity" not in df.columns:
        return []
    
    drought_counts = df["DroughtSeverity"].value_counts().reset_index()
    drought_counts.columns = ["severity", "count"]
    
    total = drought_counts["count"].sum()
    drought_counts["percentage"] = (drought_counts["count"] / total * 100).round(1)
    
    return drought_counts.to_dict(orient="records")

def drought_trend(df):
    """Get drought score trend by year or month"""
    if df is None or df.empty or "DroughtSeverity" not in df.columns:
        return {"years": [], "avg_drought_score": [], "severe_pct": [], "moderate_pct": []}

    if "year" not in df.columns:
        return {"years": [], "avg_drought_score": [], "severe_pct": [], "moderate_pct": []}

    monthly = use_monthly_periods(df)
    period_col = "month" if monthly else "year"

    work = prepare_period_frame(df[[period_col, "DroughtSeverity"]], period_col, monthly)
    work = work.dropna(subset=["DroughtSeverity"]).copy()
    if work.empty and not monthly:
        return {"years": [], "avg_drought_score": [], "severe_pct": [], "moderate_pct": []}

    work["drought_score"] = work["DroughtSeverity"].map(DROUGHT_SCORE_MAP).fillna(0)
    grouped = work.groupby(period_col).agg(
        avg_drought_score=("drought_score", "mean"),
        severe_pct=("DroughtSeverity", lambda values: (values.astype(str).str.lower().eq("severe").mean() * 100)),
        moderate_pct=("DroughtSeverity", lambda values: (values.astype(str).str.lower().eq("moderate").mean() * 100))
    ).reset_index() if not work.empty else pd.DataFrame(columns=[period_col, "avg_drought_score", "severe_pct", "moderate_pct"])
    grouped = grouped.sort_values(period_col)
    if monthly:
        grouped = expand_monthly_periods(grouped, period_col)

    payload = {
        "years": build_period_labels(grouped[period_col].tolist(), monthly),
        "avg_drought_score": [safe_round(val) for val in grouped["avg_drought_score"].tolist()],
        "severe_pct": [safe_round(val, 1) for val in grouped["severe_pct"].tolist()],
        "moderate_pct": [safe_round(val, 1) for val in grouped["moderate_pct"].tolist()],
        "period_type": "month" if monthly else "year"
    }
    return finalize_period_payload(payload, work, monthly, period_col)

def drought_indicator_trends(df):
    """Get SPI, SPEI, and PDSI trends by year or month"""
    if df is None or df.empty:
        return {"years": [], "avg_spi": [], "avg_spei": [], "avg_pdsi": []}

    if "year" not in df.columns:
        return {"years": [], "avg_spi": [], "avg_spei": [], "avg_pdsi": []}

    monthly = use_monthly_periods(df)
    period_col = "month" if monthly else "year"
    work = prepare_period_frame(df, period_col, monthly)
    result = {"years": []}

    if "SPI" in work.columns:
        grouped = work.groupby(period_col)["SPI"].mean().reset_index() if not work.empty else pd.DataFrame(columns=[period_col, "SPI"])
        grouped = grouped.sort_values(period_col)
        if monthly:
            grouped = expand_monthly_periods(grouped, period_col)
        result["years"] = build_period_labels(grouped[period_col].tolist(), monthly)
        result["avg_spi"] = [safe_round(val, 2) for val in grouped["SPI"].tolist()]

    if "SPEI" in work.columns:
        grouped = work.groupby(period_col)["SPEI"].mean().reset_index() if not work.empty else pd.DataFrame(columns=[period_col, "SPEI"])
        grouped = grouped.sort_values(period_col)
        if monthly:
            grouped = expand_monthly_periods(grouped, period_col)
        if not result["years"]:
            result["years"] = build_period_labels(grouped[period_col].tolist(), monthly)
        result["avg_spei"] = [safe_round(val, 2) for val in grouped["SPEI"].tolist()]

    if "PDSI" in work.columns:
        grouped = work.groupby(period_col)["PDSI"].mean().reset_index() if not work.empty else pd.DataFrame(columns=[period_col, "PDSI"])
        grouped = grouped.sort_values(period_col)
        if monthly:
            grouped = expand_monthly_periods(grouped, period_col)
        if not result["years"]:
            result["years"] = build_period_labels(grouped[period_col].tolist(), monthly)
        result["avg_pdsi"] = [safe_round(val, 2) for val in grouped["PDSI"].tolist()]

    result["period_type"] = "month" if monthly else "year"
    coverage_columns = [column for column in ["SPI", "SPEI", "PDSI"] if column in work.columns]
    coverage_frame = work.dropna(subset=coverage_columns, how="all") if coverage_columns else work.iloc[0:0]
    return finalize_period_payload(result, coverage_frame, monthly, period_col)

def ndvi_trend(df):
    """Get NDVI trend by year"""
    if df is None or df.empty or "NDVI" not in df.columns:
        return {"years": [], "avg_ndvi": []}
    
    if "year" not in df.columns:
        return {"years": [], "avg_ndvi": []}
    
    monthly = use_monthly_periods(df)
    period_col = "month" if monthly else "year"
    work = prepare_period_frame(df, period_col, monthly)
    grouped = work.groupby(period_col)["NDVI"].mean().reset_index() if not work.empty else pd.DataFrame(columns=[period_col, "NDVI"])
    grouped = grouped.sort_values(period_col)
    if monthly:
        grouped = expand_monthly_periods(grouped, period_col)
    
    payload = {
        "years": build_period_labels(grouped[period_col].tolist(), monthly),
        "avg_ndvi": [safe_round(val, 3) for val in grouped["NDVI"].tolist()],
        "period_type": "month" if monthly else "year"
    }
    coverage_frame = work.dropna(subset=["NDVI"]) if "NDVI" in work.columns else work.iloc[0:0]
    return finalize_period_payload(payload, coverage_frame, monthly, period_col)

def soil_moisture_trend(df):
    """Get soil moisture trend by year"""
    if df is None or df.empty or "SoilMoisture_pct" not in df.columns:
        return {"years": [], "avg_soil_moisture": []}
    
    if "year" not in df.columns:
        return {"years": [], "avg_soil_moisture": []}
    
    monthly = use_monthly_periods(df)
    period_col = "month" if monthly else "year"
    work = prepare_period_frame(df, period_col, monthly)
    grouped = work.groupby(period_col)["SoilMoisture_pct"].mean().reset_index() if not work.empty else pd.DataFrame(columns=[period_col, "SoilMoisture_pct"])
    grouped = grouped.sort_values(period_col)
    if monthly:
        grouped = expand_monthly_periods(grouped, period_col)
    
    payload = {
        "years": build_period_labels(grouped[period_col].tolist(), monthly),
        "avg_soil_moisture": [safe_round(val) for val in grouped["SoilMoisture_pct"].tolist()],
        "period_type": "month" if monthly else "year"
    }
    coverage_frame = work.dropna(subset=["SoilMoisture_pct"]) if "SoilMoisture_pct" in work.columns else work.iloc[0:0]
    return finalize_period_payload(payload, coverage_frame, monthly, period_col)

def impact_trends(df):
    """Get impact variables trends by year"""
    if df is None or df.empty:
        return {
            "years": [],
            "crop_yield": [],
            "population_affected": [],
            "hydropower_mw": [],
            "lake_kariba_level": [],
            "food_price_zmw": []
        }
    
    if "year" not in df.columns:
        return {"years": [], "crop_yield": [], "population_affected": []}
    
    result = {"years": []}
    monthly = use_monthly_periods(df)
    period_col = "month" if monthly else "year"
    work = prepare_period_frame(df, period_col, monthly)
    
    if "CropYield_kg_ha" in work.columns:
        grouped = work.groupby(period_col)["CropYield_kg_ha"].mean().reset_index() if not work.empty else pd.DataFrame(columns=[period_col, "CropYield_kg_ha"])
        grouped = grouped.sort_values(period_col)
        if monthly:
            grouped = expand_monthly_periods(grouped, period_col)
        result["years"] = build_period_labels(grouped[period_col].tolist(), monthly)
        result["crop_yield"] = [safe_round(val) for val in grouped["CropYield_kg_ha"].tolist()]
    
    if "PopulationAffected" in work.columns:
        grouped = summarize_population_affected(work, [period_col])
        if monthly and grouped is not None:
            grouped = expand_monthly_periods(grouped, period_col)
        if not result["years"]:
            result["years"] = build_period_labels(grouped[period_col].tolist(), monthly)
        result["population_affected"] = [safe_int(val) for val in grouped["PopulationAffected"].tolist()]
    
    if "Hydropower_MW" in work.columns:
        grouped = work.groupby(period_col)["Hydropower_MW"].mean().reset_index() if not work.empty else pd.DataFrame(columns=[period_col, "Hydropower_MW"])
        grouped = grouped.sort_values(period_col)
        if monthly:
            grouped = expand_monthly_periods(grouped, period_col)
        if not result["years"]:
            result["years"] = build_period_labels(grouped[period_col].tolist(), monthly)
        result["hydropower_mw"] = [safe_round(val) for val in grouped["Hydropower_MW"].tolist()]
    
    if "LakeKariba_Level_m" in work.columns:
        grouped = work.groupby(period_col)["LakeKariba_Level_m"].mean().reset_index() if not work.empty else pd.DataFrame(columns=[period_col, "LakeKariba_Level_m"])
        grouped = grouped.sort_values(period_col)
        if monthly:
            grouped = expand_monthly_periods(grouped, period_col)
        if not result["years"]:
            result["years"] = build_period_labels(grouped[period_col].tolist(), monthly)
        result["lake_kariba_level"] = [safe_round(val) for val in grouped["LakeKariba_Level_m"].tolist()]
    
    if "FoodPrice_ZMW" in work.columns:
        grouped = work.groupby(period_col)["FoodPrice_ZMW"].mean().reset_index() if not work.empty else pd.DataFrame(columns=[period_col, "FoodPrice_ZMW"])
        grouped = grouped.sort_values(period_col)
        if monthly:
            grouped = expand_monthly_periods(grouped, period_col)
        if not result["years"]:
            result["years"] = build_period_labels(grouped[period_col].tolist(), monthly)
        result["food_price_zmw"] = [safe_round(val) for val in grouped["FoodPrice_ZMW"].tolist()]
    
    result["period_type"] = "month" if monthly else "year"
    coverage_columns = [column for column in ["CropYield_kg_ha", "PopulationAffected", "Hydropower_MW", "LakeKariba_Level_m", "FoodPrice_ZMW"] if column in work.columns]
    coverage_frame = work.dropna(subset=coverage_columns, how="all") if coverage_columns else work.iloc[0:0]
    return finalize_period_payload(result, coverage_frame, monthly, period_col)

def impact_driver_breakdown(df):
    """Attribute affected population to the strongest climate stressor in each record."""
    empty_result = {
        "total_population_affected": 0,
        "total_records_with_population": 0,
        "variables": [],
        "method": "Population affected is assigned to the climate variable with the strongest normalized stress signal in each record."
    }

    if df is None or df.empty or "PopulationAffected" not in df.columns:
        return empty_result

    work = df.copy()
    work["PopulationAffected"] = pd.to_numeric(work["PopulationAffected"], errors="coerce").fillna(0)
    work = work[work["PopulationAffected"] > 0].copy()
    if work.empty:
        return empty_result

    configs = {
        "rainfall_deficit": {
            "label": "Rainfall deficit",
            "column": "Rainfall_mm",
            "higher_is_worse": False
        },
        "high_temperature": {
            "label": "High temperature",
            "column": "Temp_Max_C",
            "higher_is_worse": True
        },
        "soil_moisture_deficit": {
            "label": "Low soil moisture",
            "column": "SoilMoisture_pct",
            "higher_is_worse": False
        },
        "vegetation_stress": {
            "label": "Low NDVI",
            "column": "NDVI",
            "higher_is_worse": False
        }
    }

    available_scores = []
    for key, config in configs.items():
        column = config["column"]
        if column not in work.columns:
            continue

        series = pd.to_numeric(work[column], errors="coerce")
        valid = series.dropna()
        if valid.empty:
            continue

        low = float(valid.min())
        high = float(valid.max())
        if np.isclose(high, low):
            normalized = pd.Series(0.0, index=work.index)
        elif config["higher_is_worse"]:
            normalized = ((series - low) / (high - low)).clip(lower=0, upper=1)
        else:
            normalized = ((high - series) / (high - low)).clip(lower=0, upper=1)

        work[f"score_{key}"] = normalized.fillna(0)
        available_scores.append((key, config["label"]))

    if "DroughtSeverity" in work.columns:
        drought_scores = work["DroughtSeverity"].map(DROUGHT_SCORE_MAP).fillna(0).astype(float) / 3.0
        work["score_drought_severity"] = drought_scores.clip(lower=0, upper=1)
        available_scores.append(("drought_severity", "Drought severity"))

    if not available_scores:
        return empty_result

    score_columns = [f"score_{key}" for key, _ in available_scores]
    label_lookup = {key: label for key, label in available_scores}

    # Attribute each record's affected population to the dominant stressor.
    work["dominant_driver_key"] = work[score_columns].idxmax(axis=1).str.replace("score_", "", regex=False)
    work["dominant_driver_score"] = work[score_columns].max(axis=1)
    work = work[work["dominant_driver_score"] > 0].copy()
    if work.empty:
        return empty_result

    grouped = (
        work.groupby("dominant_driver_key", as_index=False)
        .agg(
            people_affected=("PopulationAffected", "sum"),
            record_count=("PopulationAffected", "size"),
            average_driver_score=("dominant_driver_score", "mean")
        )
        .sort_values(["people_affected", "dominant_driver_key"], ascending=[False, True])
    )

    total_population = float(grouped["people_affected"].sum())
    variables = []
    for _, row in grouped.iterrows():
        people_affected = int(round(float(row["people_affected"])))
        percentage = round((people_affected / total_population) * 100, 1) if total_population else 0.0
        variables.append({
            "variable_key": row["dominant_driver_key"],
            "variable_label": label_lookup.get(row["dominant_driver_key"], row["dominant_driver_key"]),
            "people_affected": people_affected,
            "percentage": percentage,
            "record_count": int(row["record_count"]),
            "average_driver_score": safe_round(row["average_driver_score"], 3)
        })

    return {
        "total_population_affected": int(round(total_population)),
        "total_records_with_population": int(len(work)),
        "variables": variables,
        "method": empty_result["method"]
    }
