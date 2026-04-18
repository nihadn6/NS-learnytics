from flask import Blueprint, request, jsonify, session, render_template, redirect, url_for
import datetime
from database.db import get_db_connection

attendance_bp = Blueprint('attendance', __name__)

@attendance_bp.route('/attendance/mark', methods=['GET', 'POST'])
def mark_attendance():
    role = session.get('role')
    if role not in ('teacher', 'moderator', 'superadmin'):
        return "Unauthorized", 403
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            if request.method == 'GET':
                class_id = request.args.get('class_id')
                date = request.args.get('date')
                
                if role == 'teacher':
                    cursor.execute("SELECT id, subject FROM classes WHERE id = %s AND teacher_id = %s", (class_id, session['user_id']))
                else:
                    cursor.execute("SELECT id, subject FROM classes WHERE id = %s", (class_id,))
                    
                if not cursor.fetchone():
                    return "Invalid class", 400
                    
                cursor.execute("""
                    SELECT u.id, u.name 
                    FROM enrollments e
                    JOIN users u ON e.student_id = u.id
                    WHERE e.class_id = %s
                """, (class_id,))
                students = cursor.fetchall()
                if not students:
                    return render_template('mark_attendance.html', error="No students enrolled", class_id=class_id, date=date, students=[])
                return render_template('mark_attendance.html', students=students, class_id=class_id, date=date)
                
            data = request.form
            class_id = data.get('class_id')
            date = data.get('date')
            
            for key, value in data.items():
                if key.startswith('status_'):
                    student_id = key.split('_')[1]
                    cursor.execute("""
                        INSERT INTO attendance (class_id, student_id, date, status) 
                        VALUES (%s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE status = VALUES(status)
                    """, (class_id, student_id, date, value))
            conn.commit()
            return redirect(url_for('classes.view_classes'))
    finally:
        conn.close()

