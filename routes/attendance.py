from flask import Blueprint, request, jsonify, session, render_template, redirect, url_for
import datetime
from database.db import get_db_connection

attendance_bp = Blueprint('attendance', __name__)

@attendance_bp.route('/attendance/mark', methods=['GET', 'POST'])
def mark_attendance():
    role = session.get('role')
    if role not in ('teacher', 'moderator', 'superadmin'):
        return "Unauthorized", 403
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            if request.method == 'GET':
                class_id = request.args.get('class_id')
                date = request.args.get('date')
                
                if role == 'teacher':
                    cursor.execute("SELECT id, subject FROM classes WHERE id = %s AND teacher_id = %s", (class_id, session['user_id']))
                else:
                    cursor.execute("SELECT id, subject FROM classes WHERE id = %s", (class_id,))
                    
                if not cursor.fetchone():
                    return "Invalid class", 400
                    
                cursor.execute("""
                    SELECT u.id, u.name 
                    FROM enrollments e
                    JOIN users u ON e.student_id = u.id
                    WHERE e.class_id = %s
                """, (class_id,))
                students = cursor.fetchall()
                if not students:
                    return render_template('mark_attendance.html', error="No students enrolled", class_id=class_id, date=date, students=[])
                return render_template('mark_attendance.html', students=students, class_id=class_id, date=date)
                
            data = request.form
            class_id = data.get('class_id')
            date = data.get('date')
            
            for key, value in data.items():
                if key.startswith('status_'):
                    student_id = key.split('_')[1]
                    cursor.execute("""
                        INSERT INTO attendance (class_id, student_id, date, status) 
                        VALUES (%s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE status = VALUES(status)
                    """, (class_id, student_id, date, value))
            conn.commit()
            return redirect(url_for('classes.view_classes'))
    finally:
        conn.close()

@attendance_bp.route('/attendance/history', methods=['GET'])
def view_attendance_history():
    if session.get('role') != 'student':
        return "Student view only", 403
        
    user_id = session['user_id']
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            query_records = """
                SELECT c.subject, a.date, a.status 
                FROM attendance a
                JOIN classes c ON a.class_id = c.id
                WHERE a.student_id = %s
            """
            params = [user_id]
            
            if start_date and end_date:
                query_records += " AND a.date >= %s AND a.date <= %s"
                params.extend([start_date, end_date])
            
            query_records += " ORDER BY a.date DESC"
            cursor.execute(query_records, tuple(params))
            records = cursor.fetchall()
            
            query_pct = """
                SELECT c.subject, 
                       SUM(CASE WHEN a.status = 'present' THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(*), 0) as percentage
                FROM attendance a
                JOIN classes c ON a.class_id = c.id
                WHERE a.student_id = %s
            """
            pct_params = [user_id]
            if start_date and end_date:
                query_pct += " AND a.date >= %s AND a.date <= %s"
                pct_params.extend([start_date, end_date])
            
            query_pct += " GROUP BY c.id"
            cursor.execute(query_pct, tuple(pct_params))
            percentages = cursor.fetchall()
            
            return render_template('attendance_student.html', 
                                 records=records, 
                                 percentages=percentages, 
                                 start_date=start_date, 
                                 end_date=end_date)
    finally:
        conn.close()


