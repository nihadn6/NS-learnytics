import pymysql
import os

DB_HOST = os.environ.get('DB_HOST', 'localhost')
DB_USER = os.environ.get('DB_USER', 'root')
DB_PASS = os.environ.get('DB_PASS', '')
DB_NAME = os.environ.get('DB_NAME', 'ns_learnytics')
DB_PORT = int(os.environ.get('DB_PORT', 3306))

def get_db_connection():
    # Use utf8 (not utf8mb4) for compatibility with older MySQL versions
    return pymysql.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASS,
        database=DB_NAME,
        port = DB_PORT,
        cursorclass=pymysql.cursors.DictCursor,
        charset='utf8',
        init_command='SET NAMES utf8'
    )
