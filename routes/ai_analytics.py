from flask import Blueprint, render_template, request, session, redirect, url_for, jsonify
from services.ai_risk_predictor import risk_predictor
from services.ai_grade_forecaster import grade_forecaster
from database.db import get_db_connection

ai_analytics_bp = Blueprint('ai_analytics', __name__)

@ai_analytics_bp.route('/ai/at-risk-students', methods=['GET'])
def at_risk_dashboard():
    role = session.get('role')
    user_id = session.get('user_id')

    if role not in ('superadmin', 'admin', 'teacher', 'moderator'):
        return redirect(url_for('auth.login'))

    teacher_id = request.args.get('teacher_id')
    class_id = request.args.get('class_id')
    search_query = request.args.get('search', '').strip()

    teachers = []
    classes = []
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            if role == 'teacher':
                teacher_filter = user_id
                cursor.execute("SELECT id, subject FROM classes WHERE teacher_id = %s ORDER BY subject", (user_id,))
                classes = cursor.fetchall()
            else:
                teacher_filter = teacher_id
                cursor.execute("SELECT id, name FROM users WHERE role = 'teacher' ORDER BY name")
                teachers = cursor.fetchall()

                if teacher_id:
                    cursor.execute("""
                        SELECT c.id, c.subject, c.teacher_id, u.name as teacher_name 
                        FROM classes c 
                        LEFT JOIN users u ON c.teacher_id = u.id 
                        WHERE c.teacher_id = %s 
                        ORDER BY c.subject
                    """, (teacher_id,))
                else:
                    cursor.execute("""
                        SELECT c.id, c.subject, c.teacher_id, u.name as teacher_name 
                        FROM classes c 
                        LEFT JOIN users u ON c.teacher_id = u.id 
                        ORDER BY c.subject
                    """)
                classes = cursor.fetchall()
    finally:
        conn.close()

    # Predict risks for students
    student_risks = risk_predictor.get_all_student_risks(teacher_id=teacher_filter, class_id=class_id)

    # Filter by search query if provided
    if search_query:
        sq = search_query.lower()
        filtered = []
        for s in student_risks:
            name_match = sq in (s.get('name') or '').lower()
            email_match = sq in (s.get('email') or '').lower()
            factor_match = any(sq in f.lower() for f in s.get('risk_factors', []))
            if name_match or email_match or factor_match:
                filtered.append(s)
        student_risks = filtered

    # Compute summary counters
    high_count = sum(1 for s in student_risks if s['risk_level'] == 'HIGH')
    medium_count = sum(1 for s in student_risks if s['risk_level'] == 'MEDIUM')
    low_count = sum(1 for s in student_risks if s['risk_level'] == 'LOW')
    total_students = len(student_risks)

    avg_risk_score = round(sum(s['risk_pct'] for s in student_risks) / total_students, 1) if total_students > 0 else 0.0

    return render_template('at_risk_students.html',
                           student_risks=student_risks,
                           classes=classes,
                           teachers=teachers,
                           selected_teacher_id=teacher_id,
                           selected_class_id=class_id,
                           search_query=search_query,
                           high_count=high_count,
                           medium_count=medium_count,
                           low_count=low_count,
                           total_students=total_students,
                           avg_risk_score=avg_risk_score,
                           role=role)

