import pymysql
import os

DB_HOST = os.environ.get('DB_HOST', 'localhost')
DB_USER = os.environ.get('DB_USER', 'root')
DB_PASS = os.environ.get('DB_PASS', '')
DB_NAME = 'ns_learnytics'

def get_db_connection():
    # Use utf8 (not utf8mb4) for compatibility with older MySQL versions
    return pymysql.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASS,
        database=DB_NAME,
        cursorclass=pymysql.cursors.DictCursor,
        charset='utf8',
        init_command='SET NAMES utf8'
    )
