from flask import Blueprint, render_template, session, redirect, url_for, request, flash, jsonify
from database.db import get_db_connection
import datetime

parent_bp = Blueprint('parent', __name__)

@parent_bp.before_request
def check_parent():
    if session.get('role') != 'parent':
        return redirect(url_for('auth.login'))

@parent_bp.route('/parent/dashboard')
def dashboard():
    parent_id = session['user_id']
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Fetch approved linked students
            cursor.execute("""
                SELECT u.id, u.name, sp.grade 
                FROM parent_student_links psl
                JOIN users u ON psl.student_id = u.id
                JOIN student_profiles sp ON u.id = sp.user_id
                WHERE psl.parent_id = %s AND psl.status = 'approved'
            """, (parent_id,))
            students = cursor.fetchall()

            # Handle student selection (session-based switcher)
            selected_student_id = request.args.get('student_id', session.get('selected_student_id'))
            
            # If no student selected but we have linked students, pick the first one
            if not selected_student_id and students:
                selected_student_id = students[0]['id']
            
            # Verify the parent is allowed to see this student
            current_student = None
            if selected_student_id:
                current_student = next((s for s in students if str(s['id']) == str(selected_student_id)), None)
                if current_student:
                    session['selected_student_id'] = selected_student_id
                else:
                    selected_student_id = None

            # Fetch pending requests
            cursor.execute("""
                SELECT u.name, psl.status, psl.created_at
                FROM parent_student_links psl
                JOIN users u ON psl.student_id = u.id
                WHERE psl.parent_id = %s AND psl.status != 'approved'
            """, (parent_id,))
            pending_requests = cursor.fetchall()

            # If a student is selected, fetch their data
            attendance_summary = []
            recent_marks = []
            recent_payments = []
            child_teachers = []
            child_avg_mark = None
            child_att_pct = 100.0
            child_forecast = None
            
            if selected_student_id:
                # Attendance — COALESCE ensures percentage is never NULL
                cursor.execute("""
                    SELECT c.subject, 
                           COALESCE(
                               LEAST(100, GREATEST(0,
                                   SUM(CASE WHEN a.status = 'present' THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(*), 0)
                               ))
                           , 0) as percentage
                    FROM attendance a
                    JOIN classes c ON a.class_id = c.id
                    WHERE a.student_id = %s
                    GROUP BY c.id
                    HAVING COUNT(*) > 0
                """, (selected_student_id,))
                attendance_summary = cursor.fetchall()

                # Overall Attendance %
                cursor.execute("""
                    SELECT SUM(CASE WHEN status = 'present' THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(*), 0) as pct
                    FROM attendance WHERE student_id = %s
                """, (selected_student_id,))
                att_row = cursor.fetchone()
                child_att_pct = float(att_row['pct']) if att_row and att_row['pct'] is not None else 100.0

                # Marks
                cursor.execute("""
                    SELECT c.subject, m.test_name, m.marks_obtained, m.max_marks, m.date_recorded
                    FROM marks m
                    JOIN classes c ON m.class_id = c.id
                    WHERE m.student_id = %s
                    ORDER BY m.date_recorded DESC LIMIT 5
                """, (selected_student_id,))
                recent_marks = cursor.fetchall()

                # Average Mark %
                cursor.execute("""
                    SELECT AVG(marks_obtained/max_marks * 100) as avg_score 
                    FROM marks WHERE student_id = %s
                """, (selected_student_id,))
                avg_row = cursor.fetchone()
                child_avg_mark = round(float(avg_row['avg_score']), 1) if avg_row and avg_row['avg_score'] is not None else None

                # Payments
                cursor.execute("""
                    SELECT c.subject, p.amount, p.payment_date, p.period
                    FROM payments p
                    JOIN classes c ON p.class_id = c.id
                    WHERE p.student_id = %s
                    ORDER BY p.payment_date DESC LIMIT 5
                """, (selected_student_id,))
                recent_payments = cursor.fetchall()

                # Associated Class Teachers for 1-Click Messaging
                cursor.execute("""
                    SELECT DISTINCT u.id as teacher_id, u.name as teacher_name, c.subject
                    FROM enrollments e
                    JOIN classes c ON e.class_id = c.id
                    JOIN users u ON c.teacher_id = u.id
                    WHERE e.student_id = %s
                    ORDER BY c.subject
                """, (selected_student_id,))
                child_teachers = cursor.fetchall()

                # AI Grade Forecast for Child
                try:
                    from services.ai_grade_forecaster import grade_forecaster
                    child_forecast = grade_forecaster.forecast_student_performance(selected_student_id)
                except Exception as e:
                    child_forecast = None

            # Notifications
            cursor.execute("SELECT message, created_at FROM notifications WHERE user_id = %s ORDER BY created_at DESC LIMIT 5", (parent_id,))
            notifications = cursor.fetchall()

            return render_template('parent_dashboard.html', 
                                 students=students, 
                                 current_student=current_student,
                                 pending_requests=pending_requests,
                                 attendance_summary=attendance_summary,
                                 recent_marks=recent_marks,
                                 recent_payments=recent_payments,
                                 child_teachers=child_teachers,
                                 child_avg_mark=child_avg_mark,
                                 child_att_pct=child_att_pct,
                                 child_forecast=child_forecast,
                                 notifications=notifications)
    finally:
        conn.close()