@ai_analytics_bp.route('/ai/grade-forecasting', methods=['GET'])
def grade_forecasting_dashboard():
    role = session.get('role')
    user_id = session.get('user_id')

    if role not in ('superadmin', 'admin', 'teacher', 'student', 'parent'):
        return redirect(url_for('auth.login'))

    teacher_id = request.args.get('teacher_id')
    class_id = request.args.get('class_id')
    search_query = request.args.get('search', '').strip()
    
    conn = get_db_connection()
    classes = []
    teachers = []
    forecast_data = []
    try:
        with conn.cursor() as cursor:
            if role == 'teacher':
                cursor.execute("SELECT id, subject FROM classes WHERE teacher_id = %s ORDER BY subject", (user_id,))
                classes = cursor.fetchall()
                forecast_data = grade_forecaster.forecast_all_students(teacher_id=user_id, class_id=class_id)
            elif role in ('superadmin', 'admin', 'moderator'):
                # Fetch all teachers for admin dropdown
                cursor.execute("SELECT id, name FROM users WHERE role = 'teacher' ORDER BY name")
                teachers = cursor.fetchall()

                # Fetch classes (optionally filtered if teacher_id is selected)
                if teacher_id:
                    cursor.execute("""
                        SELECT c.id, c.subject, c.teacher_id, u.name as teacher_name 
                        FROM classes c 
                        LEFT JOIN users u ON c.teacher_id = u.id 
                        WHERE c.teacher_id = %s 
                        ORDER BY c.subject
                    """, (teacher_id,))
                else:
                    cursor.execute("""
                        SELECT c.id, c.subject, c.teacher_id, u.name as teacher_name 
                        FROM classes c 
                        LEFT JOIN users u ON c.teacher_id = u.id 
                        ORDER BY c.subject
                    """)
                classes = cursor.fetchall()
                forecast_data = grade_forecaster.forecast_all_students(teacher_id=teacher_id, class_id=class_id)
            elif role == 'student':
                cursor.execute("""
                    SELECT DISTINCT c.id, c.subject 
                    FROM classes c
                    JOIN enrollments e ON e.class_id = c.id
                    WHERE e.student_id = %s
                    ORDER BY c.subject
                """, (user_id,))
                classes = cursor.fetchall()
                f_single = grade_forecaster.forecast_student_performance(user_id, class_id=class_id)
                forecast_data = [f_single] if f_single else []
            elif role == 'parent':
                target_student_id = session.get('selected_student_id')
                if not target_student_id:
                    cursor.execute("SELECT student_id FROM parent_student_links WHERE parent_id = %s AND status = 'approved' LIMIT 1", (user_id,))
                    row = cursor.fetchone()
                    target_student_id = row['student_id'] if row else None

                if target_student_id:
                    cursor.execute("""
                        SELECT DISTINCT c.id, c.subject 
                        FROM classes c
                        JOIN enrollments e ON e.class_id = c.id
                        WHERE e.student_id = %s
                        ORDER BY c.subject
                    """, (target_student_id,))
                    classes = cursor.fetchall()
                else:
                    classes = []

                f_single = grade_forecaster.forecast_student_performance(target_student_id, class_id=class_id) if target_student_id else None
                forecast_data = [f_single] if f_single else []

            # Optional server-side search filter
            if search_query:
                sq = search_query.lower()
                filtered = []
                for s in forecast_data:
                    name_match = sq in (s.get('name') or '').lower()
                    email_match = sq in (s.get('email') or '').lower()
                    subj_match = any(sq in (f.get('subject') or '').lower() or sq in (f.get('teacher_name') or '').lower() for f in s.get('forecasts', []))
                    if name_match or email_match or subj_match:
                        filtered.append(s)
                forecast_data = filtered
    finally:
        conn.close()

    return render_template('grade_forecasting.html',
                           forecast_data=forecast_data,
                           classes=classes,
                           teachers=teachers,
                           selected_teacher_id=teacher_id,
                           selected_class_id=class_id,
                           search_query=search_query,
                           role=role)

@ai_analytics_bp.route('/api/ai/predict-student/<int:student_id>', methods=['GET'])
def predict_single_student(student_id):
    if session.get('role') not in ('superadmin', 'admin', 'teacher', 'moderator'):
        return jsonify({'error': 'Unauthorized'}), 403

    class_id = request.args.get('class_id')
    analysis = risk_predictor.predict_student_risk(student_id, class_id=class_id)
    if not analysis:
        return jsonify({'error': 'Student not found'}), 404

    return jsonify(analysis)


