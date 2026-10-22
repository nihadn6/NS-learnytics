from flask import Blueprint, request, jsonify, session, render_template, redirect, url_for, flash, Response
from database.db import get_db_connection
import datetime

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

@performance_bp.route('/marks/report/export', methods=['GET'])
def export_performance_report():
    if session.get('role') not in ('teacher', 'moderator', 'superadmin'):
        return "Unauthorized", 403

    class_id = request.args.get('class_id')
    selected_test = request.args.get('test_name', '').strip()
    export_format = request.args.get('format', 'pdf').lower()

    if not class_id:
        return "Missing class_id", 400

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Permissions check for teachers
            if session['role'] == 'teacher':
                cursor.execute("SELECT 1 FROM classes WHERE id = %s AND teacher_id = %s", (class_id, session['user_id']))
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

            # Fetch strictly unique assessments conducted for this specific class
            cursor.execute("""
                SELECT test_name, MAX(max_marks) as max_marks, MIN(date_recorded) as date_recorded
                FROM marks 
                WHERE class_id = %s 
                GROUP BY test_name
                ORDER BY MIN(date_recorded) ASC, test_name ASC
            """, (class_id,))
            class_tests = cursor.fetchall()

            if selected_test:
                matched_tests = [t['test_name'] for t in class_tests if t['test_name'] == selected_test]
                test_columns = matched_tests if matched_tests else [selected_test]
            else:
                test_columns = [t['test_name'] for t in class_tests]

            # Fetch enrolled students
            cursor.execute("""
                SELECT u.id, u.name 
                FROM enrollments e 
                JOIN users u ON e.student_id = u.id 
                WHERE e.class_id = %s 
                ORDER BY u.name
            """, (class_id,))
            students = cursor.fetchall()

            # Fetch marks for this class
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

            # Calculate assessment summary statistics when single exam is filtered
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

            from datetime import date
            safe_subject = class_info['subject'].replace(' ', '_').lower()
            safe_test = (f"_{selected_test.replace(' ', '_').lower()}" if selected_test else "_all_assessments")
            filename_base = f"academic_report_{safe_subject}{safe_test}_{date.today().isoformat()}"

            if export_format == 'csv':
                import io, csv
                from flask import Response
                output = io.StringIO()
                output.write('\ufeff') # UTF-8 BOM
                writer = csv.writer(output)
                writer.writerow(["NS Learnytics — Academic Performance Report"])
                writer.writerow(["Subject / Class", class_info['subject']])
                writer.writerow(["Instructor", class_info['teacher_name']])
                writer.writerow(["Assessment Filter", selected_test if selected_test else "All Assessments"])
                writer.writerow(["Generated On", date.today().isoformat()])
                writer.writerow(["Total Enrolled Students", len(students)])
                if exam_stats:
                    writer.writerow(["Class Average", f"{exam_stats['avg_score']} ({exam_stats['avg_pct']}%)"])
                    writer.writerow(["Highest Score", f"{exam_stats['highest_score']} ({exam_stats['highest_pct']}%)"])
                    writer.writerow(["Lowest Score", f"{exam_stats['lowest_score']} ({exam_stats['lowest_pct']}%)"])
                    writer.writerow(["Pass Rate", f"{exam_stats['pass_rate']}% ({exam_stats['pass_count']}/{exam_stats['turnout']} passed)"])
                writer.writerow([]) # Blank row

                # Table headers
                header_row = ["Student ID", "Student Name"]
                for col in test_columns:
                    header_row.extend([f"{col} (Score)", f"{col} (%)"])
                writer.writerow(header_row)

                # Student rows
                for s in students:
                    row = [s['id'], s['name']]
                    for col in test_columns:
                        m_info = marks_map.get(s['id'], {}).get(col)
                        if m_info:
                            row.extend([m_info['display'], f"{m_info['pct']}%"])
                        else:
                            row.extend(["Not Taken", "N/A"])
                    writer.writerow(row)

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
                ws = wb.active
                ws.title = "Academic Report"

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
                ws.append(["NS Learnytics — Academic Performance Report"])
                ws.cell(row=1, column=1).font = title_font
                ws.append([f"Course: {class_info['subject']} | Instructor: {class_info['teacher_name']}"])
                ws.cell(row=2, column=1).font = sub_font
                ws.append([f"Assessment: {selected_test if selected_test else 'All Assessments'} | Date: {date.today().isoformat()} | Enrolled: {len(students)} Students"])
                ws.cell(row=3, column=1).font = sub_font

                curr_row = 4
                if exam_stats:
                    ws.append([f"Class Average: {exam_stats['avg_score']} ({exam_stats['avg_pct']}%) | High: {exam_stats['highest_score']} | Low: {exam_stats['lowest_score']} | Pass Rate: {exam_stats['pass_rate']}%"])
                    ws.cell(row=4, column=1).font = sub_font
                    curr_row = 5

                ws.append([]) # Blank
                curr_row += 1

                # Table Header
                headers = ["Student ID", "Student Name"]
                for col in test_columns:
                    headers.extend([f"{col} (Score)", f"{col} (%)"])
                ws.append(headers)
                header_row_idx = curr_row

                for col_idx in range(1, len(headers) + 1):
                    cell = ws.cell(row=header_row_idx, column=col_idx)
                    cell.font = tbl_header_font
                    cell.fill = tbl_header_fill
                    cell.alignment = Alignment(horizontal="center" if col_idx != 2 else "left")
                    cell.border = thin_border

                # Data rows
                for r_idx, s in enumerate(students, start=header_row_idx + 1):
                    row_data = [s['id'], s['name']]
                    for col in test_columns:
                        m_info = marks_map.get(s['id'], {}).get(col)
                        if m_info:
                            row_data.extend([m_info['display'], f"{m_info['pct']}%"])
                        else:
                            row_data.extend(["Not Taken", "-"])
                    ws.append(row_data)
                    for c_idx in range(1, len(headers) + 1):
                        cell = ws.cell(row=r_idx, column=c_idx)
                        cell.border = thin_border
                        if c_idx > 2 or c_idx == 1:
                            cell.alignment = Alignment(horizontal="center")

                # Column widths auto-adjustment
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
                doc = SimpleDocTemplate(buf, pagesize=landscape(letter), leftMargin=25, rightMargin=25, topMargin=25, bottomMargin=25)
                styles = getSampleStyleSheet()

                title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=15, leading=18, textColor=colors.HexColor('#0f766e'))
                meta_style = ParagraphStyle('MetaStyle', parent=styles['Normal'], fontSize=8.5, leading=12, textColor=colors.HexColor('#475569'))

                elements = [
                    Paragraph("NS Learnytics — Academic Performance Report", title_style),
                    Spacer(1, 3),
                    Paragraph(f"Course: <b>{class_info['subject']}</b> &nbsp;|&nbsp; Instructor: <b>{class_info['teacher_name']}</b> &nbsp;|&nbsp; Assessment: <b>{selected_test if selected_test else 'All Assessments'}</b> &nbsp;|&nbsp; Date: <b>{date.today().isoformat()}</b>", meta_style),
                    Paragraph(f"Total Enrolled Students: <b>{len(students)}</b> &nbsp;|&nbsp; Total Assessments Conducted: <b>{len(test_columns)}</b>", meta_style),
                    Spacer(1, 8)
                ]

                if exam_stats:
                    kpi_data = [[
                        f"Class Average: {exam_stats['avg_score']} ({exam_stats['avg_pct']}%)",
                        f"Highest: {exam_stats['highest_score']} ({exam_stats['highest_pct']}%)",
                        f"Lowest: {exam_stats['lowest_score']} ({exam_stats['lowest_pct']}%)",
                        f"Pass Rate: {exam_stats['pass_rate']}% ({exam_stats['pass_count']}/{exam_stats['turnout']})",
                        f"Turnout: {exam_stats['turnout']}/{exam_stats['roster_count']} ({exam_stats['turnout_pct']}%)"
                    ]]
                    kpi_table = Table(kpi_data, colWidths=[150, 140, 140, 160, 140])
                    kpi_table.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#ecfdf5')),
                        ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#065f46')),
                        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
                        ('FONTSIZE', (0, 0), (-1, -1), 8),
                        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#a7f3d0')),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                        ('TOPPADDING', (0, 0), (-1, -1), 4),
                    ]))
                    elements.append(kpi_table)
                    elements.append(Spacer(1, 8))

                # Table headers
                tbl_headers = ["Student Name"]
                for col in test_columns:
                    tbl_headers.append(f"{col}")
                tbl_data = [tbl_headers]

                for s in students:
                    row = [s['name']]
                    for col in test_columns:
                        m_info = marks_map.get(s['id'], {}).get(col)
                        if m_info:
                            row.append(f"{m_info['display']} ({m_info['pct']}%)")
                        else:
                            row.append("Not Taken")
                    tbl_data.append(row)

                col_count = len(tbl_headers)
                name_w = 160
                remaining_w = 740 - name_w
                col_w = max(50, remaining_w / max(1, (col_count - 1)))
                widths = [name_w] + [col_w] * (col_count - 1)

                t = Table(tbl_data, colWidths=widths)
                t.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0f766e')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 8.5),
                    ('ALIGN', (0, 0), (0, -1), 'LEFT'),
                    ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
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
                    "report_title": "Academic Performance Report",
                    "generated_at": date.today().isoformat(),
                    "class": {
                        "id": class_info['id'],
                        "subject": class_info['subject'],
                        "teacher": class_info['teacher_name']
                    },
                    "assessment_filter": selected_test if selected_test else "ALL",
                    "assessments": test_columns,
                    "summary_statistics": exam_stats,
                    "student_records": [
                        {
                            "student_id": s['id'],
                            "student_name": s['name'],
                            "marks": {
                                col: marks_map.get(s['id'], {}).get(col) for col in test_columns
                            }
                        }
                        for s in students
                    ]
                }
                return jsonify(payload)
            else:
                return "Invalid export format. Supported formats: pdf, excel, csv, json", 400
    finally:
        conn.close()


