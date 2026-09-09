from flask import Blueprint, request, jsonify, session, render_template, redirect, url_for
from database.db import get_db_connection
from services.ai_risk_predictor import risk_predictor
from services.ai_grade_forecaster import grade_forecaster
import datetime

analytics_bp = Blueprint('analytics', __name__)

@analytics_bp.route('/teacher_dashboard')
def teacher_dashboard():
    if session.get('role') != 'teacher':
        return redirect(url_for('auth.login'))
        
    user_id = session['user_id']
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Total Classes
            cursor.execute("SELECT COUNT(*) as cnt FROM classes WHERE teacher_id = %s", (user_id,))
            total_classes = cursor.fetchone()['cnt']
            
            # Total Students
            cursor.execute("""
                SELECT COUNT(DISTINCT e.student_id) as cnt 
                FROM enrollments e 
                JOIN classes c ON e.class_id = c.id 
                WHERE c.teacher_id = %s
            """, (user_id,))
            total_students = cursor.fetchone()['cnt']
            
            # Monthly Income (current month based on payment_date)
            current_month_str = datetime.datetime.now().strftime('%Y-%m')
            cursor.execute("""
                SELECT SUM(amount) as total 
                FROM payments p
                JOIN classes c ON p.class_id = c.id
                WHERE c.teacher_id = %s AND DATE_FORMAT(p.payment_date, '%%Y-%%m') = %s
            """, (user_id, current_month_str))
            row = cursor.fetchone()
            monthly_income = float(row['total'] or 0.0)
            
            cursor.execute("""
                SELECT SUM(amount) as total FROM expenses WHERE teacher_id = %s AND DATE_FORMAT(expense_date, '%%Y-%%m') = %s
            """, (user_id, current_month_str))
            exp_row = cursor.fetchone()
            monthly_expenses = float(exp_row['total'] or 0.0)
            net_income = monthly_income - monthly_expenses

            # Active Teacher Classes with Enrollment counts
            cursor.execute("""
                SELECT c.id, c.subject, c.schedule, c.fee, c.join_code, COUNT(e.student_id) as student_count
                FROM classes c
                LEFT JOIN enrollments e ON c.id = e.class_id
                WHERE c.teacher_id = %s
                GROUP BY c.id, c.subject, c.schedule, c.fee, c.join_code
                ORDER BY c.subject
            """, (user_id,))
            classes_list = cursor.fetchall()

            # Pending Grading Count in LMS
            cursor.execute("""
                SELECT COUNT(*) as cnt
                FROM assignment_submissions sub
                JOIN assignments a ON sub.assignment_id = a.id
                WHERE a.teacher_id = %s AND sub.status = 'submitted'
            """, (user_id,))
            pending_grading_cnt = cursor.fetchone()['cnt']

            # Recent Announcements posted by this teacher
            cursor.execute("""
                SELECT a.title, a.content, a.created_at, c.subject
                FROM announcements a
                JOIN classes c ON a.class_id = c.id
                WHERE a.teacher_id = %s
                ORDER BY a.created_at DESC LIMIT 3
            """, (user_id,))
            recent_announcements = cursor.fetchall()
            
            # Attendance Analysis & Segmentation
            cursor.execute("""
                SELECT e.student_id, u.name, 
                       SUM(CASE WHEN a.status = 'present' THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(a.id), 0) as attendance_pct
                FROM enrollments e
                JOIN classes c ON e.class_id = c.id
                JOIN users u ON e.student_id = u.id
                LEFT JOIN attendance a ON e.class_id = a.class_id AND e.student_id = a.student_id
                WHERE c.teacher_id = %s
                GROUP BY e.student_id, u.name
            """, (user_id,))
            student_stats = cursor.fetchall()
            
            at_risk_students = []
            segmentation = {'high': 0, 'avg': 0, 'risk': 0}
            
            for s in student_stats:
                pct = s['attendance_pct']
                if pct is None: continue
                pct = float(pct)
                if pct >= 75: segmentation['high'] += 1
                elif pct >= 50: segmentation['avg'] += 1
                else: 
                    segmentation['risk'] += 1
                    if pct < 60:
                        at_risk_students.append({'name': s['name'], 'reason': f'Low attendance ({pct:.1f}%)'})
            
            # Performance Trends
            cursor.execute("""
                SELECT m.test_name, AVG(m.marks_obtained/m.max_marks * 100) as avg_score
                FROM marks m
                JOIN classes c ON m.class_id = c.id
                WHERE c.teacher_id = %s
                GROUP BY m.test_name
                ORDER BY MIN(m.date_recorded) ASC
            """, (user_id,))
            perf_trends = cursor.fetchall()
            perf_labels = [p['test_name'] for p in perf_trends]
            perf_data = [float(p['avg_score']) for p in perf_trends]
            
            # Business Analytics (Revenue per class)
            cursor.execute("""
                SELECT c.subject, SUM(p.amount) as revenue
                FROM classes c
                LEFT JOIN payments p ON c.id = p.class_id
                WHERE c.teacher_id = %s
                GROUP BY c.id, c.subject
            """, (user_id,))
            class_rev = cursor.fetchall()
            rev_labels = [r['subject'] for r in class_rev]
            rev_data = [float(r['revenue'] or 0) for r in class_rev]
            
            # Fetch AI Risk Predictor Top 5 At-Risk Students
            top_5_at_risk = risk_predictor.get_all_student_risks(teacher_id=user_id)[:5]

            # Insights Engine
            insights = []
            if top_5_at_risk:
                high_risk_cnt = sum(1 for s in top_5_at_risk if s['risk_level'] == 'HIGH')
                if high_risk_cnt > 0:
                    insights.append(f"AI Warning: {high_risk_cnt} student(s) in your classes are flagged at HIGH risk of academic dropout.")
            if segmentation['risk'] > segmentation['high']:
                insights.append("Warning: You have more at-risk students than high performers. Review low-attendance follow-ups.")
            best_class = max(class_rev, key=lambda x: float(x['revenue'] or 0)) if class_rev else None
            if best_class and best_class['revenue']:
                insights.append(f"Class '{best_class['subject']}' generates the highest revenue.")
            if perf_data and len(perf_data) >= 2:
                if perf_data[-1] < perf_data[-2]:
                    insights.append("Notice: Average class performance has dipped slightly compared to the previous test.")
            
            return render_template('teacher_dashboard.html', 
                                   total_classes=total_classes,
                                   total_students=total_students,
                                   monthly_income=monthly_income,
                                   net_income=net_income,
                                   classes_list=classes_list,
                                   pending_grading_cnt=pending_grading_cnt,
                                   recent_announcements=recent_announcements,
                                   at_risk_students=at_risk_students,
                                   top_5_at_risk=top_5_at_risk,
                                   segmentation=segmentation,
                                   perf_labels=perf_labels,
                                   perf_data=perf_data,
                                   rev_labels=rev_labels,
                                   rev_data=rev_data,
                                   insights=insights)
    finally:
        conn.close()

