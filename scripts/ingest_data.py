# scripts/ingest_data.py
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import logging
from utils.database import db_manager
from utils.validation import validate_climate_record
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def ingest_csv(file_path, source_agency="Unknown", change_reason="Initial import"):
    """Ingest CSV data with validation and logging"""
    
    logger.info(f"Starting ingestion from {file_path}")
    
    # Load data
    df = pd.read_csv(file_path)
    logger.info(f"Loaded {len(df)} records")
    
    valid_records = []
    invalid_records = []
    
    for idx, row in df.iterrows():
        record = row.to_dict()
        is_valid, errors = validate_climate_record(record)
        
        if is_valid:
            valid_records.append(record)
        else:
            invalid_records.append({"record": record, "errors": errors})
    
    logger.info(f"Valid: {len(valid_records)}, Invalid: {len(invalid_records)}")
    
    # Insert valid records
    if valid_records:
        # Insert logic here
        logger.info(f"Inserted {len(valid_records)} records")
    
    # Log invalid records
    if invalid_records:
        logger.warning(f"Skipped {len(invalid_records)} invalid records")
    
    return {
        "total": len(df),
        "valid": len(valid_records),
        "invalid": len(invalid_records),
        "errors": invalid_records[:10]  # First 10 errors
    }

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        result = ingest_csv(sys.argv[1])
        print(result)
    else:
        print("Usage: python scripts/ingest_data.py <csv_file_path>")
