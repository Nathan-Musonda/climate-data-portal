import csv
import io
import logging

from flask import Response, request

from utils.data_loader import load_data_from_db
from utils.responses import error_response, success_response

from .api_shared import (
    DEFAULT_DISTRICT_COMPARISON_METRICS,
    DISTRICT_COMPARISON_METRICS,
    EXPLORER_VARIABLES,
    aggregate_metric_value,
    build_explorer_rows,
    build_explorer_summary,
    build_explorer_trend,
    filter_explorer_df,
    get_explorer_date_column,
    get_explorer_variable_options,
    list_district_comparison_metrics,
    normalize_name,
    parse_explorer_filters,
    round_metric_value,
)


logger = logging.getLogger(__name__)


def register_explorer_routes(api_v1):
    @api_v1.route('/district-comparison', methods=['GET'])
    def get_district_comparison():
        try:
            df = load_data_from_db(columns=[
                'district', 'province', 'year', 'Rainfall_mm', 'Temp_Max_C',
                'SoilMoisture_pct', 'DroughtSeverity'
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

            requested_districts = [district.strip() for district in request.args.get('districts', '').split(',') if district.strip()]
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
                metric_values = {metric_key: aggregate_metric_value(district_df, metric_key) for metric_key in selected_metrics}
                table_rows.append({"district": district, "province": province_lookup.get(district), "metrics": metric_values})

            comparison_values = [row['metrics'].get(focus_metric) for row in table_rows]
            trend_series = []
            for district in selected_districts:
                district_history = df_selected_all_years[df_selected_all_years['district'] == district]
                year_map = {}
                for year in available_years:
                    year_map[year] = aggregate_metric_value(district_history[district_history['year'] == year], focus_metric)
                trend_series.append({"district": district, "province": province_lookup.get(district), "values": [year_map.get(year) for year in available_years]})

            valid_focus_rows = [row for row in table_rows if row['metrics'].get(focus_metric) is not None]
            insights = []
            if valid_focus_rows:
                leader = max(valid_focus_rows, key=lambda row: row['metrics'][focus_metric])
                trailer = min(valid_focus_rows, key=lambda row: row['metrics'][focus_metric])
                gap = round_metric_value(focus_metric, leader['metrics'][focus_metric] - trailer['metrics'][focus_metric])
                metric_label = DISTRICT_COMPARISON_METRICS[focus_metric]['label']
                metric_unit = DISTRICT_COMPARISON_METRICS[focus_metric]['unit']
                unit_suffix = f" {metric_unit}".rstrip()
                insights.append(f"{leader['district']} has the highest {metric_label.lower()} in {selected_year} at {leader['metrics'][focus_metric]}{unit_suffix}.")
                insights.append(f"The gap between the highest and lowest selected districts is {gap}{unit_suffix} for {metric_label.lower()}.")

            return success_response({
                "year": selected_year,
                "available_years": available_years,
                "available_metrics": list_district_comparison_metrics(),
                "selected_metrics": selected_metrics,
                "focus_metric": focus_metric,
                "focus_metric_label": DISTRICT_COMPARISON_METRICS[focus_metric]["label"],
                "focus_metric_unit": DISTRICT_COMPARISON_METRICS[focus_metric]["unit"],
                "districts": selected_districts,
                "comparison": {"labels": [row['district'] for row in table_rows], "values": comparison_values},
                "trend": {"years": available_years, "series": trend_series},
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
                'Temp_Max_C', 'Temp_Min_C', 'SoilMoisture_pct', 'DroughtSeverity'
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
                "table": {"rows": rows, "shown_rows": len(rows), "total_rows": int(len(filtered_df))}
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
                'Temp_Max_C', 'Temp_Min_C', 'SoilMoisture_pct', 'DroughtSeverity'
            ])
            if df is None or df.empty:
                return error_response("No data available for export", 404)

            filtered_df = filter_explorer_df(df, filters)
            if filtered_df.empty:
                return error_response("No data found for the selected filters", 404)

            date_col = get_explorer_date_column(filtered_df)
            export_columns = [
                date_col, 'province', 'district', 'year', 'month', 'Rainfall_mm',
                'Temp_Max_C', 'Temp_Min_C', 'SoilMoisture_pct', 'DroughtSeverity'
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
