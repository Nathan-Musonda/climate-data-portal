import logging
import calendar

import pandas as pd
from flask import request

from utils.database import db_manager
from utils.data_loader import load_data_from_db
from utils.live_weather import get_live_weather
from utils.responses import error_response, success_response

from .api_shared import build_filters
from .api_v1 import (
    PROJECTION_SCENARIOS,
    _build_projection_series,
    build_live_weather_payload,
    build_missing_month_notification_item,
    build_monthly_notification_items,
)


logger = logging.getLogger(__name__)


def _safe_round(value, decimals=1):
    if value is None or pd.isna(value):
        return None
    try:
        return round(float(value), decimals)
    except (TypeError, ValueError):
        return None


def _month_name(month_number):
    try:
        number = int(month_number)
    except (TypeError, ValueError):
        return None
    if number < 1 or number > 12:
        return None
    return calendar.month_name[number]


def _average_temperature_frame(df):
    work = df.copy()
    if "Temp_Max_C" in work.columns and "Temp_Min_C" in work.columns:
        work["AvgTemp_C"] = work[["Temp_Max_C", "Temp_Min_C"]].mean(axis=1)
    elif "Temp_Max_C" in work.columns:
        work["AvgTemp_C"] = work["Temp_Max_C"]
    else:
        work["AvgTemp_C"] = pd.NA
    return work


def _record_from_row(row):
    if row is None:
        return None
    return {
        "date": str(row.get("date")) if row.get("date") is not None else None,
        "year": int(row.get("year")) if pd.notna(row.get("year")) else None,
        "month": int(row.get("month")) if pd.notna(row.get("month")) else None,
        "month_name": _month_name(row.get("month")),
        "province": row.get("province"),
        "district": row.get("district"),
        "rainfall": _safe_round(row.get("Rainfall_mm"), 1),
        "temp_max": _safe_round(row.get("Temp_Max_C"), 1),
        "temp_min": _safe_round(row.get("Temp_Min_C"), 1),
        "humidity": _safe_round(row.get("Humidity_pct"), 1),
        "wind_speed": _safe_round(row.get("WindSpeed_mps"), 1),
        "drought_severity": row.get("DroughtSeverity")
    }


def _top_record(df, column, ascending=False):
    if df is None or df.empty or column not in df.columns:
        return None
    work = df.dropna(subset=[column])
    if work.empty:
        return None
    row = work.sort_values(column, ascending=ascending).iloc[0]
    record = _record_from_row(row)
    record["value"] = _safe_round(row.get(column), 1)
    return record


def _build_series(grouped, label_col, value_cols):
    if grouped is None or grouped.empty:
        return {"labels": [], **{key: [] for key in value_cols}}
    payload = {"labels": grouped[label_col].tolist()}
    for key, column in value_cols.items():
        payload[key] = [_safe_round(value, 2) for value in grouped[column].tolist()]
    return payload