@attendance_bp.route('/attendance/history', methods=['GET'])
def view_attendance_history():
    if session.get('role') != 'student':
        return "Student view only", 403
        
    user_id = session['user_id']
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT c.subject, a.date, a.status 
                FROM attendance a
                JOIN classes c ON a.class_id = c.id
                WHERE a.student_id = %s
                ORDER BY a.date DESC
            """, (user_id,))
            records = cursor.fetchall()
            
            cursor.execute("""
                SELECT c.subject, 
                       SUM(CASE WHEN a.status = 'present' THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(*), 0) as percentage
                FROM attendance a
                JOIN classes c ON a.class_id = c.id
                WHERE a.student_id = %s
                GROUP BY c.id
            """, (user_id,))
            percentages = cursor.fetchall()
            
            return render_template('attendance_student.html', records=records, percentages=percentages)
    finally:
        conn.close()


@attendance_bp.route('/attendance/scan', methods=['GET', 'POST'])
def scan_attendance():
    # Moderators (clerks) can scan student QR codes to mark attendance
    if session.get('role') not in ('moderator', 'admin', 'superadmin'):
        return "Unauthorized", 403

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            if request.method == 'GET':
                cursor.execute("SELECT id, name FROM users WHERE role = 'teacher' ORDER BY name")
                teachers = cursor.fetchall()
                cursor.execute("SELECT id, subject, teacher_id FROM classes ORDER BY subject")
                classes = cursor.fetchall()
                cursor.execute("""
                    SELECT e.class_id, u.id as student_id, u.name 
                    FROM enrollments e 
                    JOIN users u ON e.student_id = u.id 
                    ORDER BY u.name
                """)
                enrollments = cursor.fetchall()
                return render_template('scan_attendance.html', teachers=teachers, classes=classes, enrollments=enrollments)

            # POST: accept JSON payload with token/student_id and class_id (and optional date)
            data = request.get_json() or {}
            token = data.get('token')
            student_id = data.get('student_id')
            class_id = data.get('class_id')
            date = data.get('date')  # optional YYYY-MM-DD

            if not class_id:
                return jsonify({'error': 'class_id required'}), 400

            if token:
                # Find student by token
                cursor.execute("SELECT u.id as student_id FROM student_profiles sp JOIN users u ON sp.user_id = u.id WHERE sp.qr_code = %s", (token,))
                row = cursor.fetchone()
                if not row:
                    return jsonify({'error': 'Invalid token'}), 400
                student_id = row['student_id']
            elif not student_id:
                return jsonify({'error': 'token or student_id required'}), 400

            # Verify enrollment
            cursor.execute("SELECT 1 FROM enrollments WHERE class_id = %s AND student_id = %s", (class_id, student_id))
            if not cursor.fetchone():
                return jsonify({'error': 'Student not enrolled in this class'}), 400

            # Use provided date or today
            if not date:
                date = datetime.date.today().isoformat()

            # Insert or update attendance - mark as present
            cursor.execute("""
                INSERT INTO attendance (class_id, student_id, date, status)
                VALUES (%s, %s, %s, 'present')
                ON DUPLICATE KEY UPDATE status = VALUES(status)
            """, (class_id, student_id, date))
            conn.commit()

            # Return success and student info
            cursor.execute("SELECT name FROM users WHERE id = %s", (student_id,))
            student = cursor.fetchone()
            return jsonify({'success': True, 'student': student, 'date': date})
    finally:
        conn.close()


@attendance_bp.route('/attendance/manual', methods=['GET', 'POST'])
def manual_mark():
    # Allow teachers, moderators, and superadmins to mark attendance manually
    if session.get('role') not in ('teacher', 'moderator', 'superadmin'):
        return "Unauthorized", 403

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            if request.method == 'GET':
                # For teachers: show only their classes. For others: show all classes.
                if session.get('role') == 'teacher':
                    cursor.execute("SELECT id, subject FROM classes WHERE teacher_id = %s", (session['user_id'],))
                else:
                    cursor.execute("SELECT id, subject FROM classes ORDER BY subject")
                classes = cursor.fetchall()

                class_id = request.args.get('class_id')
                date = request.args.get('date') or ''
                students = []
                if class_id:
                    cursor.execute("SELECT u.id, u.name FROM enrollments e JOIN users u ON e.student_id = u.id WHERE e.class_id = %s", (class_id,))
                    students = cursor.fetchall()
                return render_template('mark_attendance.html', students=students, class_id=class_id, date=date, action_url=url_for('attendance.manual_mark'))

            # POST: accept manual attendance entries
            data = request.form
            class_id = data.get('class_id')
            date = data.get('date')

            # permission: if teacher, must own the class_id
            if session.get('role') == 'teacher':
                cursor.execute("SELECT 1 FROM classes WHERE id = %s AND teacher_id = %s", (class_id, session['user_id']))
                if not cursor.fetchone():
                    return "Invalid class or unauthorized", 400

            for key, value in data.items():
                if key.startswith('status_'):
                    student_id = key.split('_')[1]
                    cursor.execute("""
                        INSERT INTO attendance (class_id, student_id, date, status) 
                        VALUES (%s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE status = VALUES(status)
                    """, (class_id, student_id, date, value))
            conn.commit()
            # Redirect back to classes or admin dashboard based on role
            if session.get('role') == 'teacher':
                return redirect(url_for('classes.view_classes'))
            return redirect(url_for('admin.dashboard'))
    finally:
        conn.close()


@attendance_bp.route('/attendance/report', methods=['GET'])
def attendance_report():
    role = session.get('role')
    if role not in ('teacher', 'admin', 'superadmin'):
        return "Unauthorized", 403

    user_id = session['user_id']
    class_id = request.args.get('class_id')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            teachers = []
            if role in ('admin', 'superadmin'):
                cursor.execute("SELECT id, name FROM users WHERE role = 'teacher' ORDER BY name")
                teachers = cursor.fetchall()
                cursor.execute("SELECT id, subject, teacher_id FROM classes ORDER BY subject")
                classes = cursor.fetchall()
            else:
                cursor.execute("SELECT id, subject FROM classes WHERE teacher_id = %s ORDER BY subject", (user_id,))
                classes = cursor.fetchall()
            
            records = []
            aggregated = []
            
            if class_id and start_date and end_date:
                authorized = False
                if role == 'teacher':
                    cursor.execute("SELECT 1 FROM classes WHERE id = %s AND teacher_id = %s", (class_id, user_id))
                    if cursor.fetchone():
                        authorized = True
                else:
                    authorized = True
                
                if authorized:
                    cursor.execute("""
                        SELECT u.name, u.email, a.date, a.status
                        FROM attendance a
                        JOIN users u ON a.student_id = u.id
                        WHERE a.class_id = %s AND a.date >= %s AND a.date <= %s
                        ORDER BY a.date DESC, u.name ASC
                    """, (class_id, start_date, end_date))
                    records = cursor.fetchall()
                    
                    cursor.execute("""
                        SELECT u.name,
                               SUM(CASE WHEN a.status = 'present' THEN 1 ELSE 0 END) as present_days,
                               COUNT(a.id) as total_days,
                               (SUM(CASE WHEN a.status = 'present' THEN 1 ELSE 0 END) * 100.0 / COUNT(a.id)) as attendance_percentage
                        FROM attendance a
                        JOIN users u ON a.student_id = u.id
                        WHERE a.class_id = %s AND a.date >= %s AND a.date <= %s
                        GROUP BY a.student_id, u.name
                        ORDER BY attendance_percentage DESC
                    """, (class_id, start_date, end_date))
                    aggregated = cursor.fetchall()
                    
            return render_template('attendance_report.html', teachers=teachers, classes=classes, class_id=class_id, start_date=start_date, end_date=end_date, records=records, aggregated=aggregated)
    finally:
        conn.close()


@attendance_bp.route('/attendance/finalize', methods=['POST'])
def finalize_attendance():
    import datetime
    role = session.get('role')
    if role not in ('teacher', 'moderator', 'admin', 'superadmin'):
        return jsonify({'error': 'Unauthorized'}), 403

    data = request.get_json() or {}
    class_id = data.get('class_id')
    date = data.get('date') or datetime.date.today().isoformat()

    if not class_id:
        return jsonify({'error': 'class_id required'}), 400

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            if role == 'teacher':
                cursor.execute("SELECT 1 FROM classes WHERE id = %s AND teacher_id = %s", (class_id, session['user_id']))
                if not cursor.fetchone():
                    return jsonify({'error': 'Unauthorized for this localized class sequence'}), 403

            cursor.execute("SELECT student_id FROM enrollments WHERE class_id = %s", (class_id,))
            enrolled_students = [row['student_id'] for row in cursor.fetchall()]

            if not enrolled_students:
                return jsonify({'error': 'No physical students structurally enrolled in this explicit class vector.'}), 400

            cursor.execute("SELECT student_id FROM attendance WHERE class_id = %s AND date = %s", (class_id, date))
            marked_students = set(row['student_id'] for row in cursor.fetchall())

            missing_students = [s for s in enrolled_students if s not in marked_students]
            if not missing_students:
                return jsonify({'success': True, 'message': 'All structurally enrolled students are already exclusively tracked internally for today!'})

            for student_id in missing_students:
                cursor.execute("""
                    INSERT INTO attendance (class_id, student_id, date, status) 
                    VALUES (%s, %s, %s, 'absent')
                    ON DUPLICATE KEY UPDATE status = VALUES(status)
                """, (class_id, student_id, date))
            conn.commit()

            return jsonify({'success': True, 'message': f'Algorithm executed successfully: Flagged exactly {len(missing_students)} structurally missing student(s) natively as Absent.'})
    finally:
        conn.close()
