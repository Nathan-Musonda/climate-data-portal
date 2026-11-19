# utils/auth.py
import os
import secrets
import logging
from functools import wraps
from flask import request, jsonify

logger = logging.getLogger(__name__)

API_KEY = os.environ.get('API_KEY') or secrets.token_urlsafe(24)
ADMIN_TOKEN = os.environ.get('ADMIN_TOKEN') or secrets.token_urlsafe(24)

if not os.environ.get('API_KEY'):
    logger.warning("API_KEY not set; generated a random in-memory API key for this process.")
if not os.environ.get('ADMIN_TOKEN'):
    logger.warning("ADMIN_TOKEN not set; generated a random in-memory admin token for this process.")

def require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        if not api_key or api_key != API_KEY:
            return jsonify({
                "success": False, 
                "error": "Invalid or missing API key"
            }), 401
        return f(*args, **kwargs)
    return decorated

def require_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        admin_token = request.headers.get('X-Admin-Token')
        if not admin_token or admin_token != ADMIN_TOKEN:
            return jsonify({
                "success": False, 
                "error": "Admin access required"
            }), 403
        return f(*args, **kwargs)
    return decorated

def get_user_from_request():
    api_key = request.headers.get('X-API-Key')
    if api_key == API_KEY:
        return {"role": "user", "id": "api_user"}
    admin_token = request.headers.get('X-Admin-Token')
    if admin_token == ADMIN_TOKEN:
        return {"role": "admin", "id": "admin_user"}
    return {"role": "anonymous", "id": None}
