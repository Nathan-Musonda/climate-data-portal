from flask import Flask, jsonify, render_template
from flask_cors import CORS
from flask_caching import Cache
from flask import request, g
from flask import send_from_directory
from config import Config
from routes.api_v1_refactored import api_v1
from routes.page_routes import page_routes, render_error_page
import logging
import os
import time

DEFAULT_ZAMBIA_DISTRICT_GEOJSON_URL = (
    "https://services3.arcgis.com/BU6Aadhn6tbBEdyk/arcgis/rest/services/"
    "Zambia_Administrative_Boundaries_Districts_2020/FeatureServer/0/query"
    "?where=1%3D1&outFields=*&outSR=4326&f=geojson"
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def validate_runtime_config(app):
    warnings = []
    errors = []

    if Config.DEBUG:
        warnings.append(
            "APP_DEBUG is enabled; disable it outside local development.")
    is_debug = Config.DEBUG

    required_in_all_modes = {
        "SECRET_KEY": "SECRET_KEY is not set.",
        "DB_PASSWORD": "DB_PASSWORD is not set; database connections may fail."
    }
    required_in_production = {
        "API_KEY": "API_KEY is required when APP_DEBUG is False.",
        "ADMIN_TOKEN": "ADMIN_TOKEN is required when APP_DEBUG is False."
    }

    for key, message in required_in_all_modes.items():
        if not os.getenv(key):
            if is_debug:
                warnings.append(message)
            else:
                errors.append(message)

    for key, message in required_in_production.items():
        if not os.getenv(key):
            if is_debug:
                warnings.append(
                    f"{key} is not set; a random in-memory token will be generated at startup.")
            else:
                errors.append(message)

    for message in warnings:
        app.logger.warning(message)

    if errors:
        for message in errors:
            app.logger.error(message)
        raise RuntimeError(
            "Application configuration is incomplete. Check environment variables.")


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    district_geojson_url = (
        os.getenv("ZAMBIA_DISTRICT_GEOJSON_URL", "").strip()
        or DEFAULT_ZAMBIA_DISTRICT_GEOJSON_URL
    )
    app.config['DISTRICT_GEOJSON_URL'] = district_geojson_url

    CORS(app)

    # Setup cache
    app.config['CACHE_TYPE'] = app.config.get('CACHE_TYPE', 'SimpleCache')
    app.config['CACHE_DEFAULT_TIMEOUT'] = app.config.get(
        'CACHE_DEFAULT_TIMEOUT', 300)
    cache = Cache(app)

    app.register_blueprint(api_v1)
    app.register_blueprint(page_routes)
    validate_runtime_config(app)

    @app.before_request
    def start_request_timer():
        g.request_started_at = time.perf_counter()

    @app.after_request
    def log_api_request(response):
        if request.path.startswith('/api/'):
            started_at = getattr(g, 'request_started_at', None)
            duration_ms = round((time.perf_counter() - started_at)
                                * 1000, 2) if started_at else None
            app.logger.info(
                "API request path=%s method=%s status=%s duration_ms=%s",
                request.path,
                request.method,
                response.status_code,
                duration_ms
            )
        return response

    @app.errorhandler(404)
    def not_found(error):
        if request.path.startswith('/api/'):
            return jsonify({"error": "Route not found"}), 404
        return render_error_page(404, "Page not found")

    @app.route('/favicon.ico')
    def favicon():
        return send_from_directory(
            app.static_folder,
            'favicon.ico',
            mimetype='image/vnd.microsoft.icon'
        )

    @app.errorhandler(500)
    def server_error(error):
        logger.error(f"Server error: {error}")
        if request.path.startswith('/api/'):
            return jsonify({"error": "Internal server error"}), 500
        return render_error_page(500, "Internal server error")

    return app


app = create_app()

if __name__ == "__main__":
    logger.info("Starting Zambia Climate Data Visualization Portal")
    logger.info("Server running at http://localhost:5000")
    logger.info("Swagger docs available at http://localhost:5000/apidocs")
    app.run(debug=Config.DEBUG, host='0.0.0.0', port=5000)