@attendance_bp.route('/attendance/scan', methods=['GET', 'POST'])
def scan_attendance():
    # Teachers, Moderators (clerks), and Super Admins can scan student QR codes or manually mark attendance
    role = session.get('role')
    user_id = session.get('user_id')

    if role not in ('teacher', 'moderator', 'admin', 'superadmin'):
        return "Unauthorized", 403

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            if request.method == 'GET':
                if role == 'teacher':
                    cursor.execute("SELECT id, name FROM users WHERE id = %s", (user_id,))
                    teachers = cursor.fetchall()
                    cursor.execute("SELECT id, subject, teacher_id FROM classes WHERE teacher_id = %s ORDER BY subject", (user_id,))
                    classes = cursor.fetchall()
                    cursor.execute("""
                        SELECT e.class_id, u.id as student_id, u.name 
                        FROM enrollments e 
                        JOIN users u ON e.student_id = u.id 
                        JOIN classes c ON e.class_id = c.id
                        WHERE c.teacher_id = %s
                        ORDER BY u.name
                    """, (user_id,))
                    enrollments = cursor.fetchall()
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
                return render_template('scan_attendance.html', teachers=teachers, classes=classes, enrollments=enrollments)

            # POST: accept JSON payload with token/student_id and class_id (and optional date)
            data = request.get_json() or {}
            token = data.get('token')
            student_id = data.get('student_id')
            class_id = data.get('class_id')
            date = data.get('date')  # optional YYYY-MM-DD

            if not class_id:
                return jsonify({'error': 'class_id required'}), 400

            if token:
                # Find student by token
                cursor.execute("SELECT u.id as student_id FROM student_profiles sp JOIN users u ON sp.user_id = u.id WHERE sp.qr_code = %s", (token,))
                row = cursor.fetchone()
                if not row:
                    return jsonify({'error': 'Invalid token'}), 400
                student_id = row['student_id']
            elif not student_id:
                return jsonify({'error': 'token or student_id required'}), 400

            # Verify enrollment
            cursor.execute("SELECT 1 FROM enrollments WHERE class_id = %s AND student_id = %s", (class_id, student_id))
            if not cursor.fetchone():
                return jsonify({'error': 'Student not enrolled in this class'}), 400

            # Use provided date or today
            if not date:
                date = datetime.date.today().isoformat()

            # Insert or update attendance - mark as present
            cursor.execute("""
                INSERT INTO attendance (class_id, student_id, date, status)
                VALUES (%s, %s, %s, 'present')
                ON DUPLICATE KEY UPDATE status = VALUES(status)
            """, (class_id, student_id, date))
            conn.commit()

            # Return success and student info
            cursor.execute("SELECT name FROM users WHERE id = %s", (student_id,))
            student = cursor.fetchone()
            return jsonify({'success': True, 'student': student, 'date': date})
    finally:
        conn.close()


@attendance_bp.route('/attendance/manual', methods=['GET', 'POST'])
def manual_mark():
    # Allow teachers, moderators, and superadmins to mark attendance manually
    if session.get('role') not in ('teacher', 'moderator', 'superadmin'):
        return "Unauthorized", 403

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            if request.method == 'GET':
                # For teachers: show only their classes. For others: show all classes.
                if session.get('role') == 'teacher':
                    cursor.execute("SELECT id, subject FROM classes WHERE teacher_id = %s", (session['user_id'],))
                else:
                    cursor.execute("SELECT id, subject FROM classes ORDER BY subject")
                classes = cursor.fetchall()

                class_id = request.args.get('class_id')
                date = request.args.get('date') or ''
                students = []
                if class_id:
                    cursor.execute("SELECT u.id, u.name FROM enrollments e JOIN users u ON e.student_id = u.id WHERE e.class_id = %s", (class_id,))
                    students = cursor.fetchall()
                return render_template('mark_attendance.html', students=students, class_id=class_id, date=date, action_url=url_for('attendance.manual_mark'))

            # POST: accept manual attendance entries
            data = request.form
            class_id = data.get('class_id')
            date = data.get('date')

            # permission: if teacher, must own the class_id
            if session.get('role') == 'teacher':
                cursor.execute("SELECT 1 FROM classes WHERE id = %s AND teacher_id = %s", (class_id, session['user_id']))
                if not cursor.fetchone():
                    return "Invalid class or unauthorized", 400

            for key, value in data.items():
                if key.startswith('status_'):
                    student_id = key.split('_')[1]
                    cursor.execute("""
                        INSERT INTO attendance (class_id, student_id, date, status) 
                        VALUES (%s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE status = VALUES(status)
                    """, (class_id, student_id, date, value))
            conn.commit()
            # Redirect back to classes or admin dashboard based on role
            if session.get('role') == 'teacher':
                return redirect(url_for('classes.view_classes'))
            return redirect(url_for('admin.dashboard'))
    finally:
        conn.close()


