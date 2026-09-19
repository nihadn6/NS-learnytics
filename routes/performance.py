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
    selected_test = request.args.get('test_name', '').strip()
    selected_teacher = request.args.get('teacher_id', type=int)
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            teachers = []
            classes = []
            if session['role'] in ('moderator', 'superadmin'):
                cursor.execute("SELECT id, name FROM users WHERE role = 'teacher' ORDER BY name")
                teachers = cursor.fetchall()
                cursor.execute("SELECT id, subject, teacher_id FROM classes ORDER BY subject")
                classes = cursor.fetchall()
                # Fetch distinct exams per class grouped strictly by class_id and test_name
                cursor.execute("""
                    SELECT class_id, test_name, MAX(max_marks) as max_marks, MIN(date_recorded) as date_recorded 
                    FROM marks 
                    GROUP BY class_id, test_name
                    ORDER BY MIN(date_recorded) ASC, test_name ASC
                """)
                test_rows = cursor.fetchall()
            else:
                cursor.execute("SELECT id, subject, teacher_id FROM classes WHERE teacher_id = %s ORDER BY subject", (session['user_id'],))
                classes = cursor.fetchall()
                cursor.execute("""
                    SELECT m.class_id, m.test_name, MAX(m.max_marks) as max_marks, MIN(m.date_recorded) as date_recorded
                    FROM marks m
                    JOIN classes c ON m.class_id = c.id
                    WHERE c.teacher_id = %s
                    GROUP BY m.class_id, m.test_name
                    ORDER BY MIN(m.date_recorded) ASC, m.test_name ASC
                """, (session['user_id'],))
                test_rows = cursor.fetchall()

            # Map unique tests by class_id for instant client-side dropdown reactivity
            tests_by_class = {}
            for r in test_rows:
                cid = str(r['class_id'])
                if cid not in tests_by_class:
                    tests_by_class[cid] = []
                tests_by_class[cid].append({
                    'test_name': r['test_name'],
                    'date_recorded': str(r['date_recorded']) if r.get('date_recorded') else '',
                    'max_marks': float(r['max_marks']) if r.get('max_marks') else 100.0
                })

            if not class_id:
                return render_template(
                    'performance_report.html', 
                    teachers=teachers, 
                    classes=classes, 
                    tests_by_class=tests_by_class,
                    class_tests=[],
                    selected_class=None,
                    selected_teacher=selected_teacher,
                    selected_test='',
                    report_data=None
                )

            # Security check for teachers
            if session['role'] == 'teacher':
                cursor.execute("SELECT 1 FROM classes WHERE id = %s AND teacher_id = %s", (class_id, session['user_id']))
                if not cursor.fetchone():
                    return "Unauthorized for this class", 401

            # Fetch class info
            cursor.execute("SELECT id, subject, teacher_id FROM classes WHERE id = %s", (class_id,))
            class_info = cursor.fetchone()
            if not class_info:
                return "Class not found", 404

            # Ensure teacher dropdown reflects the class's teacher if not explicitly set
            if not selected_teacher and class_info:
                selected_teacher = class_info['teacher_id']

            # Fetch strictly distinct assessments conducted for this specific class
            cursor.execute("""
                SELECT test_name, MAX(max_marks) as max_marks, MIN(date_recorded) as date_recorded
                FROM marks 
                WHERE class_id = %s 
                GROUP BY test_name
                ORDER BY MIN(date_recorded) ASC, test_name ASC
            """, (class_id,))
            class_tests = cursor.fetchall()

            # Determine columns to display based on exam filter (strictly unique to this class)
            if selected_test:
                matched_tests = [t['test_name'] for t in class_tests if t['test_name'] == selected_test]
                test_columns = matched_tests if matched_tests else [selected_test]
            else:
                test_columns = [t['test_name'] for t in class_tests]

            # Fetch Student Roster
            cursor.execute("""
                SELECT u.id, u.name 
                FROM enrollments e 
                JOIN users u ON e.student_id = u.id 
                WHERE e.class_id = %s 
                ORDER BY u.name
            """, (class_id,))
            students = cursor.fetchall()

            # Fetch marks for this class (filtered by exam if requested)
            if selected_test:
                cursor.execute("""
                    SELECT student_id, test_name, marks_obtained, max_marks, date_recorded
                    FROM marks 
                    WHERE class_id = %s AND test_name = %s
                """, (class_id, selected_test))
            else:
                cursor.execute("""
                    SELECT student_id, test_name, marks_obtained, max_marks, date_recorded
                    FROM marks 
                    WHERE class_id = %s
                """, (class_id,))
            all_marks = cursor.fetchall()

            # Transpose marks data for table: {student_id: {test_name: {'display': '85 / 100', 'obtained': 85, 'max': 100, 'pct': 85.0}}}
            marks_map = {}
            for m in all_marks:
                sid = m['student_id']
                tname = m['test_name']
                if sid not in marks_map:
                    marks_map[sid] = {}
                obt = float(m['marks_obtained'])
                mx = float(m['max_marks']) if m.get('max_marks') else 100.0
                pct = (obt / mx * 100.0) if mx > 0 else 0.0
                marks_map[sid][tname] = {
                    'display': f"{obt:g} / {mx:g}",
                    'obtained': obt,
                    'max_marks': mx,
                    'pct': round(pct, 1)
                }

            # Calculate Exam Analytics when a specific exam is chosen
            exam_stats = None
            if selected_test and all_marks:
                scores = [float(m['marks_obtained']) for m in all_marks]
                max_score = float(all_marks[0]['max_marks']) if all_marks[0].get('max_marks') else 100.0
                pct_scores = [(s / max_score * 100.0) if max_score > 0 else 0.0 for s in scores]
                pass_count = sum(1 for p in pct_scores if p >= 50.0)
                exam_stats = {
                    'test_name': selected_test,
                    'date_recorded': str(all_marks[0]['date_recorded']) if all_marks[0].get('date_recorded') else '',
                    'max_marks': max_score,
                    'turnout': len(scores),
                    'roster_count': len(students),
                    'turnout_pct': round((len(scores) / len(students) * 100.0), 1) if students else 0,
                    'avg_score': round(sum(scores) / len(scores), 2) if scores else 0,
                    'avg_pct': round(sum(pct_scores) / len(pct_scores), 1) if pct_scores else 0,
                    'highest_score': max(scores) if scores else 0,
                    'highest_pct': round((max(scores) / max_score * 100.0), 1) if max_score > 0 else 0,
                    'lowest_score': min(scores) if scores else 0,
                    'lowest_pct': round((min(scores) / max_score * 100.0), 1) if max_score > 0 else 0,
                    'pass_count': pass_count,
                    'pass_rate': round((pass_count / len(scores) * 100.0), 1) if scores else 0
                }

            return render_template(
                'performance_report.html', 
                teachers=teachers, 
                classes=classes, 
                tests_by_class=tests_by_class,
                class_info=class_info,
                class_tests=class_tests,
                test_columns=test_columns,
                students=students,
                marks_map=marks_map,
                exam_stats=exam_stats,
                selected_class=int(class_id),
                selected_teacher=selected_teacher,
                selected_test=selected_test
            )
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

