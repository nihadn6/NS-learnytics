import os
import sys

# Ensure parent directory is in Python path for database.db import
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database.db import get_db_connection

def run_migration():
    print("Running migration: Add attendance weighting columns to classes table...")
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Check enable_attendance_weight
            cursor.execute("""
                SELECT COUNT(*) as cnt
                FROM information_schema.COLUMNS 
                WHERE TABLE_SCHEMA = DATABASE() 
                  AND TABLE_NAME = 'classes' 
                  AND COLUMN_NAME = 'enable_attendance_weight'
            """)
            result = cursor.fetchone()
            col1_exists = result['cnt'] > 0 if isinstance(result, dict) else result[0] > 0

            if not col1_exists:
                print("Adding 'enable_attendance_weight' (TINYINT(1) DEFAULT 0) to 'classes'...")
                cursor.execute("""
                    ALTER TABLE classes 
                    ADD COLUMN enable_attendance_weight TINYINT(1) NOT NULL DEFAULT 0 AFTER join_code
                """)
            else:
                print("Column 'enable_attendance_weight' already exists.")

            # Check attendance_weight_pct
            cursor.execute("""
                SELECT COUNT(*) as cnt
                FROM information_schema.COLUMNS 
                WHERE TABLE_SCHEMA = DATABASE() 
                  AND TABLE_NAME = 'classes' 
                  AND COLUMN_NAME = 'attendance_weight_pct'
            """)
            result2 = cursor.fetchone()
            col2_exists = result2['cnt'] > 0 if isinstance(result2, dict) else result2[0] > 0

            if not col2_exists:
                print("Adding 'attendance_weight_pct' (DECIMAL(5,2) DEFAULT 10.00) to 'classes'...")
                cursor.execute("""
                    ALTER TABLE classes 
                    ADD COLUMN attendance_weight_pct DECIMAL(5,2) NOT NULL DEFAULT 10.00 AFTER enable_attendance_weight
                """)
            else:
                print("Column 'attendance_weight_pct' already exists.")

        conn.commit()
        print("Migration for class attendance weighting completed successfully.")
    except Exception as e:
        print(f"Migration error: {e}")
        raise e
    finally:
        conn.close()

if __name__ == '__main__':
    run_migration()