@parent_bp.route('/parent/link-request', methods=['GET', 'POST'])
def link_request():
    if request.method == 'GET':
        return render_template('parent_link_request.html')
    
    student_identifier = request.form.get('student_identifier') # Name or Email
    parent_id = session['user_id']
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Find student by email or name
            cursor.execute("SELECT id, name FROM users WHERE (email = %s OR name = %s) AND role = 'student'", 
                           (student_identifier, student_identifier))
            student = cursor.fetchone()
            
            if not student:
                flash('Student not found. Please verify the name or email.', 'error')
                return render_template('parent_link_request.html')
            
            # Check if already linked or requested
            cursor.execute("SELECT status FROM parent_student_links WHERE parent_id = %s AND student_id = %s", 
                           (parent_id, student['id']))
            existing = cursor.fetchone()
            
            if existing:
                flash(f'A request for {student["name"]} already exists (Status: {existing["status"]}).', 'warning')
                return redirect(url_for('parent.dashboard'))
            
            # Create link request
            cursor.execute("INSERT INTO parent_student_links (parent_id, student_id, status) VALUES (%s, %s, 'pending')", 
                           (parent_id, student['id']))
            conn.commit()
            flash(f'Link request for {student["name"]} submitted! Waiting for Admin/Teacher approval.', 'success')
            return redirect(url_for('parent.dashboard'))
    finally:
        conn.close()