@performance_bp.route('/marks/import', methods=['GET'])
def import_marks_view():
    role = session.get('role')
    if role not in ('teacher', 'moderator', 'admin', 'superadmin'):
        return "Unauthorized", 403

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            if role == 'teacher':
                cursor.execute("""
                    SELECT c.id, c.subject, c.schedule, COUNT(e.student_id) as student_count
                    FROM classes c
                    LEFT JOIN enrollments e ON c.id = e.class_id
                    WHERE c.teacher_id = %s
                    GROUP BY c.id, c.subject, c.schedule
                    ORDER BY c.subject
                """, (session['user_id'],))
                classes = cursor.fetchall()
                teachers = []
            else:
                cursor.execute("SELECT id, name FROM users WHERE role = 'teacher' ORDER BY name")
                teachers = cursor.fetchall()
                cursor.execute("""
                    SELECT c.id, c.subject, c.schedule, c.teacher_id, u.name as teacher_name, COUNT(e.student_id) as student_count
                    FROM classes c
                    JOIN users u ON c.teacher_id = u.id
                    LEFT JOIN enrollments e ON c.id = e.class_id
                    GROUP BY c.id, c.subject, c.schedule, c.teacher_id, u.name
                    ORDER BY c.subject
                """)
                classes = cursor.fetchall()

            today_date = datetime.date.today().isoformat()
            selected_class_id = request.args.get('class_id', type=int)

            return render_template('marks_import.html',
                                   classes=classes,
                                   teachers=teachers,
                                   today_date=today_date,
                                   selected_class_id=selected_class_id)
    finally:
        conn.close()


