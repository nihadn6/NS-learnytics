from flask import Blueprint, request, jsonify, session, render_template, redirect, url_for, flash
from database.db import get_db_connection

finance_bp = Blueprint('finance', __name__)

@finance_bp.route('/payments/record', methods=['POST'])
def record_payment():
    # This endpoint is left for direct teacher submissions; prefer using /payments/manual for broader roles
    if session.get('role') != 'teacher':
        return "Unauthorized", 403

    data = request.form
    class_id = data.get('class_id')
    student_id = data.get('student_id')
    payment_date = data.get('payment_date')
    period = data.get('period')
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT fee FROM classes WHERE id = %s", (class_id,))
            class_row = cursor.fetchone()
            amount = class_row['fee'] if class_row else 0.0
            
            cursor.execute("""
                INSERT INTO payments (class_id, student_id, amount, payment_date, period) 
                VALUES (%s, %s, %s, %s, %s)
            """, (class_id, student_id, amount, payment_date, period))
            conn.commit()
        # Assume redirected back to class students view
        # After a teacher records a payment, redirect back to the manual payment page
        # to allow adding another payment quickly (prefill the class)
        return redirect(url_for('finance.manual_payment'))
    finally:
        conn.close()


@finance_bp.route('/payments/manual', methods=['GET', 'POST'])
def manual_payment():
    # Allow teacher, moderator, superadmin to record payments
    if session.get('role') not in ('teacher', 'moderator', 'superadmin'):
        return "Unauthorized", 403

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            if request.method == 'GET':
                if session.get('role') == 'teacher':
                    cursor.execute("SELECT u.id, u.name FROM users u WHERE u.id = %s", (session['user_id'],))
                    teachers = cursor.fetchall()
                    cursor.execute("SELECT id, subject, teacher_id FROM classes WHERE teacher_id = %s", (session['user_id'],))
                    classes = cursor.fetchall()
                else:
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
                return render_template('manual_payment.html', teachers=teachers, classes=classes, enrollments=enrollments)

            data = request.form
            class_id = data.get('class_id')
            student_id = data.get('student_id')
            payment_date = data.get('payment_date')
            period = data.get('period')

            # permissions: teacher must own class
            if session.get('role') == 'teacher':
                cursor.execute("SELECT 1 FROM classes WHERE id = %s AND teacher_id = %s", (class_id, session['user_id']))
                if not cursor.fetchone():
                    return "Invalid class or unauthorized", 400

            cursor.execute("SELECT fee FROM classes WHERE id = %s", (class_id,))
            class_row = cursor.fetchone()
            amount = class_row['fee'] if class_row else 0.0

            cursor.execute("INSERT INTO payments (class_id, student_id, amount, payment_date, period) VALUES (%s,%s,%s,%s,%s)",
                           (class_id, student_id, amount, payment_date, period))
            conn.commit()
            flash('Payment recorded successfully!', 'success')
            # Redirect back to the form to easily record another payment
            return redirect(url_for('finance.manual_payment'))
    except Exception as e:
        flash(f'Error recording payment: {str(e)}', 'error')
        return redirect(url_for('finance.manual_payment'))
    finally:
        conn.close()

@finance_bp.route('/expenses/add', methods=['POST'])
def add_expense():
    if session.get('role') != 'teacher':
        return "Unauthorized", 403
        
    data = request.form
    description = data.get('description')
    amount = data.get('amount')
    expense_date = data.get('expense_date')
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO expenses (teacher_id, description, amount, expense_date) 
                VALUES (%s, %s, %s, %s)
            """, (session['user_id'], description, amount, expense_date))
            conn.commit()
        return redirect(url_for('analytics.teacher_dashboard'))
    finally:
        conn.close()

@finance_bp.route('/payments/student', methods=['GET'])
def student_payments():
    if session.get('role') != 'student':
        return "Unauthorized", 403
        
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT c.subject, p.amount, p.payment_date, p.period
                FROM payments p
                JOIN classes c ON p.class_id = c.id
                WHERE p.student_id = %s
                ORDER BY p.payment_date DESC
            """, (session['user_id'],))
            payments = cursor.fetchall()
            return render_template('payments_student.html', payments=payments)
    finally:
        conn.close()
@finance_bp.route('/income/report', methods=['GET'])
def income_report():
    if session.get('role') not in ('teacher', 'moderator', 'superadmin'):
        return "Unauthorized", 403
        
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    target_teacher_id = request.args.get('teacher_id')
    
    # Default to current month if not provided
    from datetime import datetime, date
    if not start_date:
        start_date = date.today().replace(day=1).isoformat()
    if not end_date:
        end_date = date.today().isoformat()
        
    teacher_id = session['user_id']
    if session['role'] in ('moderator', 'superadmin') and target_teacher_id:
        teacher_id = target_teacher_id

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Dropdowns for admin/moderator
            teachers = []
            if session['role'] in ('moderator', 'superadmin'):
                cursor.execute("SELECT id, name FROM users WHERE role = 'teacher' ORDER BY name")
                teachers = cursor.fetchall()

            # Query Income (Tutoring Fees)
            cursor.execute("""
                SELECT p.*, c.subject, u.name as student_name
                FROM payments p
                JOIN classes c ON p.class_id = c.id
                JOIN users u ON p.student_id = u.id
                WHERE c.teacher_id = %s AND p.payment_date BETWEEN %s AND %s
                ORDER BY p.payment_date DESC
            """, (teacher_id, start_date, end_date))
            payments = cursor.fetchall()
            
            total_income = sum(p['amount'] for p in payments)
            
            # Group by class for summary
            cursor.execute("""
                SELECT c.subject, SUM(p.amount) as total
                FROM payments p
                JOIN classes c ON p.class_id = c.id
                WHERE c.teacher_id = %s AND p.payment_date BETWEEN %s AND %s
                GROUP BY c.subject
            """, (teacher_id, start_date, end_date))
            class_summaries = cursor.fetchall()

            return render_template('income_report.html', 
                                   payments=payments, 
                                   total_income=total_income,
                                   class_summaries=class_summaries,
                                   start_date=start_date,
                                   end_date=end_date,
                                   teachers=teachers,
                                   selected_teacher=int(teacher_id) if teacher_id else None)
    finally:
        conn.close()
