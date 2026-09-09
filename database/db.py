import pymysql
import os

DB_HOST = os.environ.get('DB_HOST', '127.0.0.1')
DB_USER = os.environ.get('DB_USER', 'root')
DB_PASS = os.environ.get('DB_PASS', '')
DB_NAME = os.environ.get('DB_NAME', 'ns_learnytics')
DB_PORT = int(os.environ.get('DB_PORT', 3306)) # Standard MySQL port is 3306

def get_db_connection():
    # Aiven/Render often require SSL. We check for a DB_SSL_REQUIRED environment variable.
    ssl_config = None
    if os.environ.get('DB_SSL_REQUIRED', 'false').lower() == 'true':
        ca_path = "/etc/ssl/certs/ca-certificates.crt"
        if os.path.exists(ca_path):
            ssl_config = {"ca": ca_path}
        else:
            ssl_config = {} # Fallback to default SSL

    timeout = 10
    try:
        return pymysql.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASS,
            database=DB_NAME,
            port=DB_PORT,
            cursorclass=pymysql.cursors.DictCursor,
            charset='utf8', # Changed from utf8mb4 for maximum compatibility
            ssl=ssl_config,
            connect_timeout=timeout,
            read_timeout=timeout,
            write_timeout=timeout
        )
    except pymysql.MySQLError as e:
        print(f"CRITICAL: Database connection failed! {e}")
        print(f"Attempted connection to {DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME}")
        raise