@attendance_bp.route('/attendance/report', methods=['GET'])
def attendance_report():
    role = session.get('role')
    if role not in ('teacher', 'moderator', 'admin', 'superadmin'):
        return "Unauthorized", 403

    user_id = session['user_id']
    class_id = request.args.get('class_id')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    student_search = request.args.get('student_search', '').strip()

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            teachers = []
            if role in ('moderator', 'admin', 'superadmin'):
                cursor.execute("SELECT id, name FROM users WHERE role = 'teacher' ORDER BY name")
                teachers = cursor.fetchall()
                cursor.execute("SELECT id, subject, teacher_id FROM classes ORDER BY subject")
                classes = cursor.fetchall()
            else:
                cursor.execute("SELECT id, subject FROM classes WHERE teacher_id = %s ORDER BY subject", (user_id,))
                classes = cursor.fetchall()

            records = []
            aggregated = []
            
            if class_id and start_date and end_date:
                authorized = False
                if role == 'teacher':
                    cursor.execute("SELECT 1 FROM classes WHERE id = %s AND teacher_id = %s", (class_id, user_id))
                    if cursor.fetchone():
                        authorized = True
                else:
                    authorized = True
                
                if authorized:
                    search_clause = ""
                    params_records = [class_id, start_date, end_date]
                    params_aggregated = [class_id, start_date, end_date]

                    if student_search:
                        search_clause = " AND (u.name LIKE %s OR u.email LIKE %s)"
                        search_param = f"%{student_search}%"
                        params_records.extend([search_param, search_param])
                        params_aggregated.extend([search_param, search_param])

                    cursor.execute(f"""
                        SELECT u.name, u.email, a.date, a.status
                        FROM attendance a
                        JOIN users u ON a.student_id = u.id
                        WHERE a.class_id = %s AND a.date >= %s AND a.date <= %s{search_clause}
                        ORDER BY a.date DESC, u.name ASC
                    """, tuple(params_records))
                    records = cursor.fetchall()
                    
                    cursor.execute(f"""
                        SELECT u.name, u.email,
                               SUM(CASE WHEN a.status = 'present' THEN 1 ELSE 0 END) as present_days,
                               COUNT(a.id) as total_days,
                               (SUM(CASE WHEN a.status = 'present' THEN 1 ELSE 0 END) * 100.0 / COUNT(a.id)) as attendance_percentage
                        FROM attendance a
                        JOIN users u ON a.student_id = u.id
                        WHERE a.class_id = %s AND a.date >= %s AND a.date <= %s{search_clause}
                        GROUP BY a.student_id, u.name, u.email
                        ORDER BY attendance_percentage DESC
                    """, tuple(params_aggregated))
                    aggregated = cursor.fetchall()
                    
            return render_template(
                'attendance_report.html', 
                teachers=teachers, 
                classes=classes, 
                class_id=class_id, 
                start_date=start_date, 
                end_date=end_date, 
                student_search=student_search,
                records=records, 
                aggregated=aggregated
            )
    finally:
        conn.close()


