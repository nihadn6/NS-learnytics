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

    # Fetch current user's risk preferences
    user_risk_settings = risk_predictor.get_user_risk_settings(user_id)

    # Predict risks for students honoring teacher's customized formula & thresholds
    student_risks = risk_predictor.get_all_student_risks(teacher_id=teacher_filter, class_id=class_id, user_risk_settings=user_risk_settings)

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
                           risk_settings=user_risk_settings,
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
    
    # Retrieve user-customized grading thresholds & component weights
    user_forecast_settings = grade_forecaster.get_user_forecast_settings(user_id)

    conn = get_db_connection()
    classes = []
    teachers = []
    forecast_data = []
    try:
        with conn.cursor() as cursor:
            if role == 'teacher':
                cursor.execute("SELECT id, subject FROM classes WHERE teacher_id = %s ORDER BY subject", (user_id,))
                classes = cursor.fetchall()
                forecast_data = grade_forecaster.forecast_all_students(
                    teacher_id=user_id, 
                    class_id=class_id, 
                    user_forecast_settings=user_forecast_settings
                )
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
                forecast_data = grade_forecaster.forecast_all_students(
                    teacher_id=teacher_id, 
                    class_id=class_id, 
                    user_forecast_settings=user_forecast_settings
                )
            elif role == 'student':
                cursor.execute("""
                    SELECT DISTINCT c.id, c.subject 
                    FROM classes c
                    JOIN enrollments e ON e.class_id = c.id
                    WHERE e.student_id = %s
                    ORDER BY c.subject
                """, (user_id,))
                classes = cursor.fetchall()
                f_single = grade_forecaster.forecast_student_performance(
                    user_id, 
                    class_id=class_id, 
                    user_forecast_settings=user_forecast_settings
                )
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

                f_single = grade_forecaster.forecast_student_performance(
                    target_student_id, 
                    class_id=class_id, 
                    user_forecast_settings=user_forecast_settings
                ) if target_student_id else None
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

    # Empirical model backtest validation metrics
    accuracy_metrics = grade_forecaster.evaluate_model_accuracy(
        teacher_id=user_id if role == 'teacher' else teacher_id,
        class_id=class_id
    )

    return render_template('grade_forecasting.html',
                           forecast_data=forecast_data,
                           classes=classes,
                           teachers=teachers,
                           selected_teacher_id=teacher_id,
                           selected_class_id=class_id,
                           search_query=search_query,
                           accuracy_metrics=accuracy_metrics,
                           forecast_settings=user_forecast_settings,
                           role=role)

@ai_analytics_bp.route('/api/ai/predict-student/<int:student_id>', methods=['GET'])
def predict_single_student(student_id):
    role = session.get('role')
    user_id = session.get('user_id')
    if role not in ('superadmin', 'admin', 'teacher', 'moderator'):
        return jsonify({'error': 'Unauthorized'}), 403

    class_id = request.args.get('class_id')
    user_risk_settings = risk_predictor.get_user_risk_settings(user_id)
    analysis = risk_predictor.predict_student_risk(student_id, class_id=class_id, settings=user_risk_settings)
    if not analysis:
        return jsonify({'error': 'Student not found'}), 404

    return jsonify(analysis)

@ai_analytics_bp.route('/ai/risk-preferences', methods=['POST'])
def save_risk_preferences():
    role = session.get('role')
    user_id = session.get('user_id')
    if role not in ('superadmin', 'admin', 'teacher', 'moderator') or not user_id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    data = request.get_json() or {}
    try:
        preset_name = str(data.get('preset_name') or 'custom').strip()
        att_weight = float(data.get('att_weight', 0.40))
        marks_weight = float(data.get('marks_weight', 0.40))
        rec_att_weight = float(data.get('rec_att_weight', 0.10))
        trend_weight = float(data.get('trend_weight', 0.10))
        
        min_attendance_threshold = float(data.get('min_attendance_threshold', 75.0))
        min_marks_threshold = float(data.get('min_marks_threshold', 50.0))
        high_risk_threshold = float(data.get('high_risk_threshold', 55.0))
        medium_risk_threshold = float(data.get('medium_risk_threshold', 25.0))

        # Basic bounds validation
        att_weight = max(0.0, min(1.0, att_weight))
        marks_weight = max(0.0, min(1.0, marks_weight))
        rec_att_weight = max(0.0, min(1.0, rec_att_weight))
        trend_weight = max(0.0, min(1.0, trend_weight))

        settings = {
            'preset_name': preset_name,
            'att_weight': att_weight,
            'marks_weight': marks_weight,
            'rec_att_weight': rec_att_weight,
            'trend_weight': trend_weight,
            'min_attendance_threshold': max(10.0, min(100.0, min_attendance_threshold)),
            'min_marks_threshold': max(10.0, min(100.0, min_marks_threshold)),
            'high_risk_threshold': max(10.0, min(100.0, high_risk_threshold)),
            'medium_risk_threshold': max(5.0, min(90.0, medium_risk_threshold))
        }

        success = risk_predictor.save_user_risk_settings(user_id, settings)
        if success:
            return jsonify({'success': True, 'message': 'Custom risk radar preferences saved successfully!'})
        return jsonify({'success': False, 'message': 'Failed to save preferences to database.'}), 500
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400

