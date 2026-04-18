from flask import Blueprint, request, jsonify, session, render_template, redirect, url_for, flash
from database.db import get_db_connection

performance_bp = Blueprint('performance', __name__)

@performance_bp.route('/marks/add', methods=['GET', 'POST'])
def add_marks():
    if session.get('role') not in ('teacher', 'moderator', 'superadmin'):
        return "Unauthorized", 403
        
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            if request.method == 'GET':
                teachers = []
                classes = []
                
                if session['role'] in ('moderator', 'superadmin'):
                    cursor.execute("SELECT id, name FROM users WHERE role = 'teacher' ORDER BY name")
                    teachers = cursor.fetchall()
                    cursor.execute("SELECT id, subject, teacher_id FROM classes ORDER BY subject")
                    classes = cursor.fetchall()
                else:
                    cursor.execute("SELECT id, subject, teacher_id FROM classes WHERE teacher_id = %s", (session['user_id'],))
                    classes = cursor.fetchall()
                
                return render_template('mark_performance.html', teachers=teachers, classes=classes)
                
            data = request.form
            class_id = data.get('class_id')
            test_name = data.get('test_name')
            date_recorded = data.get('date_recorded')
            max_marks = float(data.get('max_marks', 100))
            
            # permissions: teacher must own class
            if session['role'] == 'teacher':
                cursor.execute("SELECT 1 FROM classes WHERE id = %s AND teacher_id = %s", (class_id, session['user_id']))
                if not cursor.fetchone():
                    return "Unauthorized for this class", 401

            try:
                for key, value in data.items():
                    if key.startswith('marks_') and value.strip():
                        student_id = key.split('_')[1]
                        # use ON DUPLICATE KEY UPDATE to allow correcting marks easily
                        cursor.execute("""
                            INSERT INTO marks (class_id, student_id, test_name, marks_obtained, max_marks, date_recorded) 
                            VALUES (%s, %s, %s, %s, %s, %s)
                            ON DUPLICATE KEY UPDATE marks_obtained = VALUES(marks_obtained), max_marks = VALUES(max_marks), date_recorded = VALUES(date_recorded)
                        """, (class_id, student_id, test_name, float(value), max_marks, date_recorded))
                conn.commit()
                flash('Marks successfully recorded!', 'success')
            except Exception as e:
                flash(f'Error saving marks: {str(e)}', 'error')
            
            return redirect(url_for('performance.add_marks'))
    finally:
        conn.close()

@performance_bp.route('/marks/view', methods=['GET'])
def view_marks():
    if session.get('role') != 'student':
        return "Unauthorized", 403
        
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT c.subject, m.test_name, m.marks_obtained, m.max_marks, m.date_recorded
                FROM marks m
                JOIN classes c ON m.class_id = c.id
                WHERE m.student_id = %s
                ORDER BY m.date_recorded DESC
            """, (session['user_id'],))
            records = cursor.fetchall()
            return render_template('performance_student.html', marks=records)
    finally:
        conn.close()
@performance_bp.route('/marks/report', methods=['GET'])
def performance_report():
    if session.get('role') not in ('teacher', 'moderator', 'superadmin'):
        return "Unauthorized", 403
        
    class_id = request.args.get('class_id')
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Dropdowns logic (same as add_marks)
            teachers = []
            classes = []
            if session['role'] in ('moderator', 'superadmin'):
                cursor.execute("SELECT id, name FROM users WHERE role = 'teacher' ORDER BY name")
                teachers = cursor.fetchall()
                cursor.execute("SELECT id, subject, teacher_id FROM classes ORDER BY subject")
                classes = cursor.fetchall()
            else:
                cursor.execute("SELECT id, subject, teacher_id FROM classes WHERE teacher_id = %s", (session['user_id'],))
                classes = cursor.fetchall()

            if not class_id:
                return render_template('performance_report.html', teachers=teachers, classes=classes, report_data=None)

            # Security check for teachers
            if session['role'] == 'teacher':
                cursor.execute("SELECT 1 FROM classes WHERE id = %s AND teacher_id = %s", (class_id, session['user_id']))
                if not cursor.fetchone():
                    return "Unauthorized for this class", 401

            # Fetch class info
            cursor.execute("SELECT subject FROM classes WHERE id = %s", (class_id,))
            class_info = cursor.fetchone()

            # Fetch all tests in this class to build columns
            cursor.execute("SELECT DISTINCT test_name FROM marks WHERE class_id = %s ORDER BY date_recorded", (class_id,))
            test_columns = [r['test_name'] for r in cursor.fetchall()]

            # Fetch Student Roster
            cursor.execute("""
                SELECT u.id, u.name 
                FROM enrollments e 
                JOIN users u ON e.student_id = u.id 
                WHERE e.class_id = %s 
                ORDER BY u.name
            """, (class_id,))
            students = cursor.fetchall()

            # Fetch all marks for this class
            cursor.execute("""
                SELECT student_id, test_name, marks_obtained, max_marks
                FROM marks WHERE class_id = %s
            """, (class_id,))
            all_marks = cursor.fetchall()

            # Transpose marks data for table: {student_id: {test_name: marks}}
            marks_map = {}
            for m in all_marks:
                sid = m['student_id']
                if sid not in marks_map:
                    marks_map[sid] = {}
                marks_map[sid][m['test_name']] = f"{m['marks_obtained']} / {m['max_marks']}"

            return render_template('performance_report.html', 
                                   teachers=teachers, 
                                   classes=classes, 
                                   class_info=class_info,
                                   test_columns=test_columns,
                                   students=students,
                                   marks_map=marks_map,
                                   selected_class=int(class_id))
    finally:
        conn.close()
