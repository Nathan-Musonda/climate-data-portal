# utils/responses.py
from flask import jsonify


def success_response(data, message=None, status_code=200):
    """Return consistent success response"""
    response = {
        "success": True,
        "data": data
    }
    if message:
        response["message"] = message
    return jsonify(response), status_code


def error_response(message, status_code=400, details=None):
    """Return consistent error response"""
    response = {
        "success": False,
        "error": message
    }
    if details:
        response["details"] = details
    return jsonify(response), status_code


def empty_response(message="No data found for selected filters"):
    """Return consistent empty data response"""
    return success_response([], message=message)
