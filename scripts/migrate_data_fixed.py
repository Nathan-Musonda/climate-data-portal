# scripts/migrate_data_fixed.py
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from config import Config
import logging
import re

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def safe_int(value):
    if pd.isna(value):
        return None
    try:
        if isinstance(value, str):
            numbers = re.findall(r'\d+', value)
            if numbers:
                return int(numbers[0])
            return None
        return int(float(value))
    except (ValueError, TypeError):
        return None

def safe_float(value):
    if pd.isna(value):
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None

def migrate_csv_to_db(csv_path=None):
    conn = None
    try:
        # Use the deduped CSV file unless a source CSV is provided.
        csv_path = csv_path or Config.DATA_DIR / "cleaned_zambia_climate_data_deduped.csv"
        logger.info(f"Loading CSV from {csv_path}")
        df = pd.read_csv(csv_path)
        logger.info(f"Loaded {len(df)} records")
        
        conn = psycopg2.connect(
            host=Config.DB_HOST,
            port=Config.DB_PORT,
            user=Config.DB_USER,
            password=Config.DB_PASSWORD,
            database=Config.DB_NAME
        )
        cursor = conn.cursor()
        
        records = []
        for _, row in df.iterrows():
            record = (
                row.get('Date') if pd.notna(row.get('Date')) else None,
                int(row.get('Year')) if pd.notna(row.get('Year')) else None,
                int(row.get('Month')) if pd.notna(row.get('Month')) else None,
                row.get('MonthName') if pd.notna(row.get('MonthName')) else None,
                row.get('Province') if pd.notna(row.get('Province')) else None,
                row.get('District') if pd.notna(row.get('District')) else None,
                safe_float(row.get('Rainfall_mm')),
                safe_float(row.get('Temp_Max_C')),
                safe_float(row.get('Temp_Min_C')),
                safe_float(row.get('Humidity_pct')),
                safe_float(row.get('Evapotranspiration_mm')),
                safe_float(row.get('WindSpeed_mps')),
                safe_float(row.get('SolarRadiation_Wm2')),
                safe_float(row.get('SoilMoisture_pct')),
                safe_float(row.get('NDVI')),
                safe_float(row.get('SPI')),
                safe_float(row.get('SPEI')),
                safe_float(row.get('PDSI')),
                row.get('DroughtSeverity') if pd.notna(row.get('DroughtSeverity')) else None,
                safe_float(row.get('CropYield_kg_ha')),
                safe_float(row.get('LivestockMortality_pct')),
                safe_float(row.get('FoodPrice_ZMW')),
                safe_float(row.get('LakeKariba_Level_m')),
                safe_float(row.get('Hydropower_MW')),
                safe_int(row.get('PopulationAffected')),
                safe_int(row.get('ReliefInterventions'))
            )
            records.append(record)
        
        # Use DO NOTHING to skip duplicates
        insert_query = """
            INSERT INTO climate_records (
                date, year, month, month_name, province, district,
                rainfall_mm, temp_max_c, temp_min_c, humidity_pct,
                evapotranspiration_mm, wind_speed_mps, solar_radiation_wm2,
                soil_moisture_pct, ndvi, spi, spei, pdsi, drought_severity,
                crop_yield_kg_ha, livestock_mortality_pct, food_price_zmw,
                lake_kariba_level_m, hydropower_mw, population_affected,
                relief_interventions
            ) VALUES %s
            ON CONFLICT (date, province, district) DO NOTHING
        """
        
        execute_values(cursor, insert_query, records)
        conn.commit()
        
        logger.info(f"Successfully migrated {len(records)} records to database")
        
        cursor.execute("SELECT COUNT(*) FROM climate_records")
        count = cursor.fetchone()[0]
        logger.info(f"Total records in database: {count}")
        
        cursor.close()
    except Exception as e:
        logger.error(f"Migration error: {e}")
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    csv_path = sys.argv[1] if len(sys.argv) > 1 else None
    migrate_csv_to_db(csv_path)
