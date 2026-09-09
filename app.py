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
from routes.parent import parent_bp
from routes.messages import messages_bp
from routes.lms import lms_bp
from routes.announcements import announcements_bp
from routes.ai_analytics import ai_analytics_bp
from database.db import get_db_connection

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'ns_learnytics_secure_secret_key_2024')
app.permanent_session_lifetime = timedelta(hours=2)

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
app.register_blueprint(parent_bp)
app.register_blueprint(messages_bp)
app.register_blueprint(lms_bp)
app.register_blueprint(announcements_bp)
app.register_blueprint(ai_analytics_bp)


@app.route('/')
def index():
    # Always show the login page at the site root. Users should explicitly log in.
    # This prevents stale sessions from taking visitors directly to role-specific pages.
    return redirect(url_for('auth.login'))

@app.route('/debug-db')
def debug_db():
    import traceback
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
        return f"Database Connection Error: {str(e)}<br><pre>{traceback.format_exc()}</pre>"

@app.route('/init-db')
def web_init_db():
    import traceback
    try:
        from init_prod_db import init_db
        init_db()
        return "Database Schema Initialized Successfully! <a href='/'>Go to Login</a>"
    except Exception as e:
        return f"Error during Init: {str(e)}<br><pre>{traceback.format_exc()}</pre>"

@app.route('/seed-db')
def web_seed_db():
    import traceback
    try:
        from database.seed import seed_data
        seed_data()
        return "Database Seeded with test data! <a href='/'>Go to Login</a>"
    except Exception as e:
        return f"Error during Seeding: {str(e)}<br><pre>{traceback.format_exc()}</pre>"

if __name__ == '__main__':
    app.run(debug=True, port=5000)