@attendance_bp.route('/attendance/report/export', methods=['GET'])
def export_attendance_report():
    role = session.get('role')
    if role not in ('teacher', 'moderator', 'admin', 'superadmin'):
        return "Unauthorized", 403

    user_id = session['user_id']
    class_id = request.args.get('class_id')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    student_search = request.args.get('student_search', '').strip()
    export_format = request.args.get('format', 'pdf').lower()

    if not class_id or not start_date or not end_date:
        return "Missing required parameters (class_id, start_date, end_date)", 400

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Check permissions
            if role == 'teacher':
                cursor.execute("SELECT 1 FROM classes WHERE id = %s AND teacher_id = %s", (class_id, user_id))
                if not cursor.fetchone():
                    return "Unauthorized for this class", 401

            # Fetch class and teacher info
            cursor.execute("""
                SELECT c.id, c.subject, c.teacher_id, u.name as teacher_name
                FROM classes c
                JOIN users u ON c.teacher_id = u.id
                WHERE c.id = %s
            """, (class_id,))
            class_info = cursor.fetchone()
            if not class_info:
                return "Class not found", 404

            search_clause = ""
            params_records = [class_id, start_date, end_date]
            params_aggregated = [class_id, start_date, end_date]

            if student_search:
                search_clause = " AND (u.name LIKE %s OR u.email LIKE %s)"
                search_param = f"%{student_search}%"
                params_records.extend([search_param, search_param])
                params_aggregated.extend([search_param, search_param])

            cursor.execute(f"""
                SELECT u.name, u.email, a.date, a.status
                FROM attendance a
                JOIN users u ON a.student_id = u.id
                WHERE a.class_id = %s AND a.date >= %s AND a.date <= %s{search_clause}
                ORDER BY a.date DESC, u.name ASC
            """, tuple(params_records))
            records = cursor.fetchall()
            
            cursor.execute(f"""
                SELECT u.name, u.email,
                       SUM(CASE WHEN a.status = 'present' THEN 1 ELSE 0 END) as present_days,
                       COUNT(a.id) as total_days,
                       (SUM(CASE WHEN a.status = 'present' THEN 1 ELSE 0 END) * 100.0 / COUNT(a.id)) as attendance_percentage
                FROM attendance a
                JOIN users u ON a.student_id = u.id
                WHERE a.class_id = %s AND a.date >= %s AND a.date <= %s{search_clause}
                GROUP BY a.student_id, u.name, u.email
                ORDER BY attendance_percentage DESC
            """, tuple(params_aggregated))
            aggregated = cursor.fetchall()

            # Calculate KPI summary
            total_students = len(aggregated)
            avg_attendance = round(sum(float(r['attendance_percentage']) for r in aggregated) / total_students, 1) if total_students else 0.0
            total_sessions = max((r['total_days'] for r in aggregated), default=0)

            safe_subject = class_info['subject'].replace(' ', '_').lower()
            filename_base = f"attendance_report_{safe_subject}_{start_date}_to_{end_date}"

            from datetime import date

            if export_format == 'csv':
                import io, csv
                from flask import Response
                output = io.StringIO()
                output.write('\ufeff') # UTF-8 BOM
                writer = csv.writer(output)
                writer.writerow(["NS Learnytics — Attendance Report"])
                writer.writerow(["Course / Subject", class_info['subject']])
                writer.writerow(["Instructor", class_info['teacher_name']])
                writer.writerow(["Timeframe", f"{start_date} to {end_date}"])
                writer.writerow(["Student Filter", student_search if student_search else "All Students"])
                writer.writerow(["Average Attendance Rate", f"{avg_attendance}%"])
                writer.writerow(["Total Class Sessions", total_sessions])
                writer.writerow(["Generated On", date.today().isoformat()])
                writer.writerow([]) # Blank row

                # Aggregated Performance Matrix
                writer.writerow(["Student Name", "Student Email", "Days Present", "Total Days", "Attendance Rate (%)"])
                for row in aggregated:
                    writer.writerow([
                        row['name'],
                        row['email'],
                        row['present_days'],
                        row['total_days'],
                        f"{float(row['attendance_percentage']):.1f}%"
                    ])

                output.seek(0)
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
                
                # Sheet 1: Summary Matrix
                ws1 = wb.active
                ws1.title = "Summary Matrix"

                title_font = Font(name="Calibri", size=15, bold=True, color="0F766E")
                sub_font = Font(name="Calibri", size=10, italic=True, color="475569")
                tbl_header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
                tbl_header_fill = PatternFill(start_color="0F766E", end_color="0F766E", fill_type="solid")
                thin_border = Border(
                    left=Side(style='thin', color='CBD5E1'),
                    right=Side(style='thin', color='CBD5E1'),
                    top=Side(style='thin', color='CBD5E1'),
                    bottom=Side(style='thin', color='CBD5E1')
                )

                # Report Banner
                ws1.append(["NS Learnytics — Attendance Summary Matrix"])
                ws1.cell(row=1, column=1).font = title_font
                ws1.append([f"Course: {class_info['subject']} | Instructor: {class_info['teacher_name']}"])
                ws1.cell(row=2, column=1).font = sub_font
                ws1.append([f"Period: {start_date} to {end_date} | Filter: {student_search if student_search else 'All Students'} | Avg Rate: {avg_attendance}%"])
                ws1.cell(row=3, column=1).font = sub_font
                ws1.append([])

                headers1 = ["Student Name", "Student Email", "Days Present", "Total Days", "Attendance Rate (%)"]
                ws1.append(headers1)
                header_row_1 = 5

                for c_idx in range(1, len(headers1) + 1):
                    cell = ws1.cell(row=header_row_1, column=c_idx)
                    cell.font = tbl_header_font
                    cell.fill = tbl_header_fill
                    cell.alignment = Alignment(horizontal="center" if c_idx >= 3 else "left")
                    cell.border = thin_border

                for r_idx, row in enumerate(aggregated, start=header_row_1 + 1):
                    ws1.append([
                        row['name'],
                        row['email'],
                        row['present_days'],
                        row['total_days'],
                        round(float(row['attendance_percentage']), 1)
                    ])
                    for c_idx in range(1, len(headers1) + 1):
                        cell = ws1.cell(row=r_idx, column=c_idx)
                        cell.border = thin_border
                        if c_idx >= 3:
                            cell.alignment = Alignment(horizontal="center")

                for col in ws1.columns:
                    max_len = max(len(str(cell.value or '')) for cell in col)
                    col_letter = openpyxl.utils.get_column_letter(col[0].column)
                    ws1.column_dimensions[col_letter].width = max(max_len + 4, 12)

                # Sheet 2: Daily Logs
                ws2 = wb.create_sheet(title="Daily Logs")
                ws2.append(["NS Learnytics — Daily Attendance Logs"])
                ws2.cell(row=1, column=1).font = title_font
                ws2.append([f"Course: {class_info['subject']} | Period: {start_date} to {end_date}"])
                ws2.cell(row=2, column=1).font = sub_font
                ws2.append([])

                headers2 = ["Date", "Student Name", "Student Email", "Status"]
                ws2.append(headers2)
                header_row_2 = 4

                for c_idx in range(1, len(headers2) + 1):
                    cell = ws2.cell(row=header_row_2, column=c_idx)
                    cell.font = tbl_header_font
                    cell.fill = tbl_header_fill
                    cell.alignment = Alignment(horizontal="center" if c_idx in (1, 4) else "left")
                    cell.border = thin_border

                for r_idx, r in enumerate(records, start=header_row_2 + 1):
                    ws2.append([
                        str(r['date']),
                        r['name'],
                        r['email'],
                        r['status'].capitalize()
                    ])
                    for c_idx in range(1, len(headers2) + 1):
                        cell = ws2.cell(row=r_idx, column=c_idx)
                        cell.border = thin_border
                        if c_idx in (1, 4):
                            cell.alignment = Alignment(horizontal="center")

                for col in ws2.columns:
                    max_len = max(len(str(cell.value or '')) for cell in col)
                    col_letter = openpyxl.utils.get_column_letter(col[0].column)
                    ws2.column_dimensions[col_letter].width = max(max_len + 4, 12)

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
                doc = SimpleDocTemplate(buf, pagesize=landscape(letter), leftMargin=25, rightMargin=25, topMargin=25, bottomMargin=25)
                styles = getSampleStyleSheet()

                title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=15, leading=18, textColor=colors.HexColor('#0f766e'))
                meta_style = ParagraphStyle('MetaStyle', parent=styles['Normal'], fontSize=8.5, leading=12, textColor=colors.HexColor('#475569'))

                elements = [
                    Paragraph("NS Learnytics — Attendance Performance Report", title_style),
                    Spacer(1, 3),
                    Paragraph(f"Course: <b>{class_info['subject']}</b> &nbsp;|&nbsp; Instructor: <b>{class_info['teacher_name']}</b> &nbsp;|&nbsp; Period: <b>{start_date}</b> to <b>{end_date}</b>", meta_style),
                    Paragraph(f"Student Filter: <b>{student_search if student_search else 'All Students'}</b> &nbsp;|&nbsp; Enrolled Students: <b>{total_students}</b> &nbsp;|&nbsp; Average Rate: <b>{avg_attendance}%</b>", meta_style),
                    Spacer(1, 8)
                ]

                # KPI Table
                kpi_data = [[
                    f"Class: {class_info['subject']}",
                    f"Total Students: {total_students}",
                    f"Total Class Sessions: {total_sessions}",
                    f"Average Attendance Rate: {avg_attendance}%"
                ]]
                kpi_table = Table(kpi_data, colWidths=[180, 180, 180, 200])
                kpi_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#ecfdf5')),
                    ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#065f46')),
                    ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, -1), 8.5),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#a7f3d0')),
                    ('TOPPADDING', (0, 0), (-1, -1), 4),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ]))
                elements.append(kpi_table)
                elements.append(Spacer(1, 10))

                # Table of Aggregated Matrix
                tbl_data = [["Student Name", "Student Email", "Days Present", "Total Days", "Attendance Rate (%)"]]
                for row in aggregated:
                    tbl_data.append([
                        row['name'],
                        row['email'],
                        str(row['present_days']),
                        str(row['total_days']),
                        f"{float(row['attendance_percentage']):.1f}%"
                    ])

                t = Table(tbl_data, colWidths=[200, 240, 100, 100, 100])
                t.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0f766e')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 8.5),
                    ('ALIGN', (0, 0), (1, -1), 'LEFT'),
                    ('ALIGN', (2, 0), (-1, -1), 'CENTER'),
                    ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                    ('FONTSIZE', (0, 1), (-1, -1), 8),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#ffffff'), colors.HexColor('#f8fafc')]),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
                    ('TOPPADDING', (0, 0), (-1, -1), 4),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
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

            elif export_format == 'json':
                from flask import jsonify
                payload = {
                    "report_title": "Attendance Analytics Report",
                    "generated_at": date.today().isoformat(),
                    "class": {
                        "id": class_info['id'],
                        "subject": class_info['subject'],
                        "teacher": class_info['teacher_name']
                    },
                    "period": {
                        "start_date": start_date,
                        "end_date": end_date
                    },
                    "student_search_filter": student_search if student_search else "ALL",
                    "summary": {
                        "enrolled_students": total_students,
                        "average_attendance_rate": avg_attendance,
                        "total_sessions": total_sessions
                    },
                    "aggregated_matrix": [
                        {
                            "student_name": r['name'],
                            "student_email": r['email'],
                            "days_present": r['present_days'],
                            "total_days": r['total_days'],
                            "attendance_rate": round(float(r['attendance_percentage']), 1)
                        }
                        for r in aggregated
                    ],
                    "daily_logs": [
                        {
                            "date": str(r['date']),
                            "student_name": r['name'],
                            "student_email": r['email'],
                            "status": r['status']
                        }
                        for r in records
                    ]
                }
                return jsonify(payload)
            else:
                return "Invalid export format. Supported formats: pdf, excel, csv, json", 400
    finally:
        conn.close()


