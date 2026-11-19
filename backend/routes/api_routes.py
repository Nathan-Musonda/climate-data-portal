# routes/api_routes.py - COMPLETELY UPDATED VERSION
from flask import Blueprint, request, current_app
import logging
from backend.utils.data_loader import load_data
from backend.utils.filters import apply_filters, get_filter_options, has_data
from backend.utils.aggregations import (
    get_overview, rainfall_trend, temperature_trend,
    drought_summary, ndvi_trend, soil_moisture_trend, impact_trends
)
from backend.utils.responses import success_response, error_response, empty_response
from backend.utils.validation import validate_year, validate_month, validate_province, sanitize_string

logger = logging.getLogger(__name__)
api_routes = Blueprint("api_routes", __name__, url_prefix="/api")


def get_filtered_df_with_validation():
    """Helper function with validation"""
    try:
        df = load_data(current_app.config["DATA_FILE"])

        # Get and validate parameters
        province_raw = request.args.get("province")
        district_raw = request.args.get("district")
        year_raw = request.args.get("year")
        month_raw = request.args.get("month")

        # Get valid provinces for validation
        valid_provinces = df["Province"].unique(
        ).tolist() if "Province" in df.columns else []

        # Validate province
        province, province_error = validate_province(
            province_raw, valid_provinces)
        if province_error:
            return None, error_response(province_error, 400)

        # Validate year
        year, year_error = validate_year(year_raw)
        if year_error:
            return None, error_response(year_error, 400)

        # Validate month
        month, month_error = validate_month(month_raw)
        if month_error:
            return None, error_response(month_error, 400)

        # Sanitize district
        district = sanitize_string(district_raw)

        # Apply filters
        filtered_df = apply_filters(
            df, province=province, district=district, year=year, month=month)

        return filtered_df, None

    except Exception as e:
        logger.error(
            f"Error in get_filtered_df_with_validation: {e}", exc_info=True)
        return None, error_response(f"Internal server error: {str(e)}", 500)


@api_routes.route("/health", methods=["GET"])
def health():
    """API health check"""
    try:
        df = load_data(current_app.config["DATA_FILE"])
        return success_response({
            "status": "healthy",
            "records_loaded": len(df),
            "columns": df.columns.tolist(),
            "api_version": current_app.config.get("API_VERSION", "1.0.0")
        })
    except Exception as e:
        logger.error(f"Health check failed: {e}", exc_info=True)
        return error_response(f"Health check failed: {str(e)}", 500)


@api_routes.route("/info", methods=["GET"])
def info():
    """Get dataset information"""
    try:
        df = load_data(current_app.config["DATA_FILE"])
        return success_response({
            "total_records": len(df),
            "total_columns": len(df.columns),
            "columns": df.columns.tolist(),
            "provinces": sorted(df["Province"].dropna().unique().tolist()) if "Province" in df.columns else [],
            "years": sorted(df["Year"].dropna().unique().tolist()) if "Year" in df.columns else [],
            "date_range": {
                "start": df["Date"].min().isoformat() if "Date" in df.columns else None,
                "end": df["Date"].max().isoformat() if "Date" in df.columns else None
            }
        })
    except Exception as e:
        logger.error(f"Info endpoint error: {e}", exc_info=True)
        return error_response(str(e), 500)


@api_routes.route("/provinces", methods=["GET"])
def get_provinces():
    """Get all province names"""
    try:
        df = load_data(current_app.config["DATA_FILE"])
        provinces = sorted(df["Province"].dropna().unique().tolist())
        return success_response(provinces)
    except Exception as e:
        logger.error(f"Provinces endpoint error: {e}", exc_info=True)
        return error_response(str(e), 500)


@api_routes.route("/districts", methods=["GET"])
def get_districts():
    """Get districts, optionally filtered by province"""
    try:
        df = load_data(current_app.config["DATA_FILE"])
        province = request.args.get("province")

        if province and province.lower() != "all":
            df = df[df["Province"].str.lower() == province.lower()]

        districts = sorted(df["District"].dropna().unique().tolist())
        return success_response(districts)
    except Exception as e:
        logger.error(f"Districts endpoint error: {e}", exc_info=True)
        return error_response(str(e), 500)


