from flask import Blueprint, request, jsonify, session, render_template, redirect, url_for
from database.db import get_db_connection
from werkzeug.security import generate_password_hash
import uuid

admin_bp = Blueprint('admin', __name__)

@admin_bp.route('/admin/dashboard', methods=['GET'])
def dashboard():
    if session.get('role') != 'superadmin':
        return "Unauthorized", 403
        
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Fetch staff (teachers and moderators)
            cursor.execute("SELECT id, name, email, role FROM users WHERE role IN ('teacher', 'moderator')")
            staff = cursor.fetchall()
            # Fetch students
            cursor.execute("SELECT id, name, email, role FROM users WHERE role = 'student'")
            students = cursor.fetchall()
            
            # System Stats
            cursor.execute("SELECT COUNT(*) as cnt FROM users WHERE role = 'student'")
            total_students_count = cursor.fetchone()['cnt']
            
            cursor.execute("SELECT COUNT(*) as cnt FROM users WHERE role IN ('teacher', 'moderator')")
            total_staff_count = cursor.fetchone()['cnt']
            
            cursor.execute("SELECT SUM(amount) as total FROM payments")
            total_revenue = float(cursor.fetchone()['total'] or 0.0)

            return render_template('admin_dashboard.html', 
                                   staff=staff, 
                                   students=students,
                                   total_students_count=total_students_count,
                                   total_staff_count=total_staff_count,
                                   total_revenue=total_revenue)
    finally:
        conn.close()

@admin_bp.route('/admin/create_staff', methods=['POST'])
def create_staff():
    if session.get('role') != 'superadmin':
        return "Unauthorized", 403
        
    data = request.form
    name = data.get('name')
    email = data.get('email')
    password = data.get('password')
    role = data.get('role')
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
            if cursor.fetchone():
                return "Email already exists", 400
                
            pw_hash = generate_password_hash(password)
            cursor.execute("INSERT INTO users (name, email, password_hash, role) VALUES (%s, %s, %s, %s)",
                           (name, email, pw_hash, role))
            user_id = cursor.lastrowid
            
            if role == 'teacher':
                cursor.execute("INSERT INTO teacher_profiles (user_id) VALUES (%s)", (user_id,))
            
            conn.commit()
            return redirect(url_for('admin.dashboard'))
    finally:
        conn.close()


@admin_bp.route('/admin/create_student', methods=['POST'])
def create_student():
    if session.get('role') != 'superadmin':
        return "Unauthorized", 403

    data = request.form
    name = data.get('name')
    email = data.get('email')
    password = data.get('password')
    grade = data.get('grade') or ''

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
            if cursor.fetchone():
                return "Email already exists", 400

            pw_hash = generate_password_hash(password)
            cursor.execute("INSERT INTO users (name, email, password_hash, role) VALUES (%s, %s, %s, 'student')",
                           (name, email, pw_hash))
            user_id = cursor.lastrowid

            # generate QR token for student
            token = uuid.uuid4().hex
            cursor.execute("INSERT INTO student_profiles (user_id, grade, qr_code) VALUES (%s, %s, %s)",
                           (user_id, grade, token))

            conn.commit()
            return redirect(url_for('admin.dashboard'))
    finally:
        conn.close()
