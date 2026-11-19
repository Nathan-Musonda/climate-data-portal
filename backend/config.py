import os
import secrets
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from the project root.
load_dotenv(ROOT_DIR / ".env")

class Config:
    # App settings
    APP_NAME = "Zambia Climate Data Visualization Portal"
    DEBUG = os.getenv('APP_DEBUG', 'False').lower() == 'true'
    SECRET_KEY = os.getenv('SECRET_KEY') or secrets.token_urlsafe(32)
    API_VERSION = os.getenv('API_VERSION', '1.0.0')
    
    # Paths
    BASE_DIR = Path(__file__).resolve().parent
    ROOT_DIR = ROOT_DIR
    FRONTEND_DIR = ROOT_DIR / "frontend"
    TEMPLATE_DIR = FRONTEND_DIR / "templates"
    STATIC_DIR = FRONTEND_DIR / "static"
    LOG_DIR = BASE_DIR / "logs"
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
    LIVE_WEATHER_PERSIST_ENABLED = os.getenv('LIVE_WEATHER_PERSIST_ENABLED', 'true').lower() in {'1', 'true', 'yes', 'on'}
    LIVE_WEATHER_HISTORY_DEFAULT_LIMIT = int(os.getenv('LIVE_WEATHER_HISTORY_DEFAULT_LIMIT', '100'))

    # Daily district ingestion settings
    DAILY_WEATHER_API_URL = os.getenv('DAILY_WEATHER_API_URL', '')
    DAILY_WEATHER_API_KEY = os.getenv('DAILY_WEATHER_API_KEY', '')
