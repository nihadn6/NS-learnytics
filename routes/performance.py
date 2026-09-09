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
                        
                        # Notify Parents
                        try:
                            from utils.notifications import notify_parents_of_marks
                            cursor.execute("SELECT name FROM users WHERE id = %s", (student_id,))
                            s_name = cursor.fetchone()['name']
                            cursor.execute("SELECT subject FROM classes WHERE id = %s", (class_id,))
                            c_name = cursor.fetchone()['subject']
                            notify_parents_of_marks(student_id, s_name, c_name, test_name, float(value), max_marks)
                        except Exception as e:
                            print(f"Marks Notification error: {e}")

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

@performance_bp.route('/marks/template/<int:class_id>', methods=['GET'])
def download_marks_template(class_id):
    if session.get('role') not in ('teacher', 'moderator', 'superadmin'):
        return "Unauthorized", 403

    import csv
    import io
    from flask import Response

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT u.id, u.name 
                FROM enrollments e 
                JOIN users u ON e.student_id = u.id 
                WHERE e.class_id = %s 
                ORDER BY u.name
            """, (class_id,))
            students = cursor.fetchall()

            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(['student_id', 'student_name', 'marks_obtained'])
            for s in students:
                writer.writerow([s['id'], s['name'], ''])

            response = Response(output.getvalue(), mimetype='text/csv')
            response.headers['Content-Disposition'] = f'attachment; filename=marks_template_class_{class_id}.csv'
            return response
    finally:
        conn.close()

@performance_bp.route('/marks/bulk-upload', methods=['POST'])
def bulk_upload_marks():
    if session.get('role') not in ('teacher', 'moderator', 'superadmin'):
        return "Unauthorized", 403

    import csv
    import io

    class_id = request.form.get('class_id')
    test_name = request.form.get('test_name')
    date_recorded = request.form.get('date_recorded')
    max_marks = float(request.form.get('max_marks', 100))
    file = request.files.get('file')

    if not class_id or not test_name or not date_recorded or not file:
        flash('All fields and CSV file are required.', 'error')
        return redirect(url_for('performance.add_marks'))

    conn = get_db_connection()
    try:
        stream = io.StringIO(file.stream.read().decode("UTF-8"), newline=None)
        csv_reader = csv.DictReader(stream)

        count = 0
        with conn.cursor() as cursor:
            # permissions: teacher must own class
            if session['role'] == 'teacher':
                cursor.execute("SELECT 1 FROM classes WHERE id = %s AND teacher_id = %s", (class_id, session['user_id']))
                if not cursor.fetchone():
                    return "Unauthorized for this class", 401

            for row in csv_reader:
                student_id = row.get('student_id')
                val = row.get('marks_obtained')
                if student_id and val and val.strip():
                    try:
                        marks_obtained = float(val.strip())
                        cursor.execute("""
                            INSERT INTO marks (class_id, student_id, test_name, marks_obtained, max_marks, date_recorded)
                            VALUES (%s, %s, %s, %s, %s, %s)
                            ON DUPLICATE KEY UPDATE marks_obtained = VALUES(marks_obtained), max_marks = VALUES(max_marks), date_recorded = VALUES(date_recorded)
                        """, (class_id, student_id, test_name, marks_obtained, max_marks, date_recorded))
                        count += 1
                        
                        # Notify Parents
                        try:
                            from utils.notifications import notify_parents_of_marks
                            cursor.execute("SELECT name FROM users WHERE id = %s", (student_id,))
                            s_name = cursor.fetchone()['name']
                            cursor.execute("SELECT subject FROM classes WHERE id = %s", (class_id,))
                            c_name = cursor.fetchone()['subject']
                            notify_parents_of_marks(student_id, s_name, c_name, test_name, marks_obtained, max_marks)
                        except Exception as e:
                            print(f"Notification error: {e}")

                    except ValueError:
                        continue

            conn.commit()
            flash(f'Successfully imported marks for {count} student(s)!', 'success')
    except Exception as e:
        flash(f'CSV Upload Error: {str(e)}', 'error')
    finally:
        conn.close()

    return redirect(url_for('performance.add_marks'))