@ai_analytics_bp.route('/ai/risk-preferences/reset', methods=['POST'])
def reset_risk_preferences():
    role = session.get('role')
    user_id = session.get('user_id')
    if role not in ('superadmin', 'admin', 'teacher', 'moderator') or not user_id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    success = risk_predictor.reset_user_risk_settings(user_id)
    if success:
        return jsonify({'success': True, 'message': 'Risk Radar formula successfully reset to default standard configuration.'})
    return jsonify({'success': False, 'message': 'Failed to reset preferences.'}), 500


@ai_analytics_bp.route('/ai/grade-forecast-preferences', methods=['POST'])
def save_grade_forecast_preferences():
    role = session.get('role')
    user_id = session.get('user_id')
    if role not in ('superadmin', 'admin', 'teacher', 'moderator') or not user_id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    try:
        data = request.get_json() or {}
        preset_name = data.get('preset_name', 'custom')
        cutoff_a = float(data.get('cutoff_a', 75.0))
        cutoff_b = float(data.get('cutoff_b', 65.0))
        cutoff_c = float(data.get('cutoff_c', 50.0))
        cutoff_s = float(data.get('cutoff_s', 35.0))
        exam_weight = float(data.get('exam_weight', 0.90))
        hw_weight = float(data.get('hw_weight', 0.10))
        target_threshold = float(data.get('target_threshold', 50.0))

        if not (0.0 <= cutoff_s < cutoff_c < cutoff_b < cutoff_a <= 100.0):
            return jsonify({'success': False, 'message': 'Grade cutoffs must be strictly ascending: S < C < B < A'}), 400

        total_w = exam_weight + hw_weight
        if total_w <= 0:
            return jsonify({'success': False, 'message': 'Sum of weights must be greater than zero.'}), 400

        settings = {
            'preset_name': preset_name,
            'cutoff_a': max(10.0, min(100.0, cutoff_a)),
            'cutoff_b': max(10.0, min(100.0, cutoff_b)),
            'cutoff_c': max(10.0, min(100.0, cutoff_c)),
            'cutoff_s': max(5.0, min(100.0, cutoff_s)),
            'exam_weight': max(0.0, min(1.0, exam_weight / total_w)),
            'hw_weight': max(0.0, min(1.0, hw_weight / total_w)),
            'target_threshold': max(10.0, min(100.0, target_threshold))
        }

        success = grade_forecaster.save_user_forecast_settings(user_id, settings)
        if success:
            return jsonify({'success': True, 'message': 'Grade Forecaster scale & weight preferences saved successfully!'})
        return jsonify({'success': False, 'message': 'Failed to save preferences to database.'}), 500
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400


@ai_analytics_bp.route('/ai/grade-forecast-preferences/reset', methods=['POST'])
def reset_grade_forecast_preferences():
    role = session.get('role')
    user_id = session.get('user_id')
    if role not in ('superadmin', 'admin', 'teacher', 'moderator') or not user_id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    success = grade_forecaster.reset_user_forecast_settings(user_id)
    if success:
        return jsonify({'success': True, 'message': 'Grade Forecaster successfully reset to default National G.C.E. standard.'})
    return jsonify({'success': False, 'message': 'Failed to reset preferences.'}), 500