def register_extra_routes(api_v1):
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
        except Exception as error:
            return error_response(str(error), 500)

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
                'DroughtSeverity'
            ])

            if df is None or df.empty:
                empty_items = [
                    build_missing_month_notification_item(
                        month,
                        selected_year,
                        district=selected_district,
                        province=selected_province
                    )
                    for month in range(1, 13)
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

            district_count = 0
            if 'district' in df.columns:
                district_count = int(
                    df['district']
                    .dropna()
                    .astype(str)
                    .str.strip()
                    .replace('', pd.NA)
                    .dropna()
                    .nunique()
                )
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
        except Exception as error:
            logger.error(f"District monthly notifications error: {error}", exc_info=True)
            return error_response(str(error), 500)

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

    @api_v1.route('/climate-analysis', methods=['GET'])
    def get_climate_analysis():
        try:
            filters = {}
            province = request.args.get('province')
            district = request.args.get('district')
            year = request.args.get('year', type=int)
            month = request.args.get('month', type=int)

            if province and province.lower() != 'all':
                filters['province'] = province
            if district and district.lower() != 'all':
                filters['district'] = district
            if year:
                filters['year'] = year
            if month:
                filters['month'] = month

            df = load_data_from_db(filters, columns=[
                'date',
                'year',
                'month',
                'province',
                'district',
                'Rainfall_mm',
                'Temp_Max_C',
                'Temp_Min_C',
                'Humidity_pct',
                'WindSpeed_mps',
                'DroughtSeverity'
            ])

            if df is None or df.empty:
                return success_response({
                    "scope": filters,
                    "summary": {},
                    "yearly": {"labels": [], "avg_temp": [], "rainfall": [], "humidity": [], "wind_speed": []},
                    "monthly": [],
                    "distribution": [],
                    "extremes": {},
                    "records": [],
                    "station": {
                        "name": "Zambia climate observation dataset",
                        "province": filters.get("province") or "All provinces",
                        "region": filters.get("district") or "All districts",
                        "elevation": "Not specified",
                        "coordinates": "Not specified"
                    },
                    "insights": ["No climate records matched the selected filters."]
                })

            df = _average_temperature_frame(df)
            available_years = sorted([int(item) for item in df["year"].dropna().unique().tolist()]) if "year" in df.columns else []
            month_group = (
                df.groupby("month")
                .agg(
                    avg_temp=("AvgTemp_C", "mean"),
                    rainfall=("Rainfall_mm", "mean"),
                    humidity=("Humidity_pct", "mean"),
                    wind_speed=("WindSpeed_mps", "mean")
                )
                .reset_index()
                .sort_values("month")
            ) if "month" in df.columns else pd.DataFrame()

            yearly_group = (
                df.groupby("year")
                .agg(
                    avg_temp=("AvgTemp_C", "mean"),
                    rainfall=("Rainfall_mm", "sum"),
                    humidity=("Humidity_pct", "mean"),
                    wind_speed=("WindSpeed_mps", "mean")
                )
                .reset_index()
                .sort_values("year")
            ) if "year" in df.columns else pd.DataFrame()

            station_group = pd.DataFrame()
            if "district" in df.columns:
                station_group = (
                    df.groupby("district")
                    .agg(
                        avg_temp=("AvgTemp_C", "mean"),
                        min_temp=("Temp_Min_C", "mean"),
                        rainfall=("Rainfall_mm", "sum"),
                        humidity=("Humidity_pct", "mean"),
                        wind_speed=("WindSpeed_mps", "mean"),
                        record_count=("district", "count")
                    )
                    .reset_index()
                    .sort_values("district")
                )

            hottest_month = None
            coldest_month = None
            driest_month = None
            if not month_group.empty:
                hottest = month_group.dropna(subset=["avg_temp"]).sort_values("avg_temp", ascending=False).head(1)
                coldest = month_group.dropna(subset=["avg_temp"]).sort_values("avg_temp", ascending=True).head(1)
                driest = month_group.dropna(subset=["rainfall"]).sort_values("rainfall", ascending=True).head(1)
                if not hottest.empty:
                    hottest_month = {"month": _month_name(hottest.iloc[0]["month"]), "value": _safe_round(hottest.iloc[0]["avg_temp"], 1)}
                if not coldest.empty:
                    coldest_month = {"month": _month_name(coldest.iloc[0]["month"]), "value": _safe_round(coldest.iloc[0]["avg_temp"], 1)}
                if not driest.empty:
                    driest_month = {"month": _month_name(driest.iloc[0]["month"]), "value": _safe_round(driest.iloc[0]["rainfall"], 1)}

            monthly_rows = []
            for _, row in month_group.iterrows():
                monthly_rows.append({
                    "month": int(row["month"]) if pd.notna(row["month"]) else None,
                    "month_name": _month_name(row["month"]),
                    "avg_temp": _safe_round(row["avg_temp"], 1),
                    "rainfall": _safe_round(row["rainfall"], 1),
                    "humidity": _safe_round(row["humidity"], 1),
                    "wind_speed": _safe_round(row["wind_speed"], 1)
                })

            distribution = []
            if "DroughtSeverity" in df.columns:
                counts = df["DroughtSeverity"].dropna().astype(str).str.strip().value_counts()
                distribution = [
                    {"label": label, "count": int(count)}
                    for label, count in counts.items()
                    if label
                ]

            work = df.copy()
            date_col = "date" if "date" in work.columns else None
            if date_col:
                work[date_col] = work[date_col].astype(str)
                work = work.sort_values(date_col, ascending=False)
            elif "year" in work.columns:
                work = work.sort_values(["year", "month"], ascending=False)

            records = [_record_from_row(row) for _, row in work.head(100).iterrows()]
            highest_temp = _top_record(df, "Temp_Max_C", ascending=False)
            lowest_temp = _top_record(df, "Temp_Min_C", ascending=True)
            max_rainfall = _top_record(df, "Rainfall_mm", ascending=False)

            yearly_rows = []
            hottest_year = None
            wettest_year = None
            driest_year = None
            if not yearly_group.empty:
                for _, row in yearly_group.iterrows():
                    yearly_rows.append({
                        "year": int(row["year"]) if pd.notna(row["year"]) else None,
                        "avg_temp": _safe_round(row["avg_temp"], 1),
                        "rainfall": _safe_round(row["rainfall"], 1),
                        "humidity": _safe_round(row["humidity"], 1),
                        "wind_speed": _safe_round(row["wind_speed"], 1)
                    })
                hottest = yearly_group.dropna(subset=["avg_temp"]).sort_values("avg_temp", ascending=False).head(1)
                wettest = yearly_group.dropna(subset=["rainfall"]).sort_values("rainfall", ascending=False).head(1)
                driest = yearly_group.dropna(subset=["rainfall"]).sort_values("rainfall", ascending=True).head(1)
                if not hottest.empty:
                    hottest_year = {"year": int(hottest.iloc[0]["year"]), "value": _safe_round(hottest.iloc[0]["avg_temp"], 1)}
                if not wettest.empty:
                    wettest_year = {"year": int(wettest.iloc[0]["year"]), "value": _safe_round(wettest.iloc[0]["rainfall"], 1)}
                if not driest.empty:
                    driest_year = {"year": int(driest.iloc[0]["year"]), "value": _safe_round(driest.iloc[0]["rainfall"], 1)}

            station_analysis = {
                "labels": [],
                "avg_temp": [],
                "rainfall": [],
                "humidity": [],
                "wind_speed": [],
                "hottest_station": None,
                "coldest_station": None,
                "wettest_station": None,
                "driest_station": None
            }
            if not station_group.empty:
                station_sorted = station_group.sort_values("rainfall", ascending=False).head(12)
                station_analysis["labels"] = station_sorted["district"].astype(str).tolist()
                station_analysis["avg_temp"] = [_safe_round(value, 1) for value in station_sorted["avg_temp"].tolist()]
                station_analysis["rainfall"] = [_safe_round(value, 1) for value in station_sorted["rainfall"].tolist()]
                station_analysis["humidity"] = [_safe_round(value, 1) for value in station_sorted["humidity"].tolist()]
                station_analysis["wind_speed"] = [_safe_round(value, 1) for value in station_sorted["wind_speed"].tolist()]

                hottest_station = station_group.dropna(subset=["avg_temp"]).sort_values("avg_temp", ascending=False).head(1)
                coldest_station = station_group.dropna(subset=["min_temp"]).sort_values("min_temp", ascending=True).head(1)
                wettest_station = station_group.dropna(subset=["rainfall"]).sort_values("rainfall", ascending=False).head(1)
                driest_station = station_group.dropna(subset=["rainfall"]).sort_values("rainfall", ascending=True).head(1)
                if not hottest_station.empty:
                    station_analysis["hottest_station"] = {"name": hottest_station.iloc[0]["district"], "value": _safe_round(hottest_station.iloc[0]["avg_temp"], 1)}
                if not coldest_station.empty:
                    station_analysis["coldest_station"] = {"name": coldest_station.iloc[0]["district"], "value": _safe_round(coldest_station.iloc[0]["min_temp"], 1)}
                if not wettest_station.empty:
                    station_analysis["wettest_station"] = {"name": wettest_station.iloc[0]["district"], "value": _safe_round(wettest_station.iloc[0]["rainfall"], 1)}
                if not driest_station.empty:
                    station_analysis["driest_station"] = {"name": driest_station.iloc[0]["district"], "value": _safe_round(driest_station.iloc[0]["rainfall"], 1)}

            indicators = {
                "temperature_change": None,
                "rainfall_change": None,
                "humidity_change": None,
                "wind_change": None,
                "severe_drought_records": 0
            }
            if len(yearly_rows) >= 2:
                first_year = yearly_rows[0]
                last_year = yearly_rows[-1]
                indicators["temperature_change"] = _safe_round((last_year.get("avg_temp") or 0) - (first_year.get("avg_temp") or 0), 1)
                indicators["rainfall_change"] = _safe_round((last_year.get("rainfall") or 0) - (first_year.get("rainfall") or 0), 1)
                indicators["humidity_change"] = _safe_round((last_year.get("humidity") or 0) - (first_year.get("humidity") or 0), 1)
                indicators["wind_change"] = _safe_round((last_year.get("wind_speed") or 0) - (first_year.get("wind_speed") or 0), 1)
            if "DroughtSeverity" in df.columns:
                indicators["severe_drought_records"] = int(
                    df["DroughtSeverity"].dropna().astype(str).str.strip().str.lower().eq("severe").sum()
                )

            wettest_month = None
            if not month_group.empty:
                wettest = month_group.dropna(subset=["rainfall"]).sort_values("rainfall", ascending=False).head(1)
                if not wettest.empty:
                    wettest_month = {"month": _month_name(wettest.iloc[0]["month"]), "value": _safe_round(wettest.iloc[0]["rainfall"], 1)}

            place = filters.get("district") or filters.get("province") or "the selected area"
            insights = []
            if wettest_month:
                insights.append(f"Rainfall levels were highest around {wettest_month['month']} with an average of {wettest_month['value']} mm.")
            if hottest_month:
                insights.append(f"Temperatures peaked around {hottest_month['month']} with an average temperature of {hottest_month['value']} C.")
            if driest_month:
                insights.append(f"The driest month in the selected records was {driest_month['month']} with about {driest_month['value']} mm of rainfall.")
            if available_years:
                insights.append(f"The analysis covers {place} across {min(available_years)} to {max(available_years)} using {len(df):,} climate records.")

            return success_response({
                "scope": filters,
                "summary": {
                    "avg_temperature": _safe_round(df["AvgTemp_C"].mean(), 1),
                    "total_rainfall": _safe_round(df["Rainfall_mm"].sum(), 1) if "Rainfall_mm" in df.columns else None,
                    "humidity": _safe_round(df["Humidity_pct"].mean(), 1) if "Humidity_pct" in df.columns else None,
                    "wind_speed": _safe_round(df["WindSpeed_mps"].mean(), 1) if "WindSpeed_mps" in df.columns else None,
                    "hottest_month": hottest_month,
                    "coldest_month": coldest_month,
                    "hottest_year": hottest_year,
                    "wettest_year": wettest_year,
                    "driest_year": driest_year,
                    "record_count": int(len(df))
                },
                "yearly": _build_series(
                    yearly_group,
                    "year",
                    {
                        "avg_temp": "avg_temp",
                        "rainfall": "rainfall",
                        "humidity": "humidity",
                        "wind_speed": "wind_speed"
                    }
                ),
                "yearly_rows": yearly_rows,
                "monthly": monthly_rows,
                "distribution": distribution,
                "station_analysis": station_analysis,
                "indicators": indicators,
                "extremes": {
                    "highest_temperature": highest_temp,
                    "lowest_temperature": lowest_temp,
                    "maximum_rainfall": max_rainfall,
                    "driest_month": driest_month
                },
                "records": records,
                "station": {
                    "name": "Zambia climate observation dataset",
                    "province": filters.get("province") or "All provinces",
                    "region": filters.get("district") or "All districts",
                    "elevation": "Not specified in dataset",
                    "coordinates": "Not specified in dataset"
                },
                "insights": insights
            })
        except Exception as error:
            logger.error(f"Climate analysis endpoint error: {error}", exc_info=True)
            return error_response("Unable to build climate analysis right now.", 500)

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
                'DroughtSeverity'
            ])

            horizon = max(1, min(horizon or 5, 100))
            if df is None or df.empty:
                return success_response({
                    "scope": filters,
                    "horizon": horizon,
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
                target_year = (last_year + horizon) if last_year else None

            series = [
                _build_projection_series(df, metric_key, horizon, selected_scenario=scenario)
                for metric_key in ["rainfall", "temperature", "drought"]
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
