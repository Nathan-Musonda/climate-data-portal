import logging

from utils.data_loader import load_data_from_db
from utils.monthly import (
    build_empty_monthly_chart_payload,
    build_monthly_chart_payload as shared_build_monthly_chart_payload,
    prepare_monthly_frame,
)
from utils.responses import error_response, success_response

from .api_shared import build_filters


logger = logging.getLogger(__name__)


def build_monthly_chart_payload(rows, value_keys, fill_values=None):
    return shared_build_monthly_chart_payload(rows, value_keys, fill_values=fill_values)


def register_event_routes(api_v1):
    @api_v1.route('/extreme-events', methods=['GET'])
    def get_extreme_events():
        try:
            filters = build_filters(include_year=True)
            df = load_data_from_db(filters, columns=[
                'year', 'month', 'province', 'district', 'Rainfall_mm', 'Temp_Max_C',
                'DroughtSeverity'
            ])
            empty_monthly = build_empty_monthly_chart_payload([
                "heat_events",
                "heavy_rainfall_events",
                "severe_drought_events",
                "average_rainfall"
            ])

            if df is None or df.empty:
                return success_response({
                    "year": filters.get('year'),
                    "province": filters.get('province'),
                    "summary": {
                        "heat_event_count": 0,
                        "heavy_rainfall_count": 0,
                        "severe_drought_count": 0,
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
                avg_rainfall = float(month_df['Rainfall_mm'].mean()) if 'Rainfall_mm' in month_df.columns and not month_df['Rainfall_mm'].dropna().empty else None
                observed_month_rows.append({
                    "month": month,
                    "heavy_rainfall_events": heavy_count,
                    "heat_events": heat_count,
                    "severe_drought_events": severe_count,
                    "average_rainfall": round(avg_rainfall, 2) if avg_rainfall is not None else None
                })

            monthly_payload, monthly_rows = build_monthly_chart_payload(
                observed_month_rows,
                [
                    "heat_events",
                    "heavy_rainfall_events",
                    "severe_drought_events",
                    "average_rainfall"
                ]
            )
            monthly_heat = monthly_payload["heat_events"]
            monthly_rain = monthly_payload["heavy_rainfall_events"]
            monthly_drought = monthly_payload["severe_drought_events"]

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

            insights = []
            heat_rows = [row for row in monthly_rows if (row['heat_events'] or 0) > 0]
            rain_rows = [row for row in monthly_rows if (row['heavy_rainfall_events'] or 0) > 0]
            drought_rows = [row for row in monthly_rows if (row['severe_drought_events'] or 0) > 0]
            max_heat_month = max(heat_rows, key=lambda row: row['heat_events']) if heat_rows else None
            max_rain_month = max(rain_rows, key=lambda row: row['heavy_rainfall_events']) if rain_rows else None
            max_drought_month = max(drought_rows, key=lambda row: row['severe_drought_events']) if drought_rows else None
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
                'SPI', 'SoilMoisture_pct'
            ])
            empty_extreme_rainfall = build_empty_monthly_chart_payload([
                "high_rainfall_events",
                "very_high_rainfall_events",
                "extreme_rainfall_events"
            ])
            empty_extreme_rainfall["top_rainfall_values"] = []
            empty_monthly_pattern = build_empty_monthly_chart_payload([
                "flood_events",
                "average_rainfall",
                "average_spi",
                "average_soil_moisture"
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
                        "max_rainfall": None,
                        "peak_month": None,
                        "avg_spi": None,
                        "avg_soil_moisture": None
                    },
                    "extreme_rainfall": empty_extreme_rainfall,
                    "rainfall_trend": {"labels": [], "average_rainfall": []},
                    "spi_trend": {"labels": [], "average_spi": []},
                    "soil_moisture_trend": {"labels": [], "average_soil_moisture": []},
                    "province_rainfall": {"labels": [], "values": []},
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
                        "max_rainfall": None,
                        "peak_month": None,
                        "avg_spi": None,
                        "avg_soil_moisture": None
                    },
                    "extreme_rainfall": empty_extreme_rainfall,
                    "rainfall_trend": {"labels": [], "average_rainfall": []},
                    "spi_trend": {"labels": [], "average_spi": []},
                    "soil_moisture_trend": {"labels": [], "average_soil_moisture": []},
                    "province_rainfall": {"labels": [], "values": []},
                    "monthly_pattern": empty_monthly_pattern,
                    "hotspots": [],
                    "insights": []
                })

            high_threshold = 50
            very_high_threshold = 100
            extreme_threshold = 150
            rainfall_threshold = float(df['Rainfall_mm'].quantile(0.90)) if 'Rainfall_mm' in df.columns and not df['Rainfall_mm'].dropna().empty else None

            observed_month_rows = []
            for month in sorted(df['month'].dropna().astype(int).unique().tolist()):
                month_df = df[df['month'] == month]
                avg_rainfall = float(month_df['Rainfall_mm'].mean()) if 'Rainfall_mm' in month_df.columns and not month_df['Rainfall_mm'].dropna().empty else None
                avg_spi = float(month_df['SPI'].mean()) if 'SPI' in month_df.columns and not month_df['SPI'].dropna().empty else None
                avg_soil_moisture = float(month_df['SoilMoisture_pct'].mean()) if 'SoilMoisture_pct' in month_df.columns and not month_df['SoilMoisture_pct'].dropna().empty else None
                observed_month_rows.append({
                    "month": month,
                    "flood_events": int((month_df['Rainfall_mm'] >= rainfall_threshold).sum()) if rainfall_threshold is not None and 'Rainfall_mm' in month_df.columns else 0,
                    "high_rainfall_events": int((month_df['Rainfall_mm'] >= high_threshold).sum()) if 'Rainfall_mm' in month_df.columns else 0,
                    "very_high_rainfall_events": int((month_df['Rainfall_mm'] >= very_high_threshold).sum()) if 'Rainfall_mm' in month_df.columns else 0,
                    "extreme_rainfall_events": int((month_df['Rainfall_mm'] >= extreme_threshold).sum()) if 'Rainfall_mm' in month_df.columns else 0,
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
                    "average_rainfall",
                    "average_spi",
                    "average_soil_moisture"
                ]
            )
            monthly_flood = monthly_pattern_payload["flood_events"]
            monthly_high = extreme_rainfall_payload["high_rainfall_events"]
            monthly_very_high = extreme_rainfall_payload["very_high_rainfall_events"]
            monthly_extreme = extreme_rainfall_payload["extreme_rainfall_events"]

            yearly_rainfall = []
            if 'year' in df.columns and 'Rainfall_mm' in df.columns:
                grouped = df.groupby('year')['Rainfall_mm'].mean().reset_index().sort_values('year')
                yearly_rainfall = [{"label": str(int(row['year'])), "value": round(float(row['Rainfall_mm']), 2)} for _, row in grouped.iterrows()]

            spi_trend = []
            if 'year' in df.columns and 'SPI' in df.columns:
                grouped = df.groupby('year')['SPI'].mean().reset_index().sort_values('year')
                spi_trend = [{"label": str(int(row['year'])), "value": round(float(row['SPI']), 2)} for _, row in grouped.iterrows() if row['SPI'] is not None]

            soil_moisture_trend = []
            if 'year' in df.columns and 'SoilMoisture_pct' in df.columns:
                grouped = df.groupby('year')['SoilMoisture_pct'].mean().reset_index().sort_values('year')
                soil_moisture_trend = [{"label": str(int(row['year'])), "value": round(float(row['SoilMoisture_pct']), 2)} for _, row in grouped.iterrows() if row['SoilMoisture_pct'] is not None]

            province_rainfall = []
            if 'province' in df.columns and 'Rainfall_mm' in df.columns:
                grouped = df.groupby('province')['Rainfall_mm'].mean().reset_index().sort_values('Rainfall_mm', ascending=False)
                province_rainfall = [{"label": row['province'], "value": round(float(row['Rainfall_mm']), 2)} for _, row in grouped.head(8).iterrows()]

            top_rainfall_values = []
            if 'Rainfall_mm' in df.columns:
                top_rows = (
                    df[['province', 'Rainfall_mm']]
                    .dropna(subset=['province', 'Rainfall_mm'])
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
                rain_rank = df[df['Rainfall_mm'] >= rainfall_threshold].groupby('province').size().sort_values(ascending=False)
                for province, count in rain_rank.head(5).items():
                    hotspots.append({"province": province, "flood_events": int(count)})

            flood_rows = [row for row in monthly_rows if (row['flood_events'] or 0) > 0]
            peak_month = max(flood_rows, key=lambda row: row['flood_events']) if flood_rows else None
            insights = []
            if rainfall_threshold is not None:
                insights.append(f"Flood signals are based on rainfall values at or above {round(rainfall_threshold, 2)} mm, which is the 90th percentile for the selected data.")
            insights.append(f"Simple wet-condition thresholds are also tracked as high rainfall ({high_threshold}+ mm), very high rainfall ({very_high_threshold}+ mm), and extreme rainfall ({extreme_threshold}+ mm).")
            if peak_month:
                insights.append(f"Flood-related rainfall activity peaked in {peak_month['label']} with {peak_month['flood_events']} high-rainfall records.")
            if hotspots:
                insights.append(f"{hotspots[0]['province']} recorded the highest concentration of flood-like rainfall events in the active view.")
            if 'SPI' in df.columns and not df['SPI'].dropna().empty:
                insights.append(f"{round(float((df['SPI'] > 1).mean() * 100), 1)}% of available SPI records are above 1, indicating wetter-than-normal conditions.")
            if 'SoilMoisture_pct' in df.columns and not df['SoilMoisture_pct'].dropna().empty:
                insights.append(f"Average soil moisture in the filtered data is {round(float(df['SoilMoisture_pct'].mean()), 1)}%, which helps indicate how saturated the ground may be.")

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
                    "max_rainfall": round(float(df['Rainfall_mm'].max()), 2) if 'Rainfall_mm' in df.columns and not df['Rainfall_mm'].dropna().empty else None,
                    "peak_month": peak_month['label'] if peak_month else None,
                    "avg_spi": round(float(df['SPI'].mean()), 2) if 'SPI' in df.columns and not df['SPI'].dropna().empty else None,
                    "avg_soil_moisture": round(float(df['SoilMoisture_pct'].mean()), 2) if 'SoilMoisture_pct' in df.columns and not df['SoilMoisture_pct'].dropna().empty else None
                },
                "extreme_rainfall": {
                    **extreme_rainfall_payload,
                    "top_rainfall_values": top_rainfall_values
                },
                "rainfall_trend": {"labels": [item['label'] for item in yearly_rainfall], "average_rainfall": [item['value'] for item in yearly_rainfall]},
                "spi_trend": {"labels": [item['label'] for item in spi_trend], "average_spi": [item['value'] for item in spi_trend]},
                "soil_moisture_trend": {"labels": [item['label'] for item in soil_moisture_trend], "average_soil_moisture": [item['value'] for item in soil_moisture_trend]},
                "province_rainfall": {"labels": [item['label'] for item in province_rainfall], "values": [item['value'] for item in province_rainfall]},
                "monthly_pattern": monthly_pattern_payload,
                "hotspots": hotspots,
                "insights": insights
            })
        except Exception as e:
            logger.error(f"Flood events error: {e}", exc_info=True)
            return error_response(str(e), 500)