@parent_bp.route('/parent/report/<int:student_id>')
def progress_report(student_id):
    parent_id = session['user_id']
    
    # Filter parameters
    class_id = request.args.get('class_id')
    teacher_id = request.args.get('teacher_id')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Security check: Ensure parent is approved for this student
            cursor.execute("""
                SELECT u.id, u.name, u.email, sp.grade
                FROM parent_student_links psl
                JOIN users u ON psl.student_id = u.id
                LEFT JOIN student_profiles sp ON u.id = sp.user_id
                WHERE psl.parent_id = %s AND psl.student_id = %s AND psl.status = 'approved'
            """, (parent_id, student_id))
            student = cursor.fetchone()
            
            if not student:
                flash('Unauthorized access or student link not approved.', 'error')
                return redirect(url_for('parent.dashboard'))

            # Fetch enrolled classes and teachers for filter dropdowns
            cursor.execute("""
                SELECT c.id, c.subject, c.teacher_id, u.name as teacher_name
                FROM enrollments e
                JOIN classes c ON e.class_id = c.id
                JOIN users u ON c.teacher_id = u.id
                WHERE e.student_id = %s
                ORDER BY c.subject
            """, (student_id,))
            enrolled_classes = cursor.fetchall()

            # Unique teachers
            teachers = {}
            for ec in enrolled_classes:
                teachers[ec['teacher_id']] = ec['teacher_name']

            # 1. Attendance Query
            att_sql = """
                SELECT c.subject, u.name as teacher_name,
                       COUNT(a.id) as total_sessions,
                       SUM(CASE WHEN a.status = 'present' THEN 1 ELSE 0 END) as present_sessions,
                       SUM(CASE WHEN a.status = 'absent' THEN 1 ELSE 0 END) as absent_sessions,
                       SUM(CASE WHEN a.status = 'present' THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(a.id), 0) as percentage
                FROM enrollments e
                JOIN classes c ON e.class_id = c.id
                JOIN users u ON c.teacher_id = u.id
                LEFT JOIN attendance a ON a.class_id = c.id AND a.student_id = %s
                WHERE e.student_id = %s
            """
            att_params = [student_id, student_id]
            if class_id:
                att_sql += " AND c.id = %s"
                att_params.append(class_id)
            if teacher_id:
                att_sql += " AND c.teacher_id = %s"
                att_params.append(teacher_id)
            if start_date and end_date:
                att_sql += " AND (a.date IS NULL OR (a.date >= %s AND a.date <= %s))"
                att_params.extend([start_date, end_date])
            att_sql += " GROUP BY c.id, c.subject, u.name"

            cursor.execute(att_sql, tuple(att_params))
            attendance = cursor.fetchall()

            # 2. Exam Marks Query
            marks_sql = """
                SELECT c.subject, u.name as teacher_name, m.test_name, m.marks_obtained, m.max_marks, m.date_recorded
                FROM marks m
                JOIN classes c ON m.class_id = c.id
                JOIN users u ON c.teacher_id = u.id
                WHERE m.student_id = %s
            """
            marks_params = [student_id]
            if class_id:
                marks_sql += " AND c.id = %s"
                marks_params.append(class_id)
            if teacher_id:
                marks_sql += " AND c.teacher_id = %s"
                marks_params.append(teacher_id)
            if start_date and end_date:
                marks_sql += " AND m.date_recorded >= %s AND m.date_recorded <= %s"
                marks_params.extend([start_date, end_date])
            marks_sql += " ORDER BY m.date_recorded DESC"

            cursor.execute(marks_sql, tuple(marks_params))
            marks = cursor.fetchall()

            # 3. Payment History Query
            pay_sql = """
                SELECT c.subject, u.name as teacher_name, p.amount, p.payment_date, p.period
                FROM payments p
                JOIN classes c ON p.class_id = c.id
                JOIN users u ON c.teacher_id = u.id
                WHERE p.student_id = %s
            """
            pay_params = [student_id]
            if class_id:
                pay_sql += " AND c.id = %s"
                pay_params.append(class_id)
            if teacher_id:
                pay_sql += " AND c.teacher_id = %s"
                pay_params.append(teacher_id)
            if start_date and end_date:
                pay_sql += " AND p.payment_date >= %s AND p.payment_date <= %s"
                pay_params.extend([start_date, end_date])
            pay_sql += " ORDER BY p.payment_date DESC"

            cursor.execute(pay_sql, tuple(pay_params))
            payments = cursor.fetchall()

            now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')

            return render_template('student_report.html',
                                 student=student,
                                 enrolled_classes=enrolled_classes,
                                 teachers=teachers,
                                 selected_class_id=class_id,
                                 selected_teacher_id=teacher_id,
                                 start_date=start_date,
                                 end_date=end_date,
                                 attendance=attendance,
                                 marks=marks,
                                 payments=payments,
                                 generated_at=now)
    finally:
        conn.close()