@attendance_bp.route('/attendance/finalize', methods=['POST'])
def finalize_attendance():
    import datetime
    role = session.get('role')
    if role not in ('teacher', 'moderator', 'admin', 'superadmin'):
        return jsonify({'error': 'Unauthorized'}), 403

    data = request.get_json() or {}
    class_id = data.get('class_id')
    date = data.get('date') or datetime.date.today().isoformat()

    if not class_id:
        return jsonify({'error': 'class_id required'}), 400

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            if role == 'teacher':
                cursor.execute("SELECT 1 FROM classes WHERE id = %s AND teacher_id = %s", (class_id, session['user_id']))
                if not cursor.fetchone():
                    return jsonify({'error': 'Unauthorized for this localized class sequence'}), 403

            cursor.execute("SELECT student_id FROM enrollments WHERE class_id = %s", (class_id,))
            enrolled_students = [row['student_id'] for row in cursor.fetchall()]

            if not enrolled_students:
                return jsonify({'error': 'No physical students structurally enrolled in this explicit class vector.'}), 400

            cursor.execute("SELECT student_id FROM attendance WHERE class_id = %s AND date = %s", (class_id, date))
            marked_students = set(row['student_id'] for row in cursor.fetchall())

            missing_students = [s for s in enrolled_students if s not in marked_students]
            if not missing_students:
                return jsonify({'success': True, 'message': 'All structurally enrolled students are already exclusively tracked internally for today!'})

            for student_id in missing_students:
                cursor.execute("""
                    INSERT INTO attendance (class_id, student_id, date, status) 
                    VALUES (%s, %s, %s, 'absent')
                    ON DUPLICATE KEY UPDATE status = VALUES(status)
                """, (class_id, student_id, date))
                
                # Trigger Notification for Parents
                try:
                    from utils.notifications import notify_parents_of_absence
                    cursor.execute("SELECT name FROM users WHERE id = %s", (student_id,))
                    s_name = cursor.fetchone()['name']
                    cursor.execute("SELECT subject FROM classes WHERE id = %s", (class_id,))
                    c_name = cursor.fetchone()['subject']
                    notify_parents_of_absence(student_id, s_name, c_name, date)
                except Exception as e:
                    print(f"Notification error: {e}")

            conn.commit()

            return jsonify({'success': True, 'message': f'Algorithm executed successfully: Flagged exactly {len(missing_students)} structurally missing student(s) natively as Absent.'})
    finally:
        conn.close()
