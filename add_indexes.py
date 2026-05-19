# add_indexes.py
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils.database import db_manager

print("Creating database indexes...")

indexes = [
    'CREATE INDEX IF NOT EXISTS idx_date ON climate_records(date)',
    'CREATE INDEX IF NOT EXISTS idx_province ON climate_records(province)',
    'CREATE INDEX IF NOT EXISTS idx_district ON climate_records(district)',
    'CREATE INDEX IF NOT EXISTS idx_year ON climate_records(year)',
    'CREATE INDEX IF NOT EXISTS idx_drought_severity ON climate_records(drought_severity)',
    'CREATE INDEX IF NOT EXISTS idx_year_province ON climate_records(year, province)',
    'CREATE INDEX IF NOT EXISTS idx_month ON climate_records(month)',
]

for idx in indexes:
    try:
        db_manager.execute_query(idx)
        print(f"  ✓ {idx.split('ON')[0].replace('CREATE INDEX IF NOT EXISTS', '').strip()}")
    except Exception as e:
        print(f"  ✗ Error: {e}")

print("\n✅ All indexes created successfully!")
