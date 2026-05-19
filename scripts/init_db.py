# scripts/init_db.py
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
from config import Config
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_database():
    """Create database if it doesn't exist"""
    conn = None
    try:
        conn = psycopg2.connect(
            host=Config.DB_HOST,
            port=Config.DB_PORT,
            user=Config.DB_USER,
            password=Config.DB_PASSWORD,
            database='postgres'
        )
        conn.autocommit = True
        cursor = conn.cursor()
        
        cursor.execute(f"SELECT 1 FROM pg_database WHERE datname = '{Config.DB_NAME}'")
        if not cursor.fetchone():
            cursor.execute(f"CREATE DATABASE {Config.DB_NAME}")
            logger.info(f"Database {Config.DB_NAME} created successfully")
        else:
            logger.info(f"Database {Config.DB_NAME} already exists")
        
        cursor.close()
    except Exception as e:
        logger.error(f"Error creating database: {e}")
        raise
    finally:
        if conn:
            conn.close()

def create_tables():
    """Create all tables"""
    conn = None
    try:
        conn = psycopg2.connect(
            host=Config.DB_HOST,
            port=Config.DB_PORT,
            user=Config.DB_USER,
            password=Config.DB_PASSWORD,
            database=Config.DB_NAME
        )
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS climate_records (
                id SERIAL PRIMARY KEY,
                date DATE NOT NULL,
                year INTEGER NOT NULL,
                month INTEGER NOT NULL,
                month_name VARCHAR(20),
                province VARCHAR(100) NOT NULL,
                district VARCHAR(100) NOT NULL,
                rainfall_mm DECIMAL(8,2),
                temp_max_c DECIMAL(5,2),
                temp_min_c DECIMAL(5,2),
                humidity_pct DECIMAL(5,2),
                evapotranspiration_mm DECIMAL(8,2),
                wind_speed_mps DECIMAL(5,2),
                solar_radiation_wm2 DECIMAL(8,2),
                soil_moisture_pct DECIMAL(5,2),
                ndvi DECIMAL(5,3),
                spi DECIMAL(5,2),
                spei DECIMAL(5,2),
                pdsi DECIMAL(5,2),
                drought_severity VARCHAR(50),
                crop_yield_kg_ha DECIMAL(10,2),
                livestock_mortality_pct DECIMAL(5,2),
                food_price_zmw DECIMAL(10,2),
                lake_kariba_level_m DECIMAL(6,2),
                hydropower_mw DECIMAL(10,2),
                population_affected INTEGER,
                relief_interventions INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(date, province, district)
            )
        """)
        
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_year ON climate_records(year)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_province ON climate_records(province)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_district ON climate_records(district)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_date ON climate_records(date)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_drought_severity ON climate_records(drought_severity)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_year_province ON climate_records(year, province)")
        
        conn.commit()
        logger.info("Tables created successfully")
        cursor.close()
    except Exception as e:
        logger.error(f"Error creating tables: {e}")
        raise
    finally:
        if conn:
            conn.close()

def main():
    logger.info("Starting database initialization...")
    create_database()
    create_tables()
    logger.info("Database initialization complete!")

if __name__ == "__main__":
    main()
