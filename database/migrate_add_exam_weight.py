import os
import sys

# Ensure parent directory is in Python path for database.db import
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database.db import get_db_connection

def run_migration():
    print("Running migration: Add weight_pct to marks table...")
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Check if column already exists
            cursor.execute("""
                SELECT COUNT(*) as cnt
                FROM information_schema.COLUMNS 
                WHERE TABLE_SCHEMA = DATABASE() 
                  AND TABLE_NAME = 'marks' 
                  AND COLUMN_NAME = 'weight_pct'
            """)
            result = cursor.fetchone()
            col_exists = result['cnt'] > 0 if isinstance(result, dict) else result[0] > 0

            if not col_exists:
                print("Adding 'weight_pct' column (DECIMAL(5,2) NOT NULL DEFAULT 100.00) to 'marks' table...")
                cursor.execute("""
                    ALTER TABLE marks 
                    ADD COLUMN weight_pct DECIMAL(5,2) NOT NULL DEFAULT 100.00 AFTER max_marks
                """)
                print("Column 'weight_pct' successfully added.")
            else:
                print("Column 'weight_pct' already exists in 'marks' table.")

            # Ensure all existing rows have weight_pct set to default 100.00
            cursor.execute("UPDATE marks SET weight_pct = 100.00 WHERE weight_pct IS NULL OR weight_pct <= 0")
            
        conn.commit()
        print("Migration for exam weight completed successfully.")
    except Exception as e:
        print(f"Migration error: {e}")
        raise e
    finally:
        conn.close()

if __name__ == '__main__':
    run_migration()
