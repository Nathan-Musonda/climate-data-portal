# tests/test_api.py
import sys
import os
import unittest

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app


class TestClimateAPI(unittest.TestCase):
    CANONICAL_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.client = cls.app.test_client()

    def get_json(self, path):
        response = self.client.get(path)
        return response, response.get_json()

    def assert_monthly_payload_shape(self, payload, keys):
        self.assertEqual(payload['period_type'], 'month')
        self.assertEqual(payload['years'], self.CANONICAL_MONTHS)
        self.assertEqual(payload['labels'], self.CANONICAL_MONTHS)
        self.assertEqual(payload['month_numbers'], list(range(1, 13)))
        self.assertEqual(payload['month_labels'], self.CANONICAL_MONTHS)
        self.assertEqual(len(payload['available_months']), payload['observed_month_count'])
        self.assertEqual(len(payload['missing_months']), 12 - payload['observed_month_count'])
        for key in keys:
            self.assertIn(key, payload)
            self.assertEqual(len(payload[key]), 12)

    def test_health_endpoint(self):
        response, data = self.get_json('/api/v1/health')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(data['success'])
        self.assertEqual(data['data']['status'], 'healthy')

    def test_filter_options_endpoints(self):
        for path in ['/api/v1/provinces', '/api/v1/years', '/api/v1/districts']:
            response, data = self.get_json(path)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(data['success'])
            self.assertIsInstance(data['data'], list)

    def test_overview_endpoint(self):
        response, data = self.get_json('/api/v1/overview')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(data['success'])
        self.assertIn('total_records', data['data'])

    def test_invalid_year_returns_empty_overview(self):
        response, data = self.get_json('/api/v1/overview?year=9999')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(data['success'])
        self.assertEqual(data['data']['total_records'], 0)

    def test_trend_endpoints(self):
        for path, key in [
            ('/api/v1/rainfall-trend', 'avg_rainfall'),
            ('/api/v1/temperature-trend', 'avg_max_temp'),
            ('/api/v1/drought-trend', 'avg_drought_score'),
            ('/api/v1/ndvi-trend', 'avg_ndvi'),
            ('/api/v1/soil-moisture-trend', 'avg_soil_moisture'),
            ('/api/v1/impact-trends', 'population_affected'),
        ]:
            response, data = self.get_json(path)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(data['success'])
            self.assertIn(key, data['data'])

    def test_flood_events_endpoint(self):
        response, data = self.get_json('/api/v1/flood-events')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(data['success'])
        payload = data['data']
        self.assertIn('summary', payload)
        self.assertIn('monthly_pattern', payload)
        self.assertIn('hotspots', payload)
        self.assertGreaterEqual(payload['summary']['flood_event_count'], 0)
        top_locations = [
            item['location']
            for item in payload['extreme_rainfall'].get('top_rainfall_values', [])
            if item.get('location')
        ]
        self.assertEqual(len(top_locations), len(set(top_locations)))

    def test_extreme_events_endpoint(self):
        response, data = self.get_json('/api/v1/extreme-events')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(data['success'])
        payload = data['data']
        self.assertIn('summary', payload)
        self.assertIn('monthly', payload)
        self.assertIn('hotspots', payload)

    def test_district_summary_endpoint(self):
        response, data = self.get_json('/api/v1/district-summary?district=Lusaka&year=2025')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(data['success'])
        self.assertEqual(data['data']['district'], 'Lusaka')

    def test_district_monthly_notifications_endpoint(self):
        response, data = self.get_json('/api/v1/district-monthly-notifications')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(data['success'])
        payload = data['data']
        self.assertIn('items', payload)
        self.assertIn('item_count', payload)
        self.assertIn('district_count', payload)
        self.assertIn('month_count', payload)
        self.assertIsInstance(payload['items'], list)

    def test_district_comparison_endpoint(self):
        response, data = self.get_json('/api/v1/district-comparison?districts=Lusaka,Ndola&focus_metric=rainfall')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(data['success'])
        self.assertIn('comparison', data['data'])
        self.assertIn('trend', data['data'])

    def test_district_comparison_has_no_default_districts(self):
        response, data = self.get_json('/api/v1/district-comparison?focus_metric=rainfall')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(data['success'])
        self.assertEqual(data['data']['districts'], [])
        self.assertEqual(data['data']['comparison']['labels'], [])
        self.assertEqual(data['data']['table'], [])

    def test_projections_endpoint(self):
        response, data = self.get_json('/api/v1/projections?horizon=3')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(data['success'])
        self.assertEqual(data['data']['horizon'], 3)
        self.assertIn('series', data['data'])
        self.assertGreaterEqual(len(data['data']['series']), 1)
        first_series = data['data']['series'][0]
        self.assertIn('historical', first_series)
        self.assertIn('projected', first_series)
        self.assertIn('scenario_projected', first_series)
        self.assertIn('scenarios', first_series)

        population_series = next(
            (item for item in data['data']['series'] if item.get('metric') == 'population'),
            None
        )
        self.assertIsNotNone(population_series)
        _, impact_data = self.get_json('/api/v1/impact-trends')
        expected_history = [
            {"year": int(year), "value": float(value)}
            for year, value in zip(
                impact_data['data']['labels'],
                impact_data['data']['population_affected']
            )
        ]
        self.assertEqual(population_series['historical'], expected_history)

    def test_projections_endpoint_supports_rcp_target_year(self):
        response, data = self.get_json('/api/v1/projections?scenario=rcp85&target_year=2050')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(data['success'])
        self.assertEqual(data['data']['selected_scenario'], 'rcp85')
        self.assertEqual(data['data']['target_year'], 2050)
        self.assertIn('rcp45', data['data']['scenario_options'])
        self.assertIn('rcp85', data['data']['scenario_options'])
        first_series = data['data']['series'][0]
        self.assertGreaterEqual(len(first_series['scenario_projected']), 1)
        first_point = first_series['scenario_projected'][0]
        self.assertIn('low', first_point)
        self.assertIn('high', first_point)

    def test_explorer_endpoint(self):
        response, data = self.get_json('/api/v1/explorer?variable=Rainfall_mm&province=all')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(data['success'])
        self.assertIn('chart', data['data'])
        self.assertIn('table', data['data'])

    def test_empty_monthly_trend_endpoints_return_twelve_month_shape(self):
        for path, keys in [
            ('/api/v1/rainfall-trend?year=9999', ['avg_rainfall']),
            ('/api/v1/temperature-trend?year=9999', ['avg_max_temp', 'avg_min_temp']),
            ('/api/v1/drought-trend?year=9999', ['avg_drought_score', 'severe_pct', 'moderate_pct']),
            ('/api/v1/ndvi-trend?year=9999', ['avg_ndvi']),
            ('/api/v1/soil-moisture-trend?year=9999', ['avg_soil_moisture']),
            ('/api/v1/impact-trends?year=9999', ['crop_yield', 'population_affected', 'hydropower_mw', 'lake_kariba_level', 'food_price_zmw']),
        ]:
            response, data = self.get_json(path)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(data['success'])
            self.assert_monthly_payload_shape(data['data'], keys)

    def test_empty_event_endpoints_return_twelve_month_shape(self):
        response, data = self.get_json('/api/v1/extreme-events?year=9999')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(data['success'])
        self.assert_monthly_payload_shape(
            data['data']['monthly'],
            ['heat_events', 'heavy_rainfall_events', 'severe_drought_events', 'population_affected']
        )

        response, data = self.get_json('/api/v1/flood-events?year=9999')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(data['success'])
        self.assert_monthly_payload_shape(
            data['data']['extreme_rainfall'],
            ['high_rainfall_events', 'very_high_rainfall_events', 'extreme_rainfall_events']
        )
        self.assert_monthly_payload_shape(
            data['data']['monthly_pattern'],
            ['flood_events', 'population_affected', 'average_rainfall']
        )

    def test_explorer_same_empty_year_returns_monthly_skeleton(self):
        response, data = self.get_json('/api/v1/explorer?variable=Rainfall_mm&start_year=9999&end_year=9999')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(data['success'])
        chart = data['data']['chart']
        self.assertEqual(chart['period_type'], 'month')
        self.assert_monthly_payload_shape(chart, ['values'])

    def test_site_summary_endpoint(self):
        response, data = self.get_json('/api/v1/site-summary')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(data['success'])
        self.assertIn('latest_year', data['data'])
        self.assertIn('yearly_summaries', data['data'])
        self.assertIn('climate_updates', data['data'])
        self.assertIn('ticker_items', data['data'])
        self.assertIn('district_updates', data['data'])

    def test_rankings_endpoint(self):
        response, data = self.get_json('/api/v1/rankings/population?year=2024')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(data['success'])
        self.assertEqual(data['data']['metric'], 'population')
        self.assertIsInstance(data['data']['rankings'], list)


if __name__ == '__main__':
    unittest.main()
