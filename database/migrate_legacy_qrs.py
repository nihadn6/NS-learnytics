import os
import sys
import uuid

# Add the parent directory to the python path so it can natively find the database module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.db import get_db_connection

def migrate_legacy_qrs():
    print("Initialize scan for legacy student profiles missing QR tokens...")
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Locate all student profiles where the QR token is missing or empty
            cursor.execute("SELECT id, user_id FROM student_profiles WHERE qr_code IS NULL OR qr_code = ''")
            legacy_profiles = cursor.fetchall()
            
            if not legacy_profiles:
                print("100% of all students already securely possess a QR token!")
                return
            
            print(f"Found {len(legacy_profiles)} legacy student(s) without QR codes. Fixing...")
            
            for profile in legacy_profiles:
                new_token = str(uuid.uuid4())
                cursor.execute("UPDATE student_profiles SET qr_code = %s WHERE id = %s", (new_token, profile['id']))
            
            conn.commit()
            print(f"Successfully retroactively generated dynamic QR tokens for {len(legacy_profiles)} legacy student accounts!")
            print("Their profile dashboards will now correctly display their badges.")
            
    except Exception as e:
        print(f"CRITICAL ERROR during migration loop: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    migrate_legacy_qrs()
