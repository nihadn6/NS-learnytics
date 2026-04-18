from flask import Blueprint, request, jsonify, session, render_template, redirect, url_for
from database.db import get_db_connection
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
            # Use %% to escape for DATE_FORMAT
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
            
            # Insights Engine
            insights = []
            if segmentation['risk'] > segmentation['high']:
                insights.append("Warning: You have more at-risk students than high performers. Consider revising teaching strategies.")
            best_class = max(class_rev, key=lambda x: float(x['revenue'] or 0)) if class_rev else None
            if best_class and best_class['revenue']:
                insights.append(f"Class '{best_class['subject']}' generates the highest revenue.")
            if perf_data and len(perf_data) >= 2:
                if perf_data[-1] < perf_data[-2]:
                    insights.append("Notice: Average class performance has declined compared to the previous test.")
            
            return render_template('teacher_dashboard.html', 
                                   total_classes=total_classes,
                                   total_students=total_students,
                                   monthly_income=monthly_income,
                                   net_income=net_income,
                                   at_risk_students=at_risk_students,
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
                insights.append("Your attendance is below 75%. Try to attend more classes to improve your grades.")
            if perf_data:
                avg_score = sum(perf_data) / len(perf_data)
                if avg_score >= 75:
                    insights.append("Great job! You are performing very well overall.")
                elif avg_score < 50:
                    insights.append("You might need extra help. Consider talking to your teacher.")
            
            # Profile & QR Code
            cursor.execute("SELECT qr_code FROM student_profiles WHERE user_id = %s", (user_id,))
            profile = cursor.fetchone()
            qr_code = profile['qr_code'] if profile else None
            
            return render_template('student_dashboard.html',
                                   attendance_pct=attendance_pct,
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
            return render_template('moderator_dashboard.html', teachers=teachers, classes=classes)
    finally:
        conn.close()
