# utils/validation.py
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

def validate_year(year):
    """Validate year parameter"""
    if not year or str(year).lower() == 'all':
        return None, None
    try:
        year_int = int(year)
        if 2015 <= year_int <= 2025:
            return year_int, None
        return None, f"Year must be between 2015 and 2025, got {year_int}"
    except (ValueError, TypeError):
        return None, f"Year must be a number, got '{year}'"

def validate_month(month):
    """Validate month parameter"""
    if not month or str(month).lower() == 'all':
        return None, None
    try:
        month_int = int(month)
        if 1 <= month_int <= 12:
            return month_int, None
        return None, f"Month must be between 1 and 12, got {month_int}"
    except (ValueError, TypeError):
        return None, f"Month must be a number, got '{month}'"

def validate_province(province, valid_provinces):
    """Validate province parameter"""
    if not province or str(province).lower() == 'all':
        return None, None
    matching = [p for p in valid_provinces if p.lower() == province.lower()]
    if matching:
        return matching[0], None
    preview = valid_provinces[:5]
    return None, f"Invalid province '{province}'. Valid provinces: {', '.join(preview)}..."

def validate_climate_record(record):
    """Validate a climate record before insertion"""
    errors = []
    
    required_fields = ['date', 'province', 'district']
    for field in required_fields:
        if not record.get(field):
            errors.append(f"Missing required field: {field}")
    
    if record.get('date'):
        try:
            date_obj = datetime.strptime(record['date'], '%Y-%m-%d')
            if date_obj > datetime.now():
                errors.append("Date cannot be in the future")
        except ValueError:
            errors.append(f"Invalid date format: {record['date']}. Use YYYY-MM-DD")
    
    if record.get('Rainfall_mm') is not None:
        try:
            rainfall = float(record['Rainfall_mm'])
            if rainfall < 0:
                errors.append(f"Rainfall cannot be negative: {rainfall}")
            if rainfall > 500:
                errors.append(f"Rainfall unusually high: {rainfall}mm")
        except (ValueError, TypeError):
            errors.append(f"Invalid rainfall value: {record['Rainfall_mm']}")
    
    if record.get('Temp_Max_C') is not None:
        try:
            temp = float(record['Temp_Max_C'])
            if temp < -10 or temp > 50:
                errors.append(f"Temperature out of range: {temp}°C")
        except (ValueError, TypeError):
            errors.append(f"Invalid temperature value: {record['Temp_Max_C']}")
    
    if record.get('Humidity_pct') is not None:
        try:
            humidity = float(record['Humidity_pct'])
            if humidity < 0 or humidity > 100:
                errors.append(f"Humidity must be between 0-100: {humidity}")
        except (ValueError, TypeError):
            errors.append(f"Invalid humidity value: {record['Humidity_pct']}")
    
    if record.get('NDVI') is not None:
        try:
            ndvi = float(record['NDVI'])
            if ndvi < -1 or ndvi > 1:
                errors.append(f"NDVI must be between -1 and 1: {ndvi}")
        except (ValueError, TypeError):
            errors.append(f"Invalid NDVI value: {record['NDVI']}")
    
    valid_provinces = ['Central', 'Copperbelt', 'Eastern', 'Luapula', 'Lusaka',
                       'Muchinga', 'North-Western', 'Northern', 'Southern', 'Western']
    if record.get('province') and record['province'] not in valid_provinces:
        errors.append(f"Invalid province: {record['province']}")
    
    return len(errors) == 0, errors
