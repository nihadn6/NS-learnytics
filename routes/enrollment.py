from flask import Blueprint, request, jsonify, session, render_template, redirect, url_for
from database.db import get_db_connection
from flask import jsonify

enrollment_bp = Blueprint('enrollment', __name__)

@enrollment_bp.route('/enroll', methods=['GET', 'POST'])
def join_class():
    if session.get('role') != 'student':
        return "Unauthorized", 403
        
    if request.method == 'GET':
        return render_template('join_class.html')
        
    join_code = request.form.get('join_code')
    if not join_code:
        return render_template('join_class.html', error="Join code is required")
        
    student_id = session['user_id']
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM classes WHERE join_code = %s", (join_code,))
            class_row = cursor.fetchone()
            if not class_row:
                return render_template('join_class.html', error="Invalid join code")
                
            class_id = class_row['id']
            
            cursor.execute("SELECT id FROM enrollments WHERE class_id = %s AND student_id = %s", (class_id, student_id))
            if cursor.fetchone():
                return render_template('join_class.html', error="Already enrolled in this class")
                
            cursor.execute("INSERT INTO enrollments (class_id, student_id) VALUES (%s, %s)", (class_id, student_id))
        conn.commit()
        return redirect(url_for('classes.view_classes'))
    except Exception as e:
        return render_template('join_class.html', error=str(e))
    finally:
        conn.close()


@enrollment_bp.route('/api/classes/<int:class_id>/students', methods=['GET'])
def api_class_students(class_id):
    # Allow teacher (if owner), moderator, superadmin to fetch enrolled students for AJAX
    if session.get('role') not in ('teacher', 'moderator', 'superadmin'):
        return jsonify({'error': 'Unauthorized'}), 403

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # If teacher, ensure they own the class
            if session.get('role') == 'teacher':
                cursor.execute("SELECT 1 FROM classes WHERE id = %s AND teacher_id = %s", (class_id, session['user_id']))
                if not cursor.fetchone():
                    return jsonify({'error': 'Unauthorized for this class'}), 403

            # also fetch class info (fee) to allow client to prefill amounts
            cursor.execute("SELECT fee FROM classes WHERE id = %s", (class_id,))
            class_info = cursor.fetchone() or {}
            cursor.execute("SELECT u.id, u.name, u.email FROM enrollments e JOIN users u ON e.student_id = u.id WHERE e.class_id = %s ORDER BY u.name", (class_id,))
            rows = cursor.fetchall()
            # return a JSON-friendly list
            students = [{'id': r['id'], 'name': r['name'], 'email': r.get('email')} for r in rows]
            return jsonify({'students': students, 'fee': class_info.get('fee')})
    finally:
        conn.close()

@enrollment_bp.route('/classes/<int:class_id>/students', methods=['GET'])
def view_students(class_id):
    if session.get('role') != 'teacher':
        return "Unauthorized", 403
        
    teacher_id = session['user_id']
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT subject FROM classes WHERE id = %s AND teacher_id = %s", (class_id, teacher_id))
            class_info = cursor.fetchone()
            if not class_info:
                return "Class not found", 404
                
            cursor.execute("""
                SELECT u.id, u.name, u.email, s.grade, e.joined_at 
                FROM enrollments e
                JOIN users u ON e.student_id = u.id
                JOIN student_profiles s ON u.id = s.user_id
                WHERE e.class_id = %s
            """, (class_id,))
            students = cursor.fetchall()
            return render_template('class_students.html', students=students, class_subject=class_info['subject'], class_id=class_id)
    finally:
        conn.close()
