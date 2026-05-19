# Add these validation rules to utils/validation.py

def validate_climate_record(record):
    """Comprehensive validation for climate records"""
    errors = []
    
    # Rainfall validation
    if record.get('rainfall_mm') is not None:
        val = float(record['rainfall_mm'])
        if val < 0:
            errors.append(f"Rainfall cannot be negative: {val}")
        elif val > 500:
            errors.append(f"Rainfall unusually high: {val}mm (max expected: 500)")
    
    # Humidity validation
    if record.get('humidity_pct') is not None:
        val = float(record['humidity_pct'])
        if val < 0 or val > 100:
            errors.append(f"Humidity must be 0-100: {val}")
    
    # NDVI validation
    if record.get('ndvi') is not None:
        val = float(record['ndvi'])
        if val < -1 or val > 1:
            errors.append(f"NDVI must be -1 to 1: {val}")
    
    # Temperature validation
    if record.get('temp_min_c') is not None and record.get('temp_max_c') is not None:
        t_min = float(record['temp_min_c'])
        t_max = float(record['temp_max_c'])
        if t_min >= t_max:
            errors.append(f"Min temp ({t_min}) must be less than max temp ({t_max})")
    
    # PDSI validation (typically -6 to +6)
    if record.get('pdsi') is not None:
        val = float(record['pdsi'])
        if val < -6 or val > 6:
            errors.append(f"PDSI unusually high/low: {val} (expected -6 to +6)")
    
    return len(errors) == 0, errors