@analytics_bp.route('/student_dashboard')
def student_dashboard():
    if session.get('role') != 'student':
        return redirect(url_for('auth.login'))
        
    user_id = session['user_id']
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Overall Attendance
            cursor.execute("""
                SELECT SUM(CASE WHEN status = 'present' THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(*), 0) as pct
                FROM attendance WHERE student_id = %s
            """, (user_id,))
            att_row = cursor.fetchone()
            attendance_pct = float(att_row['pct']) if att_row and att_row['pct'] is not None else 100.0
            
            # Enrolled Classes Count
            cursor.execute("SELECT COUNT(*) as cnt FROM enrollments WHERE student_id = %s", (user_id,))
            class_row = cursor.fetchone()
            total_classes = class_row['cnt'] if class_row else 0

            # Payments Made Count
            cursor.execute("SELECT COUNT(*) as cnt FROM payments WHERE student_id = %s", (user_id,))
            pay_row = cursor.fetchone()
            total_payments = pay_row['cnt'] if pay_row else 0

            # Upcoming Assignments & Homework
            cursor.execute("""
                SELECT a.id, a.title, a.due_date, a.max_points, a.description, c.subject,
                       sub.status as submission_status, sub.marks_obtained
                FROM enrollments e
                JOIN assignments a ON e.class_id = a.class_id
                JOIN classes c ON a.class_id = c.id
                LEFT JOIN assignment_submissions sub ON a.id = sub.assignment_id AND sub.student_id = %s
                WHERE e.student_id = %s
                ORDER BY a.due_date ASC LIMIT 5
            """, (user_id, user_id))
            upcoming_assignments = cursor.fetchall()

            # Recent Marks with Test Name
            cursor.execute("""
                SELECT m.test_name, m.marks_obtained, m.max_marks, m.date_recorded, c.subject
                FROM marks m
                JOIN classes c ON m.class_id = c.id
                WHERE m.student_id = %s
                ORDER BY m.date_recorded DESC LIMIT 5
            """, (user_id,))
            recent_marks = cursor.fetchall()

            # Enrolled Classes list
            cursor.execute("""
                SELECT c.id, c.subject, c.schedule, c.fee, u.name as teacher_name
                FROM enrollments e
                JOIN classes c ON e.class_id = c.id
                JOIN users u ON c.teacher_id = u.id
                WHERE e.student_id = %s
                ORDER BY c.subject
            """, (user_id,))
            enrolled_classes = cursor.fetchall()

            # AI Grade Forecast for student
            student_forecast = grade_forecaster.forecast_student_performance(user_id)

            # Performance Chart Data
            cursor.execute("""
                SELECT test_name, (marks_obtained/max_marks * 100) as score
                FROM marks
                WHERE student_id = %s
                ORDER BY date_recorded ASC
            """, (user_id,))
            marks = cursor.fetchall()
            perf_labels = [m['test_name'] for m in marks]
            perf_data = [float(m['score']) for m in marks]
            
            # Insights
            insights = []
            if attendance_pct < 75:
                insights.append("Your attendance is below 75%. Try to attend more classes to keep up with coursework.")
            if perf_data:
                avg_score = sum(perf_data) / len(perf_data)
                if avg_score >= 75:
                    insights.append("Great job! You are in the upper academic percentile.")
                elif avg_score < 50:
                    insights.append("You might need extra revision. Reach out to your teacher via Messages.")
            
            # Profile & QR Code
            cursor.execute("SELECT qr_code FROM student_profiles WHERE user_id = %s", (user_id,))
            profile = cursor.fetchone()
            qr_code = profile['qr_code'] if profile else None
            
            return render_template('student_dashboard.html',
                                   attendance_pct=attendance_pct,
                                   total_classes=total_classes,
                                   total_payments=total_payments,
                                   upcoming_assignments=upcoming_assignments,
                                   recent_marks=recent_marks,
                                   enrolled_classes=enrolled_classes,
                                   student_forecast=student_forecast,
                                   perf_labels=perf_labels,
                                   perf_data=perf_data,
                                   insights=insights,
                                   qr_code=qr_code)
    finally:
        conn.close()