@performance_bp.route('/marks/template/<int:class_id>', methods=['GET'])
def download_marks_template(class_id):
    role = session.get('role')
    if role not in ('teacher', 'moderator', 'admin', 'superadmin'):
        return "Unauthorized", 403

    export_format = request.args.get('format', 'xlsx').lower()
    test_name = (request.args.get('test_name') or 'Term Assessment 01').strip()
    try:
        max_marks = float(request.args.get('max_marks') or 100.0)
    except (ValueError, TypeError):
        max_marks = 100.0
    exam_date = request.args.get('date') or datetime.date.today().isoformat()

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            if role == 'teacher':
                cursor.execute("SELECT id, subject FROM classes WHERE id = %s AND teacher_id = %s", (class_id, session['user_id']))
            else:
                cursor.execute("SELECT id, subject FROM classes WHERE id = %s", (class_id,))
            class_row = cursor.fetchone()
            if not class_row:
                return "Class not found or unauthorized", 404

            subject_slug = "".join(c for c in class_row['subject'] if c.isalnum() or c in (' ', '_', '-')).strip().replace(' ', '_')
            test_slug = "".join(c for c in test_name if c.isalnum() or c in (' ', '_', '-')).strip().replace(' ', '_')

            # Fetch enrolled students
            cursor.execute("""
                SELECT u.id, u.name, u.email
                FROM enrollments e
                JOIN users u ON e.student_id = u.id
                WHERE e.class_id = %s
                ORDER BY u.name
            """, (class_id,))
            students = cursor.fetchall()

            if export_format == 'csv':
                import csv
                import io
                output = io.StringIO()
                output.write('\ufeff')  # UTF-8 BOM
                writer = csv.writer(output)
                writer.writerow(['student_id', 'student_name', 'email', 'test_name', 'max_marks', 'date_recorded', 'marks_obtained', 'remarks'])
                for s in students:
                    writer.writerow([s['id'], s['name'], s['email'] or '', test_name, f"{max_marks:.2f}", exam_date, '', ''])

                resp = Response(output.getvalue(), mimetype='text/csv')
                resp.headers['Content-Disposition'] = f'attachment; filename=marks_template_{subject_slug}_{test_slug}.csv'
                return resp

            # Default: Excel .xlsx
            import io
            import openpyxl
            from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Assessment Scores"

            header_fill = PatternFill(start_color="312E81", end_color="312E81", fill_type="solid")
            header_font = Font(name="Arial", size=11, bold=True, color="FFFFFF")
            thin_border = Border(
                left=Side(style='thin', color='E2E8F0'),
                right=Side(style='thin', color='E2E8F0'),
                top=Side(style='thin', color='E2E8F0'),
                bottom=Side(style='thin', color='E2E8F0')
            )

            headers = ['Student ID', 'Student Name', 'Email', 'Assessment Title', 'Max Marks', 'Exam Date', 'Marks Obtained', 'Remarks']
            ws.append(headers)

            for col_idx in range(1, len(headers) + 1):
                cell = ws.cell(row=1, column=col_idx)
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

            for s in students:
                ws.append([s['id'], s['name'], s['email'] or '', test_name, max_marks, exam_date, '', ''])

            # Apply cell styling
            for row in ws.iter_rows(min_row=2, max_row=len(students) + 1, min_col=1, max_col=len(headers)):
                for cell in row:
                    cell.border = thin_border
                    cell.font = Font(name="Arial", size=10)
                    if cell.column == 1:
                        cell.alignment = Alignment(horizontal="center")
                    elif cell.column in (5, 6):
                        cell.alignment = Alignment(horizontal="center")
                    elif cell.column == 7:
                        cell.alignment = Alignment(horizontal="right")
                        cell.number_format = '0.00'

            # Auto-fit column widths
            for col in ws.columns:
                max_len = max(len(str(cell.value or '')) for cell in col)
                col_letter = openpyxl.utils.get_column_letter(col[0].column)
                ws.column_dimensions[col_letter].width = max(max_len + 5, 14)

            ws.row_dimensions[1].height = 28

            buf = io.BytesIO()
            wb.save(buf)
            buf.seek(0)

            resp = Response(buf.getvalue(), mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            resp.headers['Content-Disposition'] = f'attachment; filename=marks_template_{subject_slug}_{test_slug}.xlsx'
            return resp
    finally:
        conn.close()


@performance_bp.route('/marks/import', methods=['POST'], endpoint='import_marks_post')
@performance_bp.route('/marks/bulk-upload', methods=['POST'], endpoint='bulk_upload_marks')
def import_marks_post():
    role = session.get('role')
    if role not in ('teacher', 'moderator', 'admin', 'superadmin'):
        return "Unauthorized", 403

    class_id = request.form.get('class_id', type=int)
    default_test_name = (request.form.get('test_name') or 'Term Assessment 01').strip()
    try:
        default_max_marks = float(request.form.get('max_marks') or 100.0)
    except (ValueError, TypeError):
        default_max_marks = 100.0
    default_date = (request.form.get('date_recorded') or '').strip()
    send_notifications = bool(request.form.get('send_notifications'))
    update_existing = bool(request.form.get('update_existing', True))
    redirect_dest = (request.form.get('redirect_to') or '').strip()
    file = request.files.get('file')

    def _get_redirect():
        if redirect_dest:
            return redirect_dest
        return url_for('performance.import_marks_view', class_id=class_id) if class_id else url_for('performance.import_marks_view')

    if not class_id:
        flash('Please select a valid class section.', 'error')
        return redirect(_get_redirect())

    if not default_date:
        default_date = datetime.date.today().isoformat()

    if not file or not file.filename:
        flash('Please select an Excel (.xlsx) or CSV (.csv) file to import.', 'error')
        return redirect(_get_redirect())

    filename = file.filename.lower()
    if not (filename.endswith('.csv') or filename.endswith('.xlsx') or filename.endswith('.xls')):
        flash('Unsupported file format. Please upload a .xlsx or .csv exam results file.', 'error')
        return redirect(_get_redirect())

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Check teacher permission
            if role == 'teacher':
                cursor.execute("SELECT id, subject FROM classes WHERE id = %s AND teacher_id = %s", (class_id, session['user_id']))
            else:
                cursor.execute("SELECT id, subject FROM classes WHERE id = %s", (class_id,))
            class_row = cursor.fetchone()
            if not class_row:
                flash('Unauthorized or invalid class section.', 'error')
                return redirect(url_for('performance.import_marks_view'))

            class_subject = class_row['subject']

            # Enrolled students for validation
            cursor.execute("SELECT student_id FROM enrollments WHERE class_id = %s", (class_id,))
            enrolled_student_ids = {row['student_id'] for row in cursor.fetchall()}

            # Parse file rows into raw_rows
            if filename.endswith('.csv'):
                import csv
                import io
                try:
                    file_bytes = file.read()
                    for enc in ('utf-8-sig', 'utf-8', 'latin-1'):
                        try:
                            text = file_bytes.decode(enc)
                            break
                        except UnicodeDecodeError:
                            continue
                    else:
                        text = file_bytes.decode('utf-8', errors='ignore')

                    stream = io.StringIO(text, newline=None)
                    reader = csv.reader(stream)
                    raw_rows = list(reader)
                except Exception as e:
                    flash(f'Failed to parse CSV file: {str(e)}', 'error')
                    return redirect(url_for('performance.import_marks_view', class_id=class_id))

            else:
                import io
                import openpyxl
                try:
                    wb = openpyxl.load_workbook(io.BytesIO(file.read()), data_only=True)
                    ws = wb.active
                    raw_rows = list(ws.iter_rows(values_only=True))
                except Exception as e:
                    flash(f'Failed to parse Excel workbook: {str(e)}', 'error')
                    return redirect(url_for('performance.import_marks_view', class_id=class_id))

            if not raw_rows:
                flash('The uploaded file is empty.', 'error')
                return redirect(url_for('performance.import_marks_view', class_id=class_id))

            # Find header indices
            header_row = [str(col or '').strip().lower() for col in raw_rows[0]]
            id_idx = None
            marks_idx = None
            test_idx = None
            max_idx = None
            date_idx = None

            for idx, h in enumerate(header_row):
                clean_h = h.replace('_', ' ').replace('-', ' ').strip()
                if clean_h in ('student id', 'studentid', 'id', 'student no', 'reg no'):
                    id_idx = idx
                elif clean_h in ('marks obtained', 'marks', 'score', 'mark', 'result', 'grade'):
                    marks_idx = idx
                elif clean_h in ('test name', 'assessment title', 'assessment', 'exam', 'title'):
                    test_idx = idx
                elif clean_h in ('max marks', 'max', 'total marks'):
                    max_idx = idx
                elif clean_h in ('date recorded', 'date', 'exam date', 'assessment date'):
                    date_idx = idx

            # Fallbacks
            if id_idx is None:
                id_idx = 0
            if marks_idx is None:
                if len(header_row) >= 7:
                    marks_idx = 6
                elif len(header_row) >= 3:
                    marks_idx = 2
                else:
                    marks_idx = 1

            inserted_count = 0
            updated_count = 0
            skipped_unregistered = 0
            skipped_blank = 0
            scores = []

            for row_num, row in enumerate(raw_rows[1:], start=2):
                if not row or all(c is None or str(c).strip() == '' for c in row):
                    continue

                try:
                    raw_id = row[id_idx] if len(row) > id_idx else None
                    if raw_id is None or str(raw_id).strip() == '':
                        continue

                    # Extract integer student ID
                    student_id = int(float(str(raw_id).strip()))

                    # Verify enrollment in this class
                    if student_id not in enrolled_student_ids:
                        skipped_unregistered += 1
                        continue

                    # Extract marks_obtained
                    raw_marks = row[marks_idx] if len(row) > marks_idx else None
                    if raw_marks is None or str(raw_marks).strip() == '':
                        skipped_blank += 1
                        continue

                    marks_obtained = float(str(raw_marks).replace(',', '').strip())

                    # Extract assessment test name
                    row_test = default_test_name
                    if test_idx is not None and len(row) > test_idx and row[test_idx]:
                        val_t = str(row[test_idx]).strip()
                        if val_t:
                            row_test = val_t

                    # Extract max marks
                    row_max = default_max_marks
                    if max_idx is not None and len(row) > max_idx and row[max_idx]:
                        try:
                            val_m = float(str(row[max_idx]).replace(',', '').strip())
                            if val_m > 0:
                                row_max = val_m
                        except (ValueError, TypeError):
                            pass

                    # Extract date
                    row_date = default_date
                    if date_idx is not None and len(row) > date_idx and row[date_idx]:
                        val_d = row[date_idx]
                        if isinstance(val_d, (datetime.date, datetime.datetime)):
                            row_date = val_d.strftime('%Y-%m-%d')
                        elif isinstance(val_d, str) and val_d.strip():
                            val_d_str = val_d.strip()
                            for fmt in ('%Y-%m-%d', '%Y/%m/%d', '%d-%m-%Y', '%d/%m/%Y'):
                                try:
                                    row_date = datetime.datetime.strptime(val_d_str, fmt).strftime('%Y-%m-%d')
                                    break
                                except ValueError:
                                    pass

                    # Check if marks record already exists
                    cursor.execute("""
                        SELECT id FROM marks
                        WHERE class_id = %s AND student_id = %s AND test_name = %s
                    """, (class_id, student_id, row_test))
                    existing = cursor.fetchone()

                    if existing:
                        if update_existing:
                            cursor.execute("""
                                UPDATE marks
                                SET marks_obtained = %s, max_marks = %s, date_recorded = %s
                                WHERE id = %s
                            """, (marks_obtained, row_max, row_date, existing['id']))
                            updated_count += 1
                        else:
                            continue
                    else:
                        cursor.execute("""
                            INSERT INTO marks (class_id, student_id, test_name, marks_obtained, max_marks, date_recorded)
                            VALUES (%s, %s, %s, %s, %s, %s)
                        """, (class_id, student_id, row_test, marks_obtained, row_max, row_date))
                        inserted_count += 1

                    scores.append(marks_obtained)

                    # Notifications
                    if send_notifications:
                        try:
                            from utils.notifications import notify_parents_of_marks
                            cursor.execute("SELECT name FROM users WHERE id = %s", (student_id,))
                            s_name_row = cursor.fetchone()
                            s_name = s_name_row['name'] if s_name_row else 'Student'
                            notify_parents_of_marks(student_id, s_name, class_subject, row_test, marks_obtained, row_max)

                            # Also notify student account
                            cursor.execute("""
                                INSERT INTO notifications (user_id, message, type)
                                VALUES (%s, %s, 'marks')
                            """, (student_id, f"New Marks Published: You scored {marks_obtained}/{row_max} in {row_test} ({class_subject})."))
                        except Exception as e:
                            print(f"Marks notification error: {e}")

                except Exception:
                    continue

            conn.commit()

            total_graded = inserted_count + updated_count
            msg_parts = [f"Successfully recorded grades for {total_graded} student(s) in {class_subject} ({default_test_name})."]
            if updated_count > 0:
                msg_parts.append(f"({updated_count} existing record(s) updated).")
            if scores:
                avg_score = sum(scores) / len(scores)
                msg_parts.append(f"Class Average: {avg_score:.1f} / {default_max_marks:.0f}.")
            if skipped_unregistered > 0:
                msg_parts.append(f"{skipped_unregistered} unlisted ID(s) skipped.")
            if skipped_blank > 0:
                msg_parts.append(f"{skipped_blank} blank score(s) skipped.")

            flash(" ".join(msg_parts), "success" if total_graded > 0 else "info")
            return redirect(_get_redirect())
    except Exception as e:
        flash(f'An unexpected error occurred during marks import: {str(e)}', 'error')
        return redirect(_get_redirect())
    finally:
        conn.close()

