from flask import Blueprint, request, jsonify, session, render_template, redirect, url_for
from database.db import get_db_connection
import string
import random

classes_bp = Blueprint('classes', __name__)

def generate_join_code(length=8):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

@classes_bp.route('/classes', methods=['GET'])
def view_classes():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
        
    user_id = session['user_id']
    role = session['role']
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            if role == 'teacher':
                cursor.execute("SELECT * FROM classes WHERE teacher_id = %s ORDER BY created_at DESC", (user_id,))
                classes = cursor.fetchall()
                return render_template('classes_teacher.html', classes=classes)
            else:
                cursor.execute("""
                    SELECT c.*, u.name as teacher_name 
                    FROM classes c 
                    JOIN enrollments e ON c.id = e.class_id 
                    JOIN users u ON c.teacher_id = u.id
                    WHERE e.student_id = %s ORDER BY e.joined_at DESC
                """, (user_id,))
                classes = cursor.fetchall()
                return render_template('classes_student.html', classes=classes)
    finally:
        conn.close()

@classes_bp.route('/classes/create', methods=['POST'])
def create_class():
    if session.get('role') != 'teacher':
        return "Unauthorized", 403
        
    data = request.form
    subject = data.get('subject')
    schedule = data.get('schedule')
    fee = data.get('fee')
    
    if not all([subject, schedule, fee]):
        return "Missing fields", 400
        
    teacher_id = session['user_id']
    join_code = generate_join_code()
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO classes (teacher_id, subject, schedule, fee, join_code)
                VALUES (%s, %s, %s, %s, %s)
            """, (teacher_id, subject, schedule, fee, join_code))
        conn.commit()
    except Exception as e:
        return str(e), 500
    finally:
        conn.close()
        
    return redirect(url_for('classes.view_classes'))

@classes_bp.route('/classes/delete/<int:class_id>', methods=['POST'])
def delete_class(class_id):
    if session.get('role') != 'teacher':
        return "Unauthorized", 403
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM classes WHERE id = %s AND teacher_id = %s", (class_id, session['user_id']))
        conn.commit()
    finally:
        conn.close()
    return redirect(url_for('classes.view_classes'))