@ai_analytics_bp.route('/api/ai/student-records/<int:student_id>', methods=['GET'])
def get_student_records(student_id):
    """Fetch consolidated attendance, marks, and fee payment history for a student."""
    if session.get('role') not in ('superadmin', 'admin', 'teacher', 'moderator'):
        return jsonify({'error': 'Unauthorized'}), 403

    raw_class_id = request.args.get('class_id')
    class_id = None
    if raw_class_id and raw_class_id.isdigit():
        class_id = int(raw_class_id)

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # 1. Student details
            cursor.execute("""
                SELECT u.id, u.name, u.email, sp.grade 
                FROM users u 
                LEFT JOIN student_profiles sp ON u.id = sp.user_id 
                WHERE u.id = %s AND u.role = 'student'
            """, (student_id,))
            student = cursor.fetchone()
            if not student:
                return jsonify({'error': 'Student not found'}), 404

            # 2. Selected Class details if filtered
            selected_class = None
            if class_id:
                cursor.execute("SELECT id, subject FROM classes WHERE id = %s", (class_id,))
                selected_class = cursor.fetchone()

            # 3. Attendance history
            if class_id:
                cursor.execute("""
                    SELECT a.id, a.date, a.status, c.subject as class_name, a.class_id
                    FROM attendance a 
                    JOIN classes c ON a.class_id = c.id 
                    WHERE a.student_id = %s AND a.class_id = %s
                    ORDER BY a.date DESC
                """, (student_id, class_id))
            else:
                cursor.execute("""
                    SELECT a.id, a.date, a.status, c.subject as class_name, a.class_id
                    FROM attendance a 
                    JOIN classes c ON a.class_id = c.id 
                    WHERE a.student_id = %s
                    ORDER BY a.date DESC
                """, (student_id,))
            attendance_rows = cursor.fetchall()

            for row in attendance_rows:
                if row.get('date'):
                    row['date'] = row['date'].strftime('%Y-%m-%d')

            total_sessions = len(attendance_rows)
            present_sessions = sum(1 for a in attendance_rows if a['status'] == 'present')
            absent_sessions = sum(1 for a in attendance_rows if a['status'] == 'absent')
            att_pct = round((present_sessions / total_sessions * 100), 1) if total_sessions > 0 else 100.0

            # 4. Exam marks history
            if class_id:
                cursor.execute("""
                    SELECT m.id, m.test_name, m.marks_obtained, m.max_marks, m.date_recorded, c.subject as class_name, m.class_id
                    FROM marks m 
                    JOIN classes c ON m.class_id = c.id 
                    WHERE m.student_id = %s AND m.class_id = %s
                    ORDER BY m.date_recorded DESC
                """, (student_id, class_id))
            else:
                cursor.execute("""
                    SELECT m.id, m.test_name, m.marks_obtained, m.max_marks, m.date_recorded, c.subject as class_name, m.class_id
                    FROM marks m 
                    JOIN classes c ON m.class_id = c.id 
                    WHERE m.student_id = %s
                    ORDER BY m.date_recorded DESC
                """, (student_id,))
            marks_rows = cursor.fetchall()

            for row in marks_rows:
                if row.get('date_recorded'):
                    row['date_recorded'] = row['date_recorded'].strftime('%Y-%m-%d')
                obtained = float(row.get('marks_obtained') or 0)
                max_m = float(row.get('max_marks') or 100)
                row['marks_obtained'] = obtained
                row['max_marks'] = max_m
                row['percentage'] = round((obtained / max_m * 100), 1) if max_m > 0 else 0.0

            avg_mark = round(sum(m['percentage'] for m in marks_rows) / len(marks_rows), 1) if marks_rows else None

            # 5. Fee payments history
            if class_id:
                cursor.execute("""
                    SELECT p.id, p.amount, p.payment_date, p.period, c.subject as class_name, p.class_id
                    FROM payments p 
                    JOIN classes c ON p.class_id = c.id 
                    WHERE p.student_id = %s AND p.class_id = %s
                    ORDER BY p.payment_date DESC
                """, (student_id, class_id))
            else:
                cursor.execute("""
                    SELECT p.id, p.amount, p.payment_date, p.period, c.subject as class_name, p.class_id
                    FROM payments p 
                    JOIN classes c ON p.class_id = c.id 
                    WHERE p.student_id = %s
                    ORDER BY p.payment_date DESC
                """, (student_id,))
            payments_rows = cursor.fetchall()

            for row in payments_rows:
                if row.get('payment_date'):
                    row['payment_date'] = row['payment_date'].strftime('%Y-%m-%d')
                row['amount'] = float(row.get('amount') or 0)

            total_paid = sum(p['amount'] for p in payments_rows)

            return jsonify({
                'student': student,
                'class': selected_class,
                'attendance': {
                    'total_sessions': total_sessions,
                    'present_sessions': present_sessions,
                    'absent_sessions': absent_sessions,
                    'percentage': att_pct,
                    'records': attendance_rows
                },
                'marks': {
                    'average': avg_mark,
                    'total_tests': len(marks_rows),
                    'records': marks_rows
                },
                'payments': {
                    'total_paid': total_paid,
                    'total_transactions': len(payments_rows),
                    'records': payments_rows
                }
            })
    finally:
        conn.close()

