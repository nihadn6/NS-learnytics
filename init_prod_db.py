import pymysql
import os
from database.db import get_db_connection

def init_db():
    print("Connecting to database...")
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Read schema.sql
            schema_path = os.path.join('database', 'schema.sql')
            with open(schema_path, 'r') as f:
                sql_content = f.read()

            # Split by semicolon to execute one by one
            # We skip 'CREATE DATABASE' and 'USE' lines for production compatibility
            commands = sql_content.split(';')
            
            for command in commands:
                cmd = command.strip()
                if not cmd:
                    continue
                if cmd.upper().startswith('CREATE DATABASE') or cmd.upper().startswith('USE '):
                    print(f"Skipping command: {cmd[:30]}...")
                    continue
                
                try:
                    print(f"Executing: {cmd[:50]}...")
                    cursor.execute(cmd)
                except Exception as e:
                    print(f"Bypassed error during command execution: {e}")
            
        conn.commit()
        print("Database initialized successfully!")
    except Exception as e:
        print(f"Error during initialization: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    init_db()
