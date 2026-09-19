from flask import Blueprint, request, jsonify, session, render_template, redirect, url_for, flash
from database.db import get_db_connection
import datetime

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
    # Allow teacher, moderator, admin, superadmin to record payments
    if session.get('role') not in ('teacher', 'moderator', 'admin', 'superadmin'):
        return "Unauthorized", 403

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            if request.method == 'GET':
                if session.get('role') == 'teacher':
                    cursor.execute("SELECT u.id, u.name FROM users u WHERE u.id = %s", (session['user_id'],))
                    teachers = cursor.fetchall()
                    cursor.execute("""
                        SELECT id, subject, teacher_id, fee, %s as teacher_name 
                        FROM classes 
                        WHERE teacher_id = %s 
                        ORDER BY subject
                    """, (session.get('name', 'Teacher'), session['user_id']))
                    classes = cursor.fetchall()
                else:
                    cursor.execute("SELECT id, name FROM users WHERE role = 'teacher' ORDER BY name")
                    teachers = cursor.fetchall()
                    cursor.execute("""
                        SELECT c.id, c.subject, c.teacher_id, c.fee, u.name as teacher_name 
                        FROM classes c 
                        JOIN users u ON c.teacher_id = u.id 
                        ORDER BY u.name, c.subject
                    """)
                    classes = cursor.fetchall()

                cursor.execute("""
                    SELECT e.class_id, u.id as student_id, u.name, u.email 
                    FROM enrollments e 
                    JOIN users u ON e.student_id = u.id 
                    ORDER BY u.name
                """)
                enrollments = cursor.fetchall()

                today = datetime.date.today().isoformat()
                default_period = datetime.datetime.now().strftime('%B %Y')
                selected_teacher_id = request.args.get('teacher_id')
                selected_class_id = request.args.get('class_id')

                return render_template('manual_payment.html', 
                                       teachers=teachers, 
                                       classes=classes, 
                                       enrollments=enrollments,
                                       today=today,
                                       default_period=default_period,
                                       selected_teacher_id=selected_teacher_id,
                                       selected_class_id=selected_class_id)

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
    
    from datetime import date
    if not start_date:
        start_date = date.today().replace(day=1).isoformat()
    if not end_date:
        end_date = date.today().isoformat()
        
    teacher_id = None
    if session['role'] == 'teacher':
        teacher_id = session['user_id']
    elif target_teacher_id:
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
            if teacher_id:
                cursor.execute("""
                    SELECT p.*, c.subject, u.name as student_name, t.name as teacher_name
                    FROM payments p
                    JOIN classes c ON p.class_id = c.id
                    JOIN users u ON p.student_id = u.id
                    JOIN users t ON c.teacher_id = t.id
                    WHERE c.teacher_id = %s AND p.payment_date BETWEEN %s AND %s
                    ORDER BY p.payment_date DESC
                """, (teacher_id, start_date, end_date))
            else:
                cursor.execute("""
                    SELECT p.*, c.subject, u.name as student_name, t.name as teacher_name
                    FROM payments p
                    JOIN classes c ON p.class_id = c.id
                    JOIN users u ON p.student_id = u.id
                    JOIN users t ON c.teacher_id = t.id
                    WHERE p.payment_date BETWEEN %s AND %s
                    ORDER BY p.payment_date DESC
                """, (start_date, end_date))
            payments = cursor.fetchall()
            
            total_income = sum(float(p['amount']) for p in payments)
            
            # Group by class for summary
            if teacher_id:
                cursor.execute("""
                    SELECT c.subject, SUM(p.amount) as total
                    FROM payments p
                    JOIN classes c ON p.class_id = c.id
                    WHERE c.teacher_id = %s AND p.payment_date BETWEEN %s AND %s
                    GROUP BY c.subject
                """, (teacher_id, start_date, end_date))
            else:
                cursor.execute("""
                    SELECT c.subject, SUM(p.amount) as total
                    FROM payments p
                    JOIN classes c ON p.class_id = c.id
                    WHERE p.payment_date BETWEEN %s AND %s
                    GROUP BY c.subject
                """, (start_date, end_date))
            class_summaries = cursor.fetchall()

            # Group by month for monthly-wise report
            if teacher_id:
                cursor.execute("""
                    SELECT DATE_FORMAT(p.payment_date, '%%Y-%%m') as month, SUM(p.amount) as total
                    FROM payments p
                    JOIN classes c ON p.class_id = c.id
                    WHERE c.teacher_id = %s
                    GROUP BY month
                    ORDER BY month DESC
                """, (teacher_id,))
            else:
                cursor.execute("""
                    SELECT DATE_FORMAT(p.payment_date, '%%Y-%%m') as month, SUM(p.amount) as total
                    FROM payments p
                    JOIN classes c ON p.class_id = c.id
                    GROUP BY month
                    ORDER BY month DESC
                """)
            monthly_summaries = cursor.fetchall()

            return render_template('income_report.html', 
                                   payments=payments, 
                                   total_income=total_income,
                                   class_summaries=class_summaries,
                                   monthly_summaries=monthly_summaries,
                                   start_date=start_date,
                                   end_date=end_date,
                                   teachers=teachers,
                                   selected_teacher=int(teacher_id) if teacher_id else None)
    finally:
        conn.close()

