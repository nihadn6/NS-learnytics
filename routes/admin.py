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

            # Pending Parent Requests
            cursor.execute("SELECT COUNT(*) as cnt FROM parent_student_links WHERE status = 'pending'")
            pending_parent_requests_count = cursor.fetchone()['cnt']

            # Total Classes
            cursor.execute("SELECT COUNT(*) as cnt FROM classes")
            total_classes_count = cursor.fetchone()['cnt']

            # Recent User Signups
            cursor.execute("SELECT id, name, email, role, created_at FROM users ORDER BY id DESC LIMIT 5")
            recent_users = cursor.fetchall()

            return render_template('admin_dashboard.html', 
                                   staff=staff, 
                                   students=students,
                                   total_students_count=total_students_count,
                                   total_staff_count=total_staff_count,
                                   total_revenue=total_revenue,
                                   pending_parent_requests_count=pending_parent_requests_count,
                                   total_classes_count=total_classes_count,
                                   recent_users=recent_users)
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

@admin_bp.route('/admin/parent-requests', methods=['GET'])
def view_parent_requests():
    if session.get('role') != 'superadmin':
        return "Unauthorized", 403
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT psl.id, p.name as parent_name, p.email as parent_email, 
                       s.name as student_name, s.email as student_email, psl.status, psl.created_at
                FROM parent_student_links psl
                JOIN users p ON psl.parent_id = p.id
                JOIN users s ON psl.student_id = s.id
                WHERE psl.status = 'pending'
            """)
            pending = cursor.fetchall()
            
            cursor.execute("""
                SELECT psl.id, p.name as parent_name, s.name as student_name, psl.status
                FROM parent_student_links psl
                JOIN users p ON psl.parent_id = p.id
                JOIN users s ON psl.student_id = s.id
                WHERE psl.status != 'pending'
                ORDER BY psl.created_at DESC LIMIT 50
            """)
            history = cursor.fetchall()
            
            return render_template('admin_parent_requests.html', pending=pending, history=history)
    finally:
        conn.close()

@admin_bp.route('/admin/parent-requests/<int:request_id>/<string:action>', methods=['POST'])
def manage_parent_request(request_id, action):
    if session.get('role') != 'superadmin':
        return "Unauthorized", 403
    
    status = 'approved' if action == 'approve' else 'rejected'
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE parent_student_links SET status = %s WHERE id = %s", (status, request_id))
            conn.commit()
        return redirect(url_for('admin.view_parent_requests'))
    finally:
        conn.close()

@admin_bp.route('/admin/manage-users', methods=['GET'])
def manage_users():
    if session.get('role') != 'superadmin':
        return "Unauthorized", 403

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Fetch staff (teachers and moderators)
            cursor.execute("SELECT id, name, email, role FROM users WHERE role IN ('teacher', 'moderator') ORDER BY role, name")
            staff = cursor.fetchall()
            # Fetch students
            cursor.execute("SELECT id, name, email, role FROM users WHERE role = 'student' ORDER BY name")
            students = cursor.fetchall()

            return render_template('admin_manage_users.html', staff=staff, students=students)
    finally:
        conn.close()

@admin_bp.route('/admin/delete_user/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    if session.get('role') != 'superadmin':
        return "Unauthorized", 403
        
    if user_id == session.get('user_id'):
        return "Cannot delete your own active administrator account", 400

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM student_profiles WHERE user_id = %s", (user_id,))
            cursor.execute("DELETE FROM teacher_profiles WHERE user_id = %s", (user_id,))
            cursor.execute("DELETE FROM parent_student_links WHERE parent_id = %s OR student_id = %s", (user_id, user_id))
            cursor.execute("DELETE FROM enrollments WHERE student_id = %s", (user_id,))
            cursor.execute("DELETE FROM attendance WHERE student_id = %s", (user_id,))
            cursor.execute("DELETE FROM marks WHERE student_id = %s", (user_id,))
            cursor.execute("DELETE FROM payments WHERE student_id = %s", (user_id,))
            cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
            conn.commit()
            next_url = request.referrer or url_for('admin.manage_users')
            return redirect(next_url)
    finally:
        conn.close()


