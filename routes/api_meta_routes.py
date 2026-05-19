import logging
import time

from flask import request

from utils.database import db_manager
from utils.data_loader import get_filter_options_from_db, load_data_from_db
from utils.live_weather import get_live_weather
from utils.responses import empty_response, error_response, success_response

from .api_shared import SITE_SUMMARY_CACHE, SITE_SUMMARY_TTL_SECONDS, get_top_province_metric_for_year
from .api_v1 import (
    build_live_weather_payload,
    build_site_summary_updates,
    get_district_climate_summaries_for_year,
    get_latest_daily_district_records,
    get_latest_monthly_district_records,
    merge_live_weather_into_site_summary,
)


logger = logging.getLogger(__name__)


def register_meta_routes(api_v1):
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
                        'DroughtSeverity'
                    ]
                ) if latest_year is not None else None

                count_result = db_manager.execute_query("SELECT COUNT(*) AS total_records FROM climate_records") or []
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

    @api_v1.route('/docs', methods=['GET'])
    def api_documentation():
        docs = {"api_version": "1.0.0", "base_url": "/api/v1", "endpoints": {
            "GET /health": "Health check", "GET /provinces": "List provinces",
            "GET /districts": "List districts", "GET /years": "List years", "GET /year-coverage": "Year-by-year record and month completeness coverage", "GET /overview": "Summary statistics",
            "GET /rainfall-trend": "Rainfall trend", "GET /temperature-trend": "Temperature trend",
            "GET /rainfall-distribution": "Rainfall histogram bins and distribution values",
            "GET /drought-trend": "Drought score trend over years or months",
            "GET /temperature-distribution": "Temperature histogram bins and distribution values",
            "GET /drought-summary": "Drought summary",
            "GET /soil-moisture-trend": "Soil moisture trend",
            "GET /impact-trends": "Impact trends",
            "GET /extreme-events": "Extreme climate event signals and monthly event activity",
            "GET /flood-events": "Flood-focused rainfall event analysis and monthly exposure patterns",
            "GET /district-comparison": "Compare multiple districts across several variables and a focus trend",
            "GET /explorer": "Climate Data Explorer filters, trend, summary statistics, and raw table rows",
            "GET /explorer/export": "Download Climate Data Explorer results as CSV",
            "GET /site-summary": "Cached footer and ticker summary payload for shared page chrome, with optional lat/lon to merge live weather",
            "GET /live-weather": "Live current conditions for the viewer latitude and longitude",
            "GET /projections": "RCP-style scenario projections for rainfall, temperature, and drought pressure",
            "GET /district-summary": "District climate summary for map side panel",
            "GET /map-district-metric": "District-level values for choropleth map shading",
            "GET /district-monthly-notifications": "Month-by-month notification summaries for the selected scope in a year",
            "GET /rankings/rainfall": "Rainfall rankings",
            "GET /rankings/temperature": "Temperature rankings",
            "GET /rankings/drought": "Drought severity rankings"
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
                'drought': [group_field, 'year', 'DroughtSeverity']
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
            else:
                return error_response("Invalid metric. Choose from: rainfall, temperature, drought", 400)

            for _, row in grouped.iterrows():
                rankings.append({
                    "rank": len(rankings) + 1,
                    "province": row['province'],
                    "value": round(row['value'], 2)
                })

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