@api_routes.route("/years", methods=["GET"])
def get_years():
    """Get all available years"""
    try:
        df = load_data(current_app.config["DATA_FILE"])

        if "Year" in df.columns:
            years = sorted(df["Year"].dropna().unique().tolist())
        elif "Date" in df.columns:
            years = sorted(df["Date"].dt.year.dropna().unique().tolist())
        else:
            years = []

        return success_response(years)
    except Exception as e:
        logger.error(f"Years endpoint error: {e}", exc_info=True)
        return error_response(str(e), 500)


@api_routes.route("/months", methods=["GET"])
def get_months():
    """Get all available months"""
    try:
        df = load_data(current_app.config["DATA_FILE"])

        if "Month" in df.columns:
            months = sorted(df["Month"].dropna().unique().tolist())
        elif "Date" in df.columns:
            months = sorted(df["Date"].dt.month.dropna().unique().tolist())
        else:
            months = []

        return success_response(months)
    except Exception as e:
        logger.error(f"Months endpoint error: {e}", exc_info=True)
        return error_response(str(e), 500)


@api_routes.route("/filter-options", methods=["GET"])
def get_filter_options_endpoint():
    """Get all filter options at once"""
    try:
        df = load_data(current_app.config["DATA_FILE"])
        options = get_filter_options(df)
        return success_response(options)
    except Exception as e:
        logger.error(f"Filter options endpoint error: {e}", exc_info=True)
        return error_response(str(e), 500)


@api_routes.route("/overview", methods=["GET"])
def get_overview_endpoint():
    """Get overview statistics with empty handling"""
    try:
        filtered_df, error = get_filtered_df_with_validation()
        if error:
            return error

        if not has_data(filtered_df):
            return empty_response("No data found for selected filters")

        stats = get_overview(filtered_df)
        return success_response(stats)
    except Exception as e:
        logger.error(f"Overview endpoint error: {e}", exc_info=True)
        return error_response(str(e), 500)


@api_routes.route("/rainfall-trend", methods=["GET"])
def get_rainfall_trend():
    """Get rainfall trend with empty handling"""
    try:
        filtered_df, error = get_filtered_df_with_validation()
        if error:
            return error

        if not has_data(filtered_df):
            return empty_response("No rainfall data found for selected filters")

        trend = rainfall_trend(filtered_df)
        return success_response(trend)
    except Exception as e:
        logger.error(f"Rainfall trend endpoint error: {e}", exc_info=True)
        return error_response(str(e), 500)


@api_routes.route("/temperature-trend", methods=["GET"])
def get_temperature_trend():
    """Get temperature trend with empty handling"""
    try:
        filtered_df, error = get_filtered_df_with_validation()
        if error:
            return error

        if not has_data(filtered_df):
            return empty_response("No temperature data found for selected filters")

        trend = temperature_trend(filtered_df)
        return success_response(trend)
    except Exception as e:
        logger.error(f"Temperature trend endpoint error: {e}", exc_info=True)
        return error_response(str(e), 500)


@api_routes.route("/drought-summary", methods=["GET"])
def get_drought_summary():
    """Get drought summary with empty handling"""
    try:
        filtered_df, error = get_filtered_df_with_validation()
        if error:
            return error

        if not has_data(filtered_df):
            return empty_response("No drought data found for selected filters")

        summary = drought_summary(filtered_df)
        return success_response(summary)
    except Exception as e:
        logger.error(f"Drought summary endpoint error: {e}", exc_info=True)
        return error_response(str(e), 500)


@api_routes.route("/ndvi-trend", methods=["GET"])
def get_ndvi_trend():
    """Get NDVI trend with empty handling"""
    try:
        filtered_df, error = get_filtered_df_with_validation()
        if error:
            return error

        if not has_data(filtered_df):
            return empty_response("No NDVI data found for selected filters")

        trend = ndvi_trend(filtered_df)
        return success_response(trend)
    except Exception as e:
        logger.error(f"NDVI trend endpoint error: {e}", exc_info=True)
        return error_response(str(e), 500)


