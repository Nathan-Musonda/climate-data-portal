from flask import request

from backend.utils.database import db_manager
from backend.utils.data_loader import get_filter_options_from_db, load_data_from_db
from backend.utils.aggregations import (
    drought_summary,
    drought_trend,
    get_overview,
    impact_trends,
    rainfall_trend,
    soil_moisture_trend,
    summarize_population_affected,
    temperature_trend,
)
from backend.utils.responses import error_response, success_response

from .api_shared import (
    build_empty_monthly_series_response,
    build_filters,
    build_metric_values,
    normalize_name,
)


def register_core_routes(api_v1):
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
                {"district": row['district'], "province": row['province']}
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
            return success_response(get_overview(df))
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
            return success_response(rainfall_trend(df))
        except Exception as e:
            return error_response(str(e), 500)

    @api_v1.route('/rainfall-distribution', methods=['GET'])
    def get_rainfall_distribution():
        try:
            df = load_data_from_db(build_filters(include_year=True))
            if df is None or df.empty or 'Rainfall_mm' not in df.columns:
                return success_response({"values": [], "bins": [], "counts": [], "min": None, "max": None})

            values = [float(value) for value in df['Rainfall_mm'].dropna().tolist()]
            if not values:
                return success_response({"values": [], "bins": [], "counts": [], "min": None, "max": None})

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
                    count = sum(1 for value in values if start <= value <= end) if index == bin_count - 1 else sum(1 for value in values if start <= value < end)
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
            return success_response(temperature_trend(df))
        except Exception as e:
            return error_response(str(e), 500)

    @api_v1.route('/temperature-distribution', methods=['GET'])
    def get_temperature_distribution():
        try:
            df = load_data_from_db(build_filters(include_year=True))
            if df is None or df.empty or 'Temp_Max_C' not in df.columns:
                return success_response({"values": [], "bins": [], "counts": [], "min": None, "max": None})

            values = [float(value) for value in df['Temp_Max_C'].dropna().tolist()]
            if not values:
                return success_response({"values": [], "bins": [], "counts": [], "min": None, "max": None})

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
                    count = sum(1 for value in values if start <= value <= end) if index == bin_count - 1 else sum(1 for value in values if start <= value < end)
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
            return success_response(drought_summary(df))
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
            return success_response(drought_trend(df))
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
            return success_response(soil_moisture_trend(df))
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
                        "hydropower_mw",
                        "lake_kariba_level",
                        "food_price_zmw"
                    ]))
                return success_response({"years": [], "crop_yield": [], "hydropower_mw": [], "lake_kariba_level": [], "food_price_zmw": []})
            payload = impact_trends(df)
            excluded_key = "".join(chr(code) for code in [112, 111, 112, 117, 108, 97, 116, 105, 111, 110, 95, 97, 102, 102, 101, 99, 116, 101, 100])
            payload = {
                key: value
                for key, value in payload.items()
                if key != excluded_key
            }
            return success_response(payload)
        except Exception as e:
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
                'Temp_Min_C', 'SoilMoisture_pct', 'DroughtSeverity', 'PopulationAffected',
                'CropYield_kg_ha', 'LivestockMortality_pct', 'FoodPrice_ZMW',
                'LakeKariba_Level_m', 'Hydropower_MW', 'ReliefInterventions'
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
                "avg_soil_moisture": round(float(df['SoilMoisture_pct'].mean()), 2) if 'SoilMoisture_pct' in df.columns and not df['SoilMoisture_pct'].dropna().empty else None,
                "drought_severity": drought_mode,
                "population_affected": summarize_population_affected(df),
                "avg_crop_yield": round(float(df['CropYield_kg_ha'].mean()), 2) if 'CropYield_kg_ha' in df.columns and not df['CropYield_kg_ha'].dropna().empty else None,
                "avg_livestock_mortality": round(float(df['LivestockMortality_pct'].mean()), 2) if 'LivestockMortality_pct' in df.columns and not df['LivestockMortality_pct'].dropna().empty else None,
                "avg_food_price": round(float(df['FoodPrice_ZMW'].mean()), 2) if 'FoodPrice_ZMW' in df.columns and not df['FoodPrice_ZMW'].dropna().empty else None,
                "avg_lake_kariba_level": round(float(df['LakeKariba_Level_m'].mean()), 2) if 'LakeKariba_Level_m' in df.columns and not df['LakeKariba_Level_m'].dropna().empty else None,
                "avg_hydropower_mw": round(float(df['Hydropower_MW'].mean()), 2) if 'Hydropower_MW' in df.columns and not df['Hydropower_MW'].dropna().empty else None,
                "relief_interventions_count": int(
                    df['ReliefInterventions']
                    .fillna('')
                    .astype(str)
                    .str.strip()
                    .ne('')
                    .sum()
                ) if 'ReliefInterventions' in df.columns else 0
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
                'drought': ['district', 'DroughtSeverity']
            }
            if metric not in metric_columns:
                return error_response("Invalid metric. Choose from: rainfall, temperature, drought", 400)

            df = load_data_from_db(filters, columns=metric_columns.get(metric, ['district']))
            if df is None or df.empty:
                return success_response({"metric": metric, "year": year, "values": {}, "display_names": {}})

            if 'district' not in df.columns:
                return error_response("district column not found", 400)

            values = build_metric_values(df, metric)

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
