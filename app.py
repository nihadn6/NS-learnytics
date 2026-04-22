from flask import Flask, render_template, session, redirect, url_for
from datetime import timedelta
import os

from routes.auth import auth_bp
from routes.classes import classes_bp
from routes.enrollment import enrollment_bp
from routes.attendance import attendance_bp
from routes.performance import performance_bp
from routes.finance import finance_bp
from routes.analytics import analytics_bp
from routes.profile import profile_bp
from routes.admin import admin_bp
from database.db import get_db_connection

app = Flask(__name__)
app.secret_key = 'ns_learnytics_secret_key'
app.permanent_session_lifetime = timedelta(days=7)

# Register Blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(classes_bp)
app.register_blueprint(enrollment_bp)
app.register_blueprint(attendance_bp)
app.register_blueprint(performance_bp)
app.register_blueprint(finance_bp)
app.register_blueprint(analytics_bp)
app.register_blueprint(profile_bp)
app.register_blueprint(admin_bp)

@app.route('/')
def index():
    # Always show the login page at the site root. Users should explicitly log in.
    # This prevents stale sessions from taking visitors directly to role-specific pages.
    return redirect(url_for('auth.login'))

@app.route('/debug-db')
def debug_db():
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("SHOW TABLES")
            tables = cursor.fetchall()
            cursor.execute("SELECT DATABASE()")
            db_name = cursor.fetchone()
        conn.close()
        return f"Connected to: {db_name}. Tables found: {tables}"
    except Exception as e:
        return f"Database Connection Error: {str(e)}"

@app.route('/init-db')
def web_init_db():
    try:
        from init_prod_db import init_db
        init_db()
        return "Database Schema Initialized Successfully! <a href='/'>Go to Login</a>"
    except Exception as e:
        return f"Error during Init: {str(e)}"

@app.route('/seed-db')
def web_seed_db():
    try:
        from database.seed import seed_data
        seed_data()
        return "Database Seeded with test data! <a href='/'>Go to Login</a>"
    except Exception as e:
        return f"Error during Seeding: {str(e)}"

if __name__ == '__main__':
    app.run(debug=True, port=5000)