@api_routes.route("/soil-moisture-trend", methods=["GET"])
def get_soil_moisture_trend():
    """Get soil moisture trend with empty handling"""
    try:
        filtered_df, error = get_filtered_df_with_validation()
        if error:
            return error

        if not has_data(filtered_df):
            return empty_response("No soil moisture data found for selected filters")

        trend = soil_moisture_trend(filtered_df)
        return success_response(trend)
    except Exception as e:
        logger.error(f"Soil moisture trend endpoint error: {e}", exc_info=True)
        return error_response(str(e), 500)


@api_routes.route("/impact-trends", methods=["GET"])
def get_impact_trends():
    """Get impact trends with empty handling"""
    try:
        filtered_df, error = get_filtered_df_with_validation()
        if error:
            return error

        if not has_data(filtered_df):
            return empty_response("No impact data found for selected filters")

        trends = impact_trends(filtered_df)
        return success_response(trends)
    except Exception as e:
        logger.error(f"Impact trends endpoint error: {e}", exc_info=True)
        return error_response(str(e), 500)


@api_routes.route("/province-summary", methods=["GET"])
def get_province_summary():
    """Get summary statistics by province"""
    try:
        filtered_df, error = get_filtered_df_with_validation()
        if error:
            return error

        if not has_data(filtered_df):
            return empty_response("No data found for selected filters")

        # Aggregate by province
        summary = filtered_df.groupby("Province").agg({
            "Rainfall_mm": "mean",
            "Temp_Max_C": "mean",
            "Temp_Min_C": "mean",
            "DroughtSeverity": lambda x: x.value_counts().index[0] if len(x) > 0 else None
        }).reset_index()

        # Convert to dict
        result = summary.to_dict(orient="records")
        return success_response(result)
    except Exception as e:
        logger.error(f"Province summary endpoint error: {e}", exc_info=True)
        return error_response(str(e), 500)


@api_routes.route("/drought-by-year", methods=["GET"])
def get_drought_by_year():
    """Get drought severity distribution by year"""
    try:
        filtered_df, error = get_filtered_df_with_validation()
        if error:
            return error

        if not has_data(filtered_df) or "DroughtSeverity" not in filtered_df.columns:
            return empty_response("No drought data found")

        # Cross-tabulation of year and drought severity
        drought_by_year = pd.crosstab(
            filtered_df["Year"],
            filtered_df["DroughtSeverity"],
            normalize='index'
        ).reset_index()

        result = drought_by_year.to_dict(orient="records")
        return success_response(result)
    except Exception as e:
        logger.error(f"Drought by year endpoint error: {e}", exc_info=True)
        return error_response(str(e), 500)


@api_routes.route("/data-preview", methods=["GET"])
def get_data_preview():
    """Get preview of data with pagination"""
    try:
        filtered_df, error = get_filtered_df_with_validation()
        if error:
            return error

        if not has_data(filtered_df):
            return empty_response("No data found for selected filters")

        # Pagination parameters
        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("per_page", 50, type=int)
        per_page = min(per_page, 200)  # Limit to 200 max

        # Sorting
        sort_by = request.args.get("sort_by", "Date")
        sort_order = request.args.get("sort_order", "desc")

        # Apply sorting
        if sort_by in filtered_df.columns:
            ascending = (sort_order.lower() == "asc")
            filtered_df = filtered_df.sort_values(sort_by, ascending=ascending)

        # Pagination
        start = (page - 1) * per_page
        end = start + per_page
        paginated_df = filtered_df.iloc[start:end]

        # Convert dates to strings
        if "Date" in paginated_df.columns:
            paginated_df["Date"] = paginated_df["Date"].astype(str)

        return success_response({
            "page": page,
            "per_page": per_page,
            "total_records": len(filtered_df),
            "total_pages": (len(filtered_df) + per_page - 1) // per_page,
            "data": paginated_df.replace({float('nan'): None}).to_dict(orient="records")
        })
    except Exception as e:
        logger.error(f"Data preview endpoint error: {e}", exc_info=True)
        return error_response(str(e), 500)
