# create_audit_table.py
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.utils.database import db_manager

print("Creating audit log table...")

try:
    db_manager.execute_query('''
        CREATE TABLE IF NOT EXISTS audit_log (
            id SERIAL PRIMARY KEY,
            table_name VARCHAR(100),
            action VARCHAR(20),
            record_id INTEGER,
            old_data JSONB,
            new_data JSONB,
            changed_by VARCHAR(100),
            changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    print("  ? audit_log table created")
    
    db_manager.execute_query('''
        CREATE INDEX IF NOT EXISTS idx_audit_changed_at ON audit_log(changed_at)
    ''')
    print("  ? index on changed_at created")
    
    print("\n? Audit table ready!")
except Exception as e:
    print(f"  ? Error: {e}")
