import sys
import os
import unittest
from datetime import date

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

from backend.routes.api_v1 import (
    _build_projection_series,
    build_explorer_trend,
    build_monthly_notification_items,
    build_site_summary_updates,
)
from backend.utils.aggregations import rainfall_trend, summarize_population_affected, temperature_trend
from backend.utils.monthly import (
    build_empty_monthly_chart_payload,
    build_empty_monthly_payload,
    build_monthly_chart_payload as build_shared_monthly_chart_payload,
    normalize_monthly_rows,
)


class TestDataHelpers(unittest.TestCase):
    def test_population_summary_uses_location_maxima(self):
        df = pd.DataFrame([
            {"district": "A", "month": 1, "PopulationAffected": 10},
            {"district": "A", "month": 1, "PopulationAffected": 15},
            {"district": "B", "month": 1, "PopulationAffected": 20},
            {"district": "A", "month": 2, "PopulationAffected": 5},
        ])

        overall = summarize_population_affected(df)
        by_month = summarize_population_affected(df, ["month"])

        self.assertEqual(overall, 35)
        self.assertEqual(by_month["PopulationAffected"].tolist(), [35, 5])

    def test_population_projection_series_uses_yearly_location_maxima(self):
        df = pd.DataFrame([
            {"year": 2024, "district": "A", "PopulationAffected": 10},
            {"year": 2024, "district": "A", "PopulationAffected": 15},
            {"year": 2024, "district": "B", "PopulationAffected": 20},
            {"year": 2025, "district": "A", "PopulationAffected": 5},
            {"year": 2025, "district": "A", "PopulationAffected": 7},
            {"year": 2025, "district": "B", "PopulationAffected": 30},
        ])

        series = _build_projection_series(df, "population", horizon=2)

        self.assertEqual(
            series["historical"],
            [
                {"year": 2024, "value": 35.0},
                {"year": 2025, "value": 37.0},
            ]
        )

    def test_monthly_notifications_fill_all_twelve_months_for_selected_district(self):
        df = pd.DataFrame([
            {"year": 2025, "month": 1, "district": "Kasempa", "province": "North-Western", "Rainfall_mm": 120, "Temp_Max_C": 31, "NDVI": 0.63, "DroughtSeverity": "Mild", "PopulationAffected": 10},
            {"year": 2025, "month": 8, "district": "Kasempa", "province": "North-Western", "Rainfall_mm": 4, "Temp_Max_C": 36, "NDVI": 0.24, "DroughtSeverity": "Severe", "PopulationAffected": 1200},
        ])

        items = build_monthly_notification_items(df, 2025, district_filter="Kasempa")

        self.assertEqual(len(items), 12)
        self.assertEqual([item["month"] for item in items], list(range(1, 13)))
        self.assertEqual(items[0]["title"], "Jan 2025")
        self.assertIn("Kasempa", items[1]["body"])
        self.assertIn("No climate records were available", items[1]["body"])

    def test_monthly_notifications_fill_all_twelve_months_for_all_districts(self):
        df = pd.DataFrame([
            {"year": 2024, "month": 2, "district": "Kasempa", "province": "North-Western", "Rainfall_mm": 80, "Temp_Max_C": 29, "NDVI": 0.52, "DroughtSeverity": "No Drought", "PopulationAffected": 0},
            {"year": 2024, "month": 2, "district": "Mwinilunga", "province": "North-Western", "Rainfall_mm": 95, "Temp_Max_C": 28, "NDVI": 0.61, "DroughtSeverity": "Mild", "PopulationAffected": 5},
            {"year": 2024, "month": 10, "district": "Sesheke", "province": "Western", "Rainfall_mm": 12, "Temp_Max_C": 34, "NDVI": 0.31, "DroughtSeverity": "Moderate", "PopulationAffected": 40},
        ])

        items = build_monthly_notification_items(df, 2024)

        self.assertEqual(len(items), 12)
        self.assertEqual([item["month"] for item in items], list(range(1, 13)))
        self.assertIn("districts across", items[1]["body"])
        self.assertIn("province reported", items[1]["body"])
        self.assertIn("No climate records were available", items[0]["body"])

    def test_monthly_notifications_fill_all_twelve_months_for_selected_province(self):
        df = pd.DataFrame([
            {"year": 2023, "month": 3, "district": "Kasempa", "province": "North-Western", "Rainfall_mm": 140, "Temp_Max_C": 30, "NDVI": 0.66, "DroughtSeverity": "Mild", "PopulationAffected": 15},
            {"year": 2023, "month": 3, "district": "Mwinilunga", "province": "North-Western", "Rainfall_mm": 155, "Temp_Max_C": 29, "NDVI": 0.68, "DroughtSeverity": "No Drought", "PopulationAffected": 0},
        ])

        items = build_monthly_notification_items(df, 2023, province_filter="North-Western")

        self.assertEqual(len(items), 12)
        self.assertEqual(items[2]["province"], "North-Western")
        self.assertIn("districts reported", items[2]["body"])
        self.assertIn("No climate records were available for North-Western", items[0]["body"])

    def test_rainfall_trend_uses_full_jan_to_dec_structure_for_partial_year(self):
        df = pd.DataFrame([
            {"year": 2025, "month": 1, "Rainfall_mm": 120},
            {"year": 2025, "month": 10, "Rainfall_mm": 45},
        ])

        trend = rainfall_trend(df)

        self.assertEqual(trend["period_type"], "month")
        self.assertEqual(trend["years"], ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])
        self.assertEqual(trend["month_numbers"], list(range(1, 13)))
        self.assertEqual(trend["month_labels"], ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])
        self.assertEqual(trend["avg_rainfall"][0], 120.0)
        self.assertIsNone(trend["avg_rainfall"][1])
        self.assertEqual(trend["avg_rainfall"][9], 45.0)
        self.assertIsNone(trend["avg_rainfall"][10])
        self.assertIsNone(trend["avg_rainfall"][11])
        self.assertEqual(trend["observed_month_count"], 2)
        self.assertFalse(trend["is_complete_period"])
        self.assertEqual(trend["missing_month_labels"], ["Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Nov", "Dec"])

    def test_temperature_trend_uses_full_jan_to_dec_structure_for_partial_year(self):
        df = pd.DataFrame([
            {"year": 2025, "month": 2, "Temp_Max_C": 33, "Temp_Min_C": 18},
            {"year": 2025, "month": 9, "Temp_Max_C": 36, "Temp_Min_C": 20},
        ])

        trend = temperature_trend(df)

        self.assertEqual(trend["period_type"], "month")
        self.assertEqual(trend["years"], ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])
        self.assertEqual(trend["month_numbers"], list(range(1, 13)))
        self.assertEqual(trend["month_labels"], ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])
        self.assertIsNone(trend["avg_max_temp"][0])
        self.assertEqual(trend["avg_max_temp"][1], 33.0)
        self.assertEqual(trend["avg_max_temp"][8], 36.0)
        self.assertIsNone(trend["avg_min_temp"][7])
        self.assertEqual(trend["avg_min_temp"][8], 20.0)
        self.assertEqual(trend["available_month_labels"], ["Feb", "Sep"])
        self.assertEqual(trend["missing_month_labels"], ["Jan", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Oct", "Nov", "Dec"])

    def test_explorer_trend_uses_full_jan_to_dec_structure_for_partial_year(self):
        df = pd.DataFrame([
            {"year": 2025, "month": 2, "Rainfall_mm": 98},
            {"year": 2025, "month": 10, "Rainfall_mm": 41},
        ])

        chart = build_explorer_trend(df, "Rainfall_mm")

        self.assertEqual(chart["period_type"], "month")
        self.assertEqual(chart["labels"], ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])
        self.assertEqual(chart["month_numbers"], list(range(1, 13)))
        self.assertEqual(chart["month_labels"], ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])
        self.assertIsNone(chart["values"][0])
        self.assertEqual(chart["values"][1], 98.0)
        self.assertEqual(chart["values"][9], 41.0)
        self.assertIsNone(chart["values"][10])
        self.assertEqual(chart["observed_month_count"], 2)
        self.assertFalse(chart["is_complete_period"])

    def test_shared_monthly_helper_normalizes_sparse_rows_with_null_fill(self):
        normalized = normalize_monthly_rows(
            [
                {"month": 1, "value": 4.2},
                {"month": 2, "value": 3.1},
                {"month": 4, "value": 6.9},
                {"month": 8, "value": 12.0},
            ],
            ["value"]
        )

        self.assertEqual(normalized["labels"], ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])
        self.assertEqual([row["month"] for row in normalized["rows"]], list(range(1, 13)))
        self.assertEqual([row["value"] for row in normalized["rows"]][0], 4.2)
        self.assertEqual([row["value"] for row in normalized["rows"]][1], 3.1)
        self.assertIsNone([row["value"] for row in normalized["rows"]][2])
        self.assertEqual([row["value"] for row in normalized["rows"]][3], 6.9)
        self.assertEqual([row["value"] for row in normalized["rows"]][7], 12.0)
        self.assertIsNone([row["value"] for row in normalized["rows"]][11])

    def test_shared_monthly_helper_supports_zero_fill_when_zero_is_semantically_correct(self):
        payload = build_empty_monthly_payload(["total_rainfall"], fill_values={"total_rainfall": 0})

        self.assertEqual(payload["labels"], ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])
        self.assertEqual(payload["month_numbers"], list(range(1, 13)))
        self.assertEqual(payload["total_rainfall"], [0] * 12)

    def test_shared_monthly_chart_payload_uses_standard_month_contract(self):
        payload, rows = build_shared_monthly_chart_payload(
            [
                {"month": 1, "value": 4.2},
                {"month": 4, "value": 6.9},
                {"month": 8, "value": 12.0},
            ],
            ["value"]
        )

        self.assertEqual(payload["period_type"], "month")
        self.assertEqual(payload["years"], ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])
        self.assertEqual(payload["labels"], ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])
        self.assertEqual(payload["month_numbers"], list(range(1, 13)))
        self.assertEqual(payload["value"][0], 4.2)
        self.assertIsNone(payload["value"][1])
        self.assertEqual(payload["value"][3], 6.9)
        self.assertEqual(payload["value"][7], 12.0)
        self.assertEqual([row["month"] for row in rows], list(range(1, 13)))

    def test_shared_empty_monthly_chart_payload_returns_standardized_empty_shape(self):
        payload = build_empty_monthly_chart_payload(["value"])

        self.assertEqual(payload["period_type"], "month")
        self.assertEqual(payload["years"], ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])
        self.assertEqual(payload["labels"], ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])
        self.assertEqual(len(payload["value"]), 12)
        self.assertEqual(payload["observed_month_count"], 0)
        self.assertFalse(payload["is_complete_period"])

    def test_explorer_trend_force_monthly_returns_empty_twelve_month_skeleton(self):
        chart = build_explorer_trend(
            pd.DataFrame(columns=["year", "month", "Rainfall_mm"]),
            "Rainfall_mm",
            force_monthly=True
        )

        self.assertEqual(chart["period_type"], "month")
        self.assertEqual(chart["labels"], ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])
        self.assertEqual(chart["month_numbers"], list(range(1, 13)))
        self.assertEqual(len(chart["values"]), 12)
        self.assertEqual(chart["observed_month_count"], 0)
        self.assertFalse(chart["is_complete_period"])

    def test_site_summary_updates_include_coverage_and_prioritized_signal(self):
        summary = build_site_summary_updates(
            total_records=15604,
            provinces=["Lusaka", "Southern", "Western"],
            district_count=116,
            years=[2015, 2025],
            yearly_summaries=[
                {
                    "year": 2025,
                    "rainfall": [{"province": "Western", "value": 182.4}],
                    "temperature": [{"province": "Lusaka", "value": 34.2}],
                    "drought": [{"province": "Southern", "value": 2.35}],
                    "ndvi": [{"province": "Northern", "value": 0.612}]
                }
            ],
            district_summaries=[
                {
                    "district": "Kasempa",
                    "province": "North-Western",
                    "avg_rainfall": 120.4,
                    "avg_temp_max": 31.1,
                    "avg_drought_score": 0.8,
                    "avg_ndvi": 0.638
                },
                {
                    "district": "Sesheke",
                    "province": "Western",
                    "avg_rainfall": 18.2,
                    "avg_temp_max": 36.4,
                    "avg_drought_score": 2.2,
                    "avg_ndvi": 0.241
                }
            ],
            latest_daily_district_records=[
                {
                    "district": "Kasempa",
                    "province": "North-Western",
                    "date": date(2025, 10, 29),
                    "rainfall_mm": 16.2,
                    "temp_max_c": 31.8,
                    "ndvi": 0.641,
                    "drought_severity": "Mild",
                    "population_affected": 15
                },
                {
                    "district": "Sesheke",
                    "province": "Western",
                    "date": date(2025, 10, 27),
                    "rainfall_mm": 4.5,
                    "temp_max_c": 38.2,
                    "ndvi": 0.211,
                    "drought_severity": "Severe",
                    "population_affected": 1400
                }
            ],
            latest_monthly_district_records=[
                {
                    "district": "Kasempa",
                    "province": "North-Western",
                    "year": 2025,
                    "month": 10,
                    "avg_rainfall": 82.4,
                    "avg_temp_max": 30.6,
                    "avg_drought_score": 0.7,
                    "avg_ndvi": 0.632,
                    "population_affected": 15
                },
                {
                    "district": "Sesheke",
                    "province": "Western",
                    "year": 2025,
                    "month": 9,
                    "avg_rainfall": 9.5,
                    "avg_temp_max": 37.3,
                    "avg_drought_score": 2.1,
                    "avg_ndvi": 0.228,
                    "population_affected": 1400
                }
            ],
            latest_year_df=pd.DataFrame([
                {
                    "year": 2025,
                    "month": 1,
                    "province": "Western",
                    "district": "Sesheke",
                    "Rainfall_mm": 200.0,
                    "Temp_Max_C": 39.0,
                    "DroughtSeverity": "Severe",
                    "PopulationAffected": 2200
                },
                {
                    "year": 2025,
                    "month": 2,
                    "province": "Western",
                    "district": "Kaoma",
                    "Rainfall_mm": 180.0,
                    "Temp_Max_C": 36.0,
                    "DroughtSeverity": "Moderate",
                    "PopulationAffected": 450
                },
                {
                    "year": 2025,
                    "month": 8,
                    "province": "Southern",
                    "district": "Gwembe",
                    "Rainfall_mm": 5.0,
                    "Temp_Max_C": 41.0,
                    "DroughtSeverity": "Severe",
                    "PopulationAffected": 5100
                }
            ])
        )

        self.assertEqual(summary["climate_updates"][0]["kind"], "coverage")
        self.assertIn("2015-2025", summary["climate_updates"][0]["date_label"])
        self.assertTrue(any(update["kind"] == "district-daily-feed" for update in summary["climate_updates"]))
        self.assertTrue(any(update["kind"] == "district-monthly-feed" for update in summary["climate_updates"]))
        self.assertTrue(any(update["kind"] == "district-daily-update" for update in summary["climate_updates"]))
        self.assertTrue(any(update["kind"] == "district-monthly-update" for update in summary["climate_updates"]))
        self.assertTrue(any(update["kind"] == "district-feed" for update in summary["climate_updates"]))
        self.assertTrue(any(update["kind"] == "severe-drought-events" for update in summary["climate_updates"]))
        self.assertTrue(any(update["kind"] == "flood-risk-events" for update in summary["climate_updates"]))
        self.assertTrue(any(update["kind"] == "heat-events" for update in summary["climate_updates"]))
        self.assertTrue(any(update["kind"] == "impact-events" for update in summary["climate_updates"]))
        self.assertEqual(len(summary["district_updates"]), 2)
        self.assertEqual(summary["district_updates"][0]["district"], "Kasempa")
        self.assertTrue(any("Coverage update" in item for item in summary["ticker_items"]))
        self.assertTrue(any("Kasempa" in item for item in summary["ticker_items"]))
        self.assertTrue(any("impact watch" in item.lower() for item in summary["ticker_items"]))


if __name__ == '__main__':
    unittest.main()
