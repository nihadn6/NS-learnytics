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

    class_id = request.args.get('class_id')
    teacher_filter = user_id if role == 'teacher' else None

    # Fetch classes for filter dropdown
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            if role == 'teacher':
                cursor.execute("SELECT id, subject FROM classes WHERE teacher_id = %s ORDER BY subject", (user_id,))
            else:
                cursor.execute("SELECT id, subject FROM classes ORDER BY subject")
            classes = cursor.fetchall()
    finally:
        conn.close()

    # Predict risks for students
    student_risks = risk_predictor.get_all_student_risks(teacher_id=teacher_filter, class_id=class_id)

    # Compute summary counters
    high_count = sum(1 for s in student_risks if s['risk_level'] == 'HIGH')
    medium_count = sum(1 for s in student_risks if s['risk_level'] == 'MEDIUM')
    low_count = sum(1 for s in student_risks if s['risk_level'] == 'LOW')
    total_students = len(student_risks)

    avg_risk_score = round(sum(s['risk_pct'] for s in student_risks) / total_students, 1) if total_students > 0 else 0.0

    return render_template('at_risk_students.html',
                           student_risks=student_risks,
                           classes=classes,
                           selected_class_id=class_id,
                           high_count=high_count,
                           medium_count=medium_count,
                           low_count=low_count,
                           total_students=total_students,
                           avg_risk_score=avg_risk_score)

@ai_analytics_bp.route('/ai/grade-forecasting', methods=['GET'])
def grade_forecasting_dashboard():
    role = session.get('role')
    user_id = session.get('user_id')

    if role not in ('superadmin', 'admin', 'teacher', 'student', 'parent'):
        return redirect(url_for('auth.login'))

    class_id = request.args.get('class_id')
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            if role == 'teacher':
                cursor.execute("SELECT id, subject FROM classes WHERE teacher_id = %s ORDER BY subject", (user_id,))
                classes = cursor.fetchall()
                forecast_data = grade_forecaster.forecast_all_students(teacher_id=user_id, class_id=class_id)
            elif role in ('superadmin', 'admin'):
                cursor.execute("SELECT id, subject FROM classes ORDER BY subject")
                classes = cursor.fetchall()
                forecast_data = grade_forecaster.forecast_all_students(class_id=class_id)
            elif role == 'student':
                classes = []
                f_single = grade_forecaster.forecast_student_performance(user_id, class_id=class_id)
                forecast_data = [f_single] if f_single else []
            elif role == 'parent':
                classes = []
                target_student_id = session.get('selected_student_id')
                if not target_student_id:
                    cursor.execute("SELECT student_id FROM parent_student_links WHERE parent_id = %s AND status = 'approved' LIMIT 1", (user_id,))
                    row = cursor.fetchone()
                    target_student_id = row['student_id'] if row else None

                f_single = grade_forecaster.forecast_student_performance(target_student_id, class_id=class_id) if target_student_id else None
                forecast_data = [f_single] if f_single else []
    finally:
        conn.close()

    return render_template('grade_forecasting.html',
                           forecast_data=forecast_data,
                           classes=classes,
                           selected_class_id=class_id,
                           role=role)

@ai_analytics_bp.route('/api/ai/predict-student/<int:student_id>', methods=['GET'])
def predict_single_student(student_id):
    if session.get('role') not in ('superadmin', 'admin', 'teacher', 'moderator'):
        return jsonify({'error': 'Unauthorized'}), 403

    analysis = risk_predictor.predict_student_risk(student_id)
    if not analysis:
        return jsonify({'error': 'Student not found'}), 404

    return jsonify(analysis)