@analytics_bp.route('/moderator_dashboard')
def moderator_dashboard():
    if session.get('role') != 'moderator':
        return redirect(url_for('auth.login'))
        
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, name FROM users WHERE role = 'teacher' ORDER BY name")
            teachers = cursor.fetchall()
            cursor.execute("SELECT id, subject, teacher_id FROM classes ORDER BY subject")
            classes = cursor.fetchall()

            # Today's Check-in Count
            cursor.execute("SELECT COUNT(*) as cnt FROM attendance WHERE date = CURDATE() AND status = 'present'")
            today_attendance = cursor.fetchone()['cnt']

            # Today's Total Fees Collected
            cursor.execute("SELECT SUM(amount) as total FROM payments WHERE payment_date = CURDATE()")
            today_fees = float(cursor.fetchone()['total'] or 0.0)

            # Live Stream of Recent Payments
            cursor.execute("""
                SELECT p.id, p.amount, p.payment_date, p.period, u.name as student_name, c.subject
                FROM payments p
                JOIN users u ON p.student_id = u.id
                JOIN classes c ON p.class_id = c.id
                ORDER BY p.id DESC LIMIT 6
            """)
            recent_payments = cursor.fetchall()

            return render_template('moderator_dashboard.html', 
                                   teachers=teachers, 
                                   classes=classes,
                                   today_attendance=today_attendance,
                                   today_fees=today_fees,
                                   recent_payments=recent_payments)
    finally:
        conn.close()