@finance_bp.route('/income/report/export', methods=['GET'])
def export_income_report():
    if session.get('role') not in ('teacher', 'moderator', 'superadmin'):
        return "Unauthorized", 403

    export_format = request.args.get('format', 'csv').lower()
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    target_teacher_id = request.args.get('teacher_id')
    
    from datetime import date
    if not start_date:
        start_date = date.today().replace(day=1).isoformat()
    if not end_date:
        end_date = date.today().isoformat()
        
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            teacher_name = "All Teachers"
            if session['role'] == 'teacher':
                teacher_id = session['user_id']
                cursor.execute("SELECT name FROM users WHERE id = %s", (teacher_id,))
                t_row = cursor.fetchone()
                teacher_name = t_row['name'] if t_row else "Teacher"
                cursor.execute("""
                    SELECT p.id, p.payment_date, u.name as student_name, c.subject, t.name as teacher_name, p.period, p.amount
                    FROM payments p
                    JOIN classes c ON p.class_id = c.id
                    JOIN users u ON p.student_id = u.id
                    JOIN users t ON c.teacher_id = t.id
                    WHERE c.teacher_id = %s AND p.payment_date BETWEEN %s AND %s
                    ORDER BY p.payment_date DESC
                """, (teacher_id, start_date, end_date))
            elif target_teacher_id:
                cursor.execute("SELECT name FROM users WHERE id = %s", (target_teacher_id,))
                t_row = cursor.fetchone()
                teacher_name = t_row['name'] if t_row else f"Teacher #{target_teacher_id}"
                cursor.execute("""
                    SELECT p.id, p.payment_date, u.name as student_name, c.subject, t.name as teacher_name, p.period, p.amount
                    FROM payments p
                    JOIN classes c ON p.class_id = c.id
                    JOIN users u ON p.student_id = u.id
                    JOIN users t ON c.teacher_id = t.id
                    WHERE c.teacher_id = %s AND p.payment_date BETWEEN %s AND %s
                    ORDER BY p.payment_date DESC
                """, (target_teacher_id, start_date, end_date))
            else:
                cursor.execute("""
                    SELECT p.id, p.payment_date, u.name as student_name, c.subject, t.name as teacher_name, p.period, p.amount
                    FROM payments p
                    JOIN classes c ON p.class_id = c.id
                    JOIN users u ON p.student_id = u.id
                    JOIN users t ON c.teacher_id = t.id
                    WHERE p.payment_date BETWEEN %s AND %s
                    ORDER BY p.payment_date DESC
                """, (start_date, end_date))

            payments = cursor.fetchall()
            total_income = sum(float(p['amount']) for p in payments)
            filename_base = f"financial_audit_report_{start_date}_to_{end_date}"

            if export_format == 'csv':
                import io, csv
                output = io.StringIO()
                output.write('\ufeff') # UTF-8 BOM
                writer = csv.writer(output)
                writer.writerow(["NS Learnytics — Financial Audit Report"])
                writer.writerow(["Reporting Period", f"{start_date} to {end_date}"])
                writer.writerow(["Teacher Filter", teacher_name])
                writer.writerow(["Total Revenue (LKR)", f"{total_income:,.2f}"])
                writer.writerow(["Total Transactions", len(payments)])
                writer.writerow([])
                writer.writerow(["Payment ID", "Date", "Student Name", "Course / Subject", "Teacher", "Billing Period", "Amount (LKR)"])
                for p in payments:
                    writer.writerow([
                        p['id'],
                        str(p['payment_date']),
                        p['student_name'],
                        p['subject'],
                        p['teacher_name'],
                        p['period'],
                        f"{float(p['amount']):.2f}"
                    ])
                
                output.seek(0)
                from flask import Response
                return Response(
                    output.getvalue(),
                    mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment;filename={filename_base}.csv"}
                )

            elif export_format in ('excel', 'xlsx'):
                import io, openpyxl
                from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
                from flask import send_file

                wb = openpyxl.Workbook()
                ws = wb.active
                ws.title = "Financial Audit"

                header_font = Font(name="Calibri", size=14, bold=True, color="1E293B")
                sub_font = Font(name="Calibri", size=10, italic=True, color="64748B")
                tbl_header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
                tbl_header_fill = PatternFill(start_color="0F766E", end_color="0F766E", fill_type="solid")
                total_fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")
                bold_font = Font(name="Calibri", size=11, bold=True)
                thin_border = Border(
                    left=Side(style='thin', color='CBD5E1'),
                    right=Side(style='thin', color='CBD5E1'),
                    top=Side(style='thin', color='CBD5E1'),
                    bottom=Side(style='thin', color='CBD5E1')
                )

                # Report Banner
                ws.append(["NS Learnytics — Financial Audit Report"])
                ws.cell(row=1, column=1).font = header_font
                ws.append([f"Period: {start_date} to {end_date} | Teacher: {teacher_name}"])
                ws.cell(row=2, column=1).font = sub_font
                ws.append([f"Generated: {date.today().isoformat()} | Total Revenue: LKR {total_income:,.2f}"])
                ws.cell(row=3, column=1).font = sub_font
                ws.append([]) # Blank

                # Table Header
                headers = ["ID", "Payment Date", "Student Name", "Course / Subject", "Teacher", "Billing Period", "Amount (LKR)"]
                ws.append(headers)
                header_row = 5
                for col_idx in range(1, len(headers) + 1):
                    cell = ws.cell(row=header_row, column=col_idx)
                    cell.font = tbl_header_font
                    cell.fill = tbl_header_fill
                    cell.alignment = Alignment(horizontal="center" if col_idx in (1, 2, 6) else ("right" if col_idx == 7 else "left"))
                    cell.border = thin_border

                # Data rows
                for row_idx, p in enumerate(payments, start=header_row + 1):
                    ws.append([
                        p['id'],
                        str(p['payment_date']),
                        p['student_name'],
                        p['subject'],
                        p['teacher_name'],
                        p['period'],
                        float(p['amount'])
                    ])
                    ws.cell(row=row_idx, column=1).alignment = Alignment(horizontal="center")
                    ws.cell(row=row_idx, column=2).alignment = Alignment(horizontal="center")
                    ws.cell(row=row_idx, column=6).alignment = Alignment(horizontal="center")
                    amt_cell = ws.cell(row=row_idx, column=7)
                    amt_cell.number_format = '#,##0.00'
                    amt_cell.alignment = Alignment(horizontal="right")
                    for c_idx in range(1, len(headers) + 1):
                        ws.cell(row=row_idx, column=c_idx).border = thin_border

                # Summary Row
                total_row = header_row + len(payments) + 1
                ws.append(["", "", "", "", "", "TOTAL REVENUE:", total_income])
                for c_idx in range(1, len(headers) + 1):
                    cell = ws.cell(row=total_row, column=c_idx)
                    cell.font = bold_font
                    cell.fill = total_fill
                    cell.border = thin_border
                total_cell = ws.cell(row=total_row, column=7)
                total_cell.number_format = '#,##0.00'
                total_cell.alignment = Alignment(horizontal="right")

                # Column widths
                for col in ws.columns:
                    max_len = max(len(str(cell.value or '')) for cell in col)
                    col_letter = openpyxl.utils.get_column_letter(col[0].column)
                    ws.column_dimensions[col_letter].width = max(max_len + 4, 12)

                buf = io.BytesIO()
                wb.save(buf)
                buf.seek(0)
                return send_file(
                    buf,
                    mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    as_attachment=True,
                    download_name=f"{filename_base}.xlsx"
                )

            elif export_format == 'pdf':
                import io
                from reportlab.lib.pagesizes import letter, landscape
                from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
                from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
                from reportlab.lib import colors
                from flask import send_file

                buf = io.BytesIO()
                doc = SimpleDocTemplate(buf, pagesize=landscape(letter), leftMargin=30, rightMargin=30, topMargin=30, bottomMargin=30)
                styles = getSampleStyleSheet()

                title_style = ParagraphStyle(
                    'TitleStyle',
                    parent=styles['Heading1'],
                    fontSize=16,
                    leading=20,
                    textColor=colors.HexColor('#0f766e')
                )
                meta_style = ParagraphStyle(
                    'MetaStyle',
                    parent=styles['Normal'],
                    fontSize=8.5,
                    leading=12,
                    textColor=colors.HexColor('#64748b')
                )

                elements = [
                    Paragraph("NS Learnytics — Financial Audit & Revenue Report", title_style),
                    Spacer(1, 4),
                    Paragraph(f"Reporting Period: <b>{start_date}</b> to <b>{end_date}</b> &nbsp;|&nbsp; Instructor Filter: <b>{teacher_name}</b> &nbsp;|&nbsp; Generated on: {date.today().isoformat()}", meta_style),
                    Paragraph(f"Total Collections: <b>{len(payments)} Payments</b> &nbsp;|&nbsp; Cumulative Revenue: <b>LKR {total_income:,.2f}</b>", meta_style),
                    Spacer(1, 12)
                ]

                # Table Data
                tbl_data = [["ID", "Payment Date", "Student Name", "Course / Subject", "Teacher", "Period", "Amount (LKR)"]]
                for p in payments:
                    tbl_data.append([
                        str(p['id']),
                        str(p['payment_date']),
                        p['student_name'],
                        p['subject'],
                        p['teacher_name'],
                        str(p['period']),
                        f"{float(p['amount']):,.2f}"
                    ])
                
                tbl_data.append(["", "", "", "", "", "TOTAL:", f"{total_income:,.2f}"])

                t = Table(tbl_data, colWidths=[35, 75, 150, 120, 130, 85, 100])
                t.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0f766e')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 9),
                    ('ALIGN', (0, 0), (-1, 0), 'LEFT'),
                    ('ALIGN', (0, 0), (0, -1), 'CENTER'),
                    ('ALIGN', (1, 0), (1, -1), 'CENTER'),
                    ('ALIGN', (5, 0), (5, -1), 'CENTER'),
                    ('ALIGN', (6, 0), (6, -1), 'RIGHT'),
                    ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                    ('FONTSIZE', (0, 1), (-1, -1), 8.5),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.HexColor('#ffffff'), colors.HexColor('#f8fafc')]),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
                    ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
                    ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#f1f5f9')),
                    ('TEXTCOLOR', (0, -1), (-1, -1), colors.HexColor('#0f766e')),
                ]))
                elements.append(t)
                doc.build(elements)
                buf.seek(0)

                return send_file(
                    buf,
                    mimetype="application/pdf",
                    as_attachment=True,
                    download_name=f"{filename_base}.pdf"
                )
            else:
                return "Invalid export format", 400
    finally:
        conn.close()
