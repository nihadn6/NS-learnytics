import os
import pymysql

DB_HOST = os.environ.get('DB_HOST', 'localhost')
DB_USER = os.environ.get('DB_USER', 'root')
DB_PASS = os.environ.get('DB_PASS', '')
DB_NAME = os.environ.get('DB_NAME', 'ns_learnytics')
DB_PORT = int(os.environ.get('DB_PORT', 3306))


def get_conn(db=None):
    return pymysql.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASS,
        database=db or DB_NAME,
        cursorclass=pymysql.cursors.DictCursor,
        charset='utf8',
        init_command='SET NAMES utf8'
    )


def column_exists(cursor, table, column):
    cursor.execute(
        "SELECT COUNT(*) AS cnt FROM information_schema.columns WHERE table_schema=%s AND table_name=%s AND column_name=%s",
        (DB_NAME, table, column)
    )
    return cursor.fetchone()['cnt'] > 0


def enum_contains(cursor, table, column, value):
    cursor.execute(
        "SELECT column_type FROM information_schema.columns WHERE table_schema=%s AND table_name=%s AND column_name=%s",
        (DB_NAME, table, column)
    )
    row = cursor.fetchone()
    if not row:
        return False
    return value in row['column_type']


def main():
    print(f"Connecting to {DB_HOST}/{DB_NAME} as {DB_USER}")
    conn = get_conn()
    try:
        with conn.cursor() as cursor:
            # 1) Add qr_code column if missing
            if not column_exists(cursor, 'student_profiles', 'qr_code'):
                print("Adding column student_profiles.qr_code")
                cursor.execute("ALTER TABLE student_profiles ADD COLUMN qr_code VARCHAR(64) UNIQUE")
            else:
                print("Column student_profiles.qr_code already exists")

            # 2) Ensure users.role enum contains 'moderator'
            if not enum_contains(cursor, 'users', 'role', 'moderator'):
                print("Adding 'moderator' to users.role enum")
                # Build new enum - include known values
                # We set order: teacher, student, moderator
                cursor.execute("ALTER TABLE users MODIFY COLUMN role ENUM('teacher','student','moderator') NOT NULL")
            else:
                print("users.role already contains 'moderator'")

            # 3) Fill missing qr_code values with UUID()
            print("Filling missing qr_code values with UUID() where necessary")
            cursor.execute("UPDATE student_profiles SET qr_code = UUID() WHERE qr_code IS NULL OR qr_code = ''")
            conn.commit()
            print("Migration completed successfully.")
    finally:
        conn.close()


if __name__ == '__main__':
    main()
