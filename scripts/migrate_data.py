# scripts/migrate_data.py
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from config import Config
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate_csv_to_db():
    conn = None
    try:
        csv_path = Config.DATA_FILE
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
                float(row.get('Rainfall_mm')) if pd.notna(row.get('Rainfall_mm')) else None,
                float(row.get('Temp_Max_C')) if pd.notna(row.get('Temp_Max_C')) else None,
                float(row.get('Temp_Min_C')) if pd.notna(row.get('Temp_Min_C')) else None,
                float(row.get('Humidity_pct')) if pd.notna(row.get('Humidity_pct')) else None,
                float(row.get('Evapotranspiration_mm')) if pd.notna(row.get('Evapotranspiration_mm')) else None,
                float(row.get('WindSpeed_mps')) if pd.notna(row.get('WindSpeed_mps')) else None,
                float(row.get('SolarRadiation_Wm2')) if pd.notna(row.get('SolarRadiation_Wm2')) else None,
                float(row.get('SoilMoisture_pct')) if pd.notna(row.get('SoilMoisture_pct')) else None,
                float(row.get('NDVI')) if pd.notna(row.get('NDVI')) else None,
                float(row.get('SPI')) if pd.notna(row.get('SPI')) else None,
                float(row.get('SPEI')) if pd.notna(row.get('SPEI')) else None,
                float(row.get('PDSI')) if pd.notna(row.get('PDSI')) else None,
                row.get('DroughtSeverity') if pd.notna(row.get('DroughtSeverity')) else None,
                float(row.get('CropYield_kg_ha')) if pd.notna(row.get('CropYield_kg_ha')) else None,
                float(row.get('LivestockMortality_pct')) if pd.notna(row.get('LivestockMortality_pct')) else None,
                float(row.get('FoodPrice_ZMW')) if pd.notna(row.get('FoodPrice_ZMW')) else None,
                float(row.get('LakeKariba_Level_m')) if pd.notna(row.get('LakeKariba_Level_m')) else None,
                float(row.get('Hydropower_MW')) if pd.notna(row.get('Hydropower_MW')) else None,
                int(row.get('PopulationAffected')) if pd.notna(row.get('PopulationAffected')) else None,
                int(float(row.get('ReliefInterventions'))) if pd.notna(row.get('ReliefInterventions')) and str(row.get('ReliefInterventions')).replace('.', '').isdigit() else None
            )
            records.append(record)
        
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
            ON CONFLICT (date, province, district) DO UPDATE SET
                rainfall_mm = EXCLUDED.rainfall_mm,
                temp_max_c = EXCLUDED.temp_max_c,
                updated_at = CURRENT_TIMESTAMP
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
    migrate_csv_to_db()
