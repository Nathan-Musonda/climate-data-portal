import os
import secrets
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Config:
    # App settings
    APP_NAME = "Zambia Climate Data Visualization Portal"
    DEBUG = os.getenv('APP_DEBUG', 'False').lower() == 'true'
    SECRET_KEY = os.getenv('SECRET_KEY') or secrets.token_urlsafe(32)
    API_VERSION = os.getenv('API_VERSION', '1.0.0')
    
    # Paths
    BASE_DIR = Path(__file__).parent
    DATA_DIR = BASE_DIR / "data" / "processed"
    DATA_FILE = DATA_DIR / "cleaned_zambia_climate_data.csv"
    
    # Database settings
    DB_HOST = os.getenv('DB_HOST', 'localhost')
    DB_PORT = os.getenv('DB_PORT', '5432')
    DB_NAME = os.getenv('DB_NAME', 'zambia_climate_portal')
    DB_USER = os.getenv('DB_USER', 'postgres')
    DB_PASSWORD = os.getenv('DB_PASSWORD', '')
    
    # Cache settings
    CACHE_TYPE = os.getenv('CACHE_TYPE', 'SimpleCache')
    CACHE_DEFAULT_TIMEOUT = int(os.getenv('CACHE_DEFAULT_TIMEOUT', '300'))

    # Live weather settings
    LIVE_WEATHER_API_URL = os.getenv('LIVE_WEATHER_API_URL', '')
    LIVE_WEATHER_API_KEY = os.getenv('LIVE_WEATHER_API_KEY', '')
    LIVE_WEATHER_TIMEOUT_SECONDS = float(os.getenv('LIVE_WEATHER_TIMEOUT_SECONDS', '6'))
    LIVE_WEATHER_CACHE_TTL_SECONDS = int(os.getenv('LIVE_WEATHER_CACHE_TTL_SECONDS', '300'))

    # Daily district ingestion settings
    DAILY_WEATHER_API_URL = os.getenv('DAILY_WEATHER_API_URL', '')
    DAILY_WEATHER_API_KEY = os.getenv('DAILY_WEATHER_API_KEY', '')