@ai_analytics_bp.route('/api/ai/student-records/<int:student_id>', methods=['GET'])
def get_student_records(student_id):
    """Fetch consolidated attendance, marks, and fee payment history for a student."""
    role = session.get('role')
    user_id = session.get('user_id')
    if role not in ('superadmin', 'admin', 'teacher', 'moderator'):
        return jsonify({'error': 'Unauthorized'}), 403

    raw_class_id = request.args.get('class_id')
    class_id = None
    if raw_class_id and raw_class_id.isdigit():
        class_id = int(raw_class_id)

    raw_teacher_id = request.args.get('teacher_id')
    teacher_id = None
    if role == 'teacher':
        teacher_id = user_id
    elif raw_teacher_id and raw_teacher_id.isdigit():
        teacher_id = int(raw_teacher_id)

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
                cursor.execute("SELECT id, subject, teacher_id FROM classes WHERE id = %s", (class_id,))
                selected_class = cursor.fetchone()

            # Teacher name if teacher-scoped
            teacher_name = None
            if teacher_id:
                cursor.execute("SELECT name FROM users WHERE id = %s", (teacher_id,))
                t_row = cursor.fetchone()
                if t_row:
                    teacher_name = t_row['name']

            # 3. Attendance history (isolated by class and/or teacher)
            att_conditions = ["a.student_id = %s"]
            att_params = [student_id]
            if class_id:
                att_conditions.append("a.class_id = %s")
                att_params.append(class_id)
            if teacher_id:
                att_conditions.append("c.teacher_id = %s")
                att_params.append(teacher_id)

            cursor.execute(f"""
                SELECT a.id, a.date, a.status, c.subject as class_name, a.class_id
                FROM attendance a 
                JOIN classes c ON a.class_id = c.id 
                WHERE {' AND '.join(att_conditions)}
                ORDER BY a.date DESC
            """, tuple(att_params))
            attendance_rows = cursor.fetchall()

            for row in attendance_rows:
                if row.get('date'):
                    row['date'] = row['date'].strftime('%Y-%m-%d')

            total_sessions = len(attendance_rows)
            present_sessions = sum(1 for a in attendance_rows if a['status'] == 'present')
            absent_sessions = sum(1 for a in attendance_rows if a['status'] == 'absent')
            att_pct = round((present_sessions / total_sessions * 100), 1) if total_sessions > 0 else 100.0

            # 4. Exam marks history (isolated by class and/or teacher)
            marks_conditions = ["m.student_id = %s"]
            marks_params = [student_id]
            if class_id:
                marks_conditions.append("m.class_id = %s")
                marks_params.append(class_id)
            if teacher_id:
                marks_conditions.append("c.teacher_id = %s")
                marks_params.append(teacher_id)

            cursor.execute(f"""
                SELECT m.id, m.test_name, m.marks_obtained, m.max_marks, m.date_recorded, c.subject as class_name, m.class_id
                FROM marks m 
                JOIN classes c ON m.class_id = c.id 
                WHERE {' AND '.join(marks_conditions)}
                ORDER BY m.date_recorded DESC
            """, tuple(marks_params))
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

            # 5. Fee payments history (isolated by class and/or teacher)
            pmts_conditions = ["p.student_id = %s"]
            pmts_params = [student_id]
            if class_id:
                pmts_conditions.append("p.class_id = %s")
                pmts_params.append(class_id)
            if teacher_id:
                pmts_conditions.append("c.teacher_id = %s")
                pmts_params.append(teacher_id)

            cursor.execute(f"""
                SELECT p.id, p.amount, p.payment_date, p.period, c.subject as class_name, p.class_id
                FROM payments p 
                JOIN classes c ON p.class_id = c.id 
                WHERE {' AND '.join(pmts_conditions)}
                ORDER BY p.payment_date DESC
            """, tuple(pmts_params))
            payments_rows = cursor.fetchall()

            for row in payments_rows:
                if row.get('payment_date'):
                    row['payment_date'] = row['payment_date'].strftime('%Y-%m-%d')
                row['amount'] = float(row.get('amount') or 0)

            total_paid = sum(p['amount'] for p in payments_rows)

            return jsonify({
                'student': student,
                'class': selected_class,
                'teacher_name': teacher_name,
                'is_teacher_scoped': bool(teacher_id),
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

