import os
import pymysql

DB_HOST = os.environ.get('DB_HOST', 'localhost')
DB_USER = os.environ.get('DB_USER', 'root')
DB_PASS = os.environ.get('DB_PASS', '')
DB_NAME = os.environ.get('DB_NAME', 'ns_learnytics')
DB_PORT = int(os.environ.get('DB_PORT', 3306))

def get_conn():
    return pymysql.connect(
        host=DB_HOST, user=DB_USER, password=DB_PASS, database=DB_NAME,
        cursorclass=pymysql.cursors.DictCursor,
        charset='utf8'
    )

def main():
    print("Migrating DB for superadmin...")
    conn = get_conn()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT column_type FROM information_schema.columns WHERE table_schema=%s AND table_name='users' AND column_name='role'", (DB_NAME,))
            row = cursor.fetchone()
            if row and 'superadmin' not in row['column_type']:
                print("Adding 'superadmin' to users.role enum")
                cursor.execute("ALTER TABLE users MODIFY COLUMN role ENUM('teacher','student','moderator','superadmin') NOT NULL")
            else:
                print("Role already supports superadmin.")
            conn.commit()
    finally:
        conn.close()

if __name__ == '__main__':
    main()
