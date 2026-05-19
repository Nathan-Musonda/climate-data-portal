# utils/data_loader.py
import pandas as pd
import logging
import time
from utils.database import db_manager

logger = logging.getLogger(__name__)
_FILTER_OPTIONS_CACHE = {"value": None, "expires_at": 0}
_FULL_DATA_CACHE = {"value": None, "expires_at": 0}
FILTER_OPTIONS_TTL_SECONDS = 600
FULL_DATA_TTL_SECONDS = 120

NUMERIC_COLUMNS = [
    'year',
    'month',
    'Rainfall_mm',
    'Temp_Max_C',
    'Temp_Min_C',
    'Humidity_pct',
    'Evapotranspiration_mm',
    'WindSpeed_mps',
    'SolarRadiation_Wm2',
    'SoilMoisture_pct',
    'NDVI',
    'SPI',
    'SPEI',
    'PDSI',
    'CropYield_kg_ha',
    'LivestockMortality_pct',
    'FoodPrice_ZMW',
    'LakeKariba_Level_m',
    'Hydropower_MW',
    'PopulationAffected'
]

DB_TO_APP_COLUMN_MAPPING = {
    'rainfall_mm': 'Rainfall_mm',
    'temp_max_c': 'Temp_Max_C',
    'temp_min_c': 'Temp_Min_C',
    'humidity_pct': 'Humidity_pct',
    'evapotranspiration_mm': 'Evapotranspiration_mm',
    'wind_speed_mps': 'WindSpeed_mps',
    'solar_radiation_wm2': 'SolarRadiation_Wm2',
    'soil_moisture_pct': 'SoilMoisture_pct',
    'ndvi': 'NDVI',
    'spi': 'SPI',
    'spei': 'SPEI',
    'pdsi': 'PDSI',
    'drought_severity': 'DroughtSeverity',
    'crop_yield_kg_ha': 'CropYield_kg_ha',
    'livestock_mortality_pct': 'LivestockMortality_pct',
    'food_price_zmw': 'FoodPrice_ZMW',
    'lake_kariba_level_m': 'LakeKariba_Level_m',
    'hydropower_mw': 'Hydropower_MW',
    'population_affected': 'PopulationAffected',
    'relief_interventions': 'ReliefInterventions'
}
APP_TO_DB_COLUMN_MAPPING = {value: key for key, value in DB_TO_APP_COLUMN_MAPPING.items()}

def load_data_from_db(filters=None, columns=None):
    """
    Load climate data from database with optional filters
    """
    try:
        normalized_filters = filters or {}
        use_full_cache = not normalized_filters and not columns

        if use_full_cache and _FULL_DATA_CACHE["value"] is not None and _FULL_DATA_CACHE["expires_at"] > time.time():
            return _FULL_DATA_CACHE["value"].copy()

        # Build query
        selected_columns = "*"
        if columns:
            db_columns = []
            for column in columns:
                resolved = APP_TO_DB_COLUMN_MAPPING.get(column, column)
                if resolved not in db_columns:
                    db_columns.append(resolved)
            selected_columns = ", ".join(db_columns) if db_columns else "*"

        query = f"SELECT {selected_columns} FROM climate_records WHERE 1=1"
        params = []
        
        if normalized_filters:
            if normalized_filters.get('province'):
                query += " AND province = %s"
                params.append(normalized_filters['province'])
            if normalized_filters.get('district'):
                query += " AND district = %s"
                params.append(normalized_filters['district'])
            if normalized_filters.get('year'):
                query += " AND year = %s"
                params.append(normalized_filters['year'])
            if normalized_filters.get('month'):
                query += " AND month = %s"
                params.append(normalized_filters['month'])
        
        query += " ORDER BY date DESC"
        
        # Execute query
        logger.info(f"Executing query: {query[:100]}...")
        results = db_manager.execute_query(query, params)
        
        if not results:
            logger.warning("No results returned from database")
            return pd.DataFrame()
        
        # Convert to DataFrame
        df = pd.DataFrame(results)
        logger.info(f"Loaded {len(df)} records from database")
        
        # Rename columns to match original naming convention
        # Only rename columns that exist
        existing_mapping = {k: v for k, v in DB_TO_APP_COLUMN_MAPPING.items() if k in df.columns}
        df = df.rename(columns=existing_mapping)

        for column in NUMERIC_COLUMNS:
            if column in df.columns:
                df[column] = pd.to_numeric(df[column], errors='coerce')

        if use_full_cache:
            _FULL_DATA_CACHE["value"] = df.copy()
            _FULL_DATA_CACHE["expires_at"] = time.time() + FULL_DATA_TTL_SECONDS
        
        return df
        
    except Exception as e:
        logger.error(f"Error loading data from database: {e}", exc_info=True)
        return pd.DataFrame()

def get_filter_options_from_db():
    """Get available filter options from database"""
    try:
        if _FILTER_OPTIONS_CACHE["value"] is not None and _FILTER_OPTIONS_CACHE["expires_at"] > time.time():
            return dict(_FILTER_OPTIONS_CACHE["value"])

        options = {}
        
        # Get provinces
        provinces = db_manager.execute_query(
            "SELECT DISTINCT province FROM climate_records ORDER BY province"
        )
        options['provinces'] = [p['province'] for p in provinces] if provinces else []
        
        # Get districts
        districts = db_manager.execute_query(
            "SELECT DISTINCT district FROM climate_records ORDER BY district"
        )
        options['districts'] = [d['district'] for d in districts] if districts else []
        
        # Get years
        years = db_manager.execute_query(
            "SELECT DISTINCT year FROM climate_records ORDER BY year"
        )
        options['years'] = [y['year'] for y in years] if years else []
        
        # Get months
        months = db_manager.execute_query(
            "SELECT DISTINCT month FROM climate_records ORDER BY month"
        )
        options['months'] = [m['month'] for m in months] if months else []
        
        _FILTER_OPTIONS_CACHE["value"] = dict(options)
        _FILTER_OPTIONS_CACHE["expires_at"] = time.time() + FILTER_OPTIONS_TTL_SECONDS
        return options
        
    except Exception as e:
        logger.error(f"Error getting filter options: {e}", exc_info=True)
        return {"provinces": [], "districts": [], "years": [], "months": []}
