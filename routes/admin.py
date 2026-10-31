from flask import Blueprint, request, jsonify, session, render_template, redirect, url_for, flash
from database.db import get_db_connection
from werkzeug.security import generate_password_hash
import uuid
import datetime
from services.ai_risk_predictor import risk_predictor
from services.student_of_month import get_or_calculate_student_of_the_month

admin_bp = Blueprint('admin', __name__)

@admin_bp.route('/admin/dashboard', methods=['GET'])
def dashboard():
    if session.get('role') != 'superadmin':
        return "Unauthorized", 403
        
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Fetch staff (teachers and moderators)
            cursor.execute("SELECT id, name, email, role FROM users WHERE role IN ('teacher', 'moderator')")
            staff = cursor.fetchall()
            # Fetch students
            cursor.execute("SELECT id, name, email, role FROM users WHERE role = 'student'")
            students = cursor.fetchall()
            
            # System Stats
            cursor.execute("SELECT COUNT(*) as cnt FROM users WHERE role = 'student'")
            total_students_count = cursor.fetchone()['cnt']
            
            cursor.execute("SELECT COUNT(*) as cnt FROM users WHERE role IN ('teacher', 'moderator')")
            total_staff_count = cursor.fetchone()['cnt']
            
            cursor.execute("SELECT SUM(amount) as total FROM payments")
            total_revenue = float(cursor.fetchone()['total'] or 0.0)

            # Pending Parent Requests
            cursor.execute("SELECT COUNT(*) as cnt FROM parent_student_links WHERE status = 'pending'")
            pending_parent_requests_count = cursor.fetchone()['cnt']

            # Total Classes
            cursor.execute("SELECT COUNT(*) as cnt FROM classes")
            total_classes_count = cursor.fetchone()['cnt']

            # Today's Check-in Count
            cursor.execute("SELECT COUNT(*) as cnt FROM attendance WHERE date = CURDATE() AND status = 'present'")
            today_attendance = cursor.fetchone()['cnt']

            # Today's Total Fees Collected
            cursor.execute("SELECT SUM(amount) as total FROM payments WHERE payment_date = CURDATE()")
            today_fees = float(cursor.fetchone()['total'] or 0.0)

            # Live Stream of Recent Fee Payments
            cursor.execute("""
                SELECT p.id, p.amount, p.payment_date, p.period, u.name as student_name, c.subject
                FROM payments p
                JOIN users u ON p.student_id = u.id
                JOIN classes c ON p.class_id = c.id
                ORDER BY p.id DESC LIMIT 6
            """)
            recent_payments = cursor.fetchall()

            # Performance Trends (Institutional Average Score Progression)
            cursor.execute("""
                SELECT m.test_name, AVG(m.marks_obtained/m.max_marks * 100) as avg_score
                FROM marks m
                GROUP BY m.test_name
                ORDER BY MIN(m.date_recorded) ASC
            """)
            perf_trends = cursor.fetchall()
            perf_labels = [p['test_name'] for p in perf_trends]
            perf_data = [round(float(p['avg_score']), 1) for p in perf_trends]

            # Latest Test Grade Distribution (Institutional Grade Spread)
            cursor.execute("""
                SELECT m.test_name, c.subject, MAX(m.date_recorded) as test_date
                FROM marks m
                JOIN classes c ON m.class_id = c.id
                GROUP BY m.test_name, c.subject
                ORDER BY test_date DESC LIMIT 1
            """)
            latest_test = cursor.fetchone()

            grade_dist = {'A': 0, 'B': 0, 'C': 0, 'Needs Support': 0}
            latest_test_name = None
            latest_test_subject = None
            if latest_test:
                latest_test_name = latest_test['test_name']
                latest_test_subject = latest_test['subject']
                cursor.execute("""
                    SELECT (m.marks_obtained / m.max_marks * 100) as pct
                    FROM marks m
                    WHERE m.test_name = %s
                """, (latest_test_name,))
                m_rows = cursor.fetchall()
                for r in m_rows:
                    score = float(r['pct'] or 0)
                    if score >= 75:
                        grade_dist['A'] += 1
                    elif score >= 65:
                        grade_dist['B'] += 1
                    elif score >= 50:
                        grade_dist['C'] += 1
                    else:
                        grade_dist['Needs Support'] += 1

            # Fetch Executive AI Risk Predictor Top 5 At-Risk Students (Institution-Wide)
            admin_risk_settings = risk_predictor.get_user_risk_settings(session.get('user_id'))
            top_5_at_risk = risk_predictor.get_all_student_risks(user_risk_settings=admin_risk_settings)[:5]

            # Student of the Month evaluation
            students_of_month, som_month_label = get_or_calculate_student_of_the_month(conn)

            # Today's Scheduled Classes Across Campus
            cursor.execute("""
                SELECT c.id, c.subject, c.schedule, c.fee, u.name as teacher_name, COUNT(e.student_id) as student_count
                FROM classes c
                JOIN users u ON c.teacher_id = u.id
                LEFT JOIN enrollments e ON c.id = e.class_id
                GROUP BY c.id, c.subject, c.schedule, c.fee, u.name
                ORDER BY c.subject
            """)
            all_classes = cursor.fetchall()

            today_day_short = datetime.date.today().strftime('%a')
            today_day_full = datetime.date.today().strftime('%A')
            today_name = today_day_full

            todays_classes = []
            for c in all_classes:
                sched = (c.get('schedule') or '').lower()
                if today_day_short.lower() in sched or today_day_full.lower() in sched:
                    todays_classes.append(c)

            # Institutional Bottlenecks: Total Ungraded Submissions in LMS
            cursor.execute("""
                SELECT COUNT(*) as cnt
                FROM assignment_submissions sub
                WHERE sub.status = 'submitted'
            """)
            total_ungraded_submissions = cursor.fetchone()['cnt']

            # Institutional Low Attendance Alert (<60%)
            cursor.execute("""
                SELECT e.student_id, u.name, 
                       SUM(CASE WHEN a.status = 'present' THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(a.id), 0) as attendance_pct
                FROM enrollments e
                JOIN users u ON e.student_id = u.id
                LEFT JOIN attendance a ON e.class_id = a.class_id AND e.student_id = a.student_id
                GROUP BY e.student_id, u.name
                HAVING attendance_pct IS NOT NULL AND attendance_pct < 60
            """)
            low_attendance_students = cursor.fetchall()
            low_attendance_count = len(low_attendance_students)

            # Recent User Signups
            cursor.execute("SELECT id, name, email, role, created_at FROM users ORDER BY id DESC LIMIT 5")
            recent_users = cursor.fetchall()

            return render_template('admin_dashboard.html', 
                                   staff=staff, 
                                   students=students,
                                   total_students_count=total_students_count,
                                   total_staff_count=total_staff_count,
                                   total_revenue=total_revenue,
                                   today_attendance=today_attendance,
                                   today_fees=today_fees,
                                   recent_payments=recent_payments,
                                   perf_labels=perf_labels,
                                   perf_data=perf_data,
                                   latest_test_name=latest_test_name,
                                   latest_test_subject=latest_test_subject,
                                   grade_dist=grade_dist,
                                   top_5_at_risk=top_5_at_risk,
                                   students_of_month=students_of_month,
                                   som_month_label=som_month_label,
                                   todays_classes=todays_classes,
                                   today_name=today_name,
                                   total_ungraded_submissions=total_ungraded_submissions,
                                   low_attendance_count=low_attendance_count,
                                   pending_parent_requests_count=pending_parent_requests_count,
                                   total_classes_count=total_classes_count,
                                   recent_users=recent_users)
    finally:
        conn.close()

@admin_bp.route('/admin/create_staff', methods=['POST'])
def create_staff():
    if session.get('role') != 'superadmin':
        return "Unauthorized", 403
        
    data = request.form
    name = data.get('name')
    email = data.get('email')
    password = data.get('password')
    role = data.get('role')
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
            if cursor.fetchone():
                return "Email already exists", 400
                
            pw_hash = generate_password_hash(password)
            cursor.execute("INSERT INTO users (name, email, password_hash, role) VALUES (%s, %s, %s, %s)",
                           (name, email, pw_hash, role))
            user_id = cursor.lastrowid
            
            if role == 'teacher':
                cursor.execute("INSERT INTO teacher_profiles (user_id) VALUES (%s)", (user_id,))
            
            conn.commit()
            return redirect(url_for('admin.dashboard'))
    finally:
        conn.close()


@admin_bp.route('/admin/create_parent', methods=['POST'])
def create_parent():
    if session.get('role') != 'superadmin':
        return "Unauthorized", 403

    data = request.form
    name = data.get('name')
    email = data.get('email')
    password = data.get('password')
    student_id = data.get('student_id', '').strip()

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Check email uniqueness
            cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
            if cursor.fetchone():
                return "Email already exists", 400

            pw_hash = generate_password_hash(password)
            cursor.execute(
                "INSERT INTO users (name, email, password_hash, role) VALUES (%s, %s, %s, 'parent')",
                (name, email, pw_hash)
            )
            parent_id = cursor.lastrowid

            # Optionally link to a student immediately (approved)
            if student_id:
                cursor.execute("SELECT id FROM users WHERE id = %s AND role = 'student'", (student_id,))
                if cursor.fetchone():
                    cursor.execute(
                        "INSERT INTO parent_student_links (parent_id, student_id, status) VALUES (%s, %s, 'approved')",
                        (parent_id, student_id)
                    )

            conn.commit()
            return redirect(url_for('admin.dashboard'))
    finally:
        conn.close()


@admin_bp.route('/admin/create_student', methods=['POST'])
def create_student():
    if session.get('role') != 'superadmin':
        return "Unauthorized", 403

    data = request.form
    name = data.get('name')
    email = data.get('email')
    password = data.get('password')
    grade = data.get('grade') or ''

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
            if cursor.fetchone():
                return "Email already exists", 400

            pw_hash = generate_password_hash(password)
            cursor.execute("INSERT INTO users (name, email, password_hash, role) VALUES (%s, %s, %s, 'student')",
                           (name, email, pw_hash))
            user_id = cursor.lastrowid

            # generate QR token for student
            token = uuid.uuid4().hex
            cursor.execute("INSERT INTO student_profiles (user_id, grade, qr_code) VALUES (%s, %s, %s)",
                           (user_id, grade, token))

            conn.commit()
            return redirect(url_for('admin.dashboard'))
    finally:
        conn.close()

@admin_bp.route('/admin/parent-requests', methods=['GET'])
def view_parent_requests():
    if session.get('role') != 'superadmin':
        return "Unauthorized", 403
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT psl.id, p.name as parent_name, p.email as parent_email, 
                       s.name as student_name, s.email as student_email, psl.status, psl.created_at
                FROM parent_student_links psl
                JOIN users p ON psl.parent_id = p.id
                JOIN users s ON psl.student_id = s.id
                WHERE psl.status = 'pending'
            """)
            pending = cursor.fetchall()
            
            cursor.execute("""
                SELECT psl.id, p.name as parent_name, s.name as student_name, psl.status
                FROM parent_student_links psl
                JOIN users p ON psl.parent_id = p.id
                JOIN users s ON psl.student_id = s.id
                WHERE psl.status != 'pending'
                ORDER BY psl.created_at DESC LIMIT 50
            """)
            history = cursor.fetchall()
            
            return render_template('admin_parent_requests.html', pending=pending, history=history)
    finally:
        conn.close()

@admin_bp.route('/admin/parent-requests/<int:request_id>/<string:action>', methods=['POST'])
def manage_parent_request(request_id, action):
    if session.get('role') != 'superadmin':
        return "Unauthorized", 403
    
    status = 'approved' if action == 'approve' else 'rejected'
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE parent_student_links SET status = %s WHERE id = %s", (status, request_id))
            conn.commit()
        return redirect(url_for('admin.view_parent_requests'))
    finally:
        conn.close()

@admin_bp.route('/admin/manage-users', methods=['GET'])
def manage_users():
    if session.get('role') != 'superadmin':
        return "Unauthorized", 403

    staff_q = request.args.get('staff_q', '').strip()
    student_q = request.args.get('student_q', '').strip()
    staff_role = request.args.get('staff_role', '').strip()

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Fetch staff (teachers and moderators) with optional search filter
            staff_conditions = ["u.role IN ('teacher', 'moderator')"]
            staff_params = []
            if staff_role in ('teacher', 'moderator'):
                staff_conditions.append("u.role = %s")
                staff_params.append(staff_role)
            if staff_q:
                staff_conditions.append("(u.name LIKE %s OR u.email LIKE %s OR CAST(u.id AS CHAR) LIKE %s OR tp.subjects LIKE %s)")
                param = f"%{staff_q}%"
                staff_params.extend([param, param, param, param])

            cursor.execute(f"""
                SELECT u.id, u.name, u.email, u.role, tp.subjects
                FROM users u
                LEFT JOIN teacher_profiles tp ON u.id = tp.user_id
                WHERE {' AND '.join(staff_conditions)}
                ORDER BY u.role, u.name
            """, tuple(staff_params))
            staff = cursor.fetchall()

            # Fetch students with optional search filter
            student_conditions = ["u.role = 'student'"]
            student_params = []
            if student_q:
                student_conditions.append("(u.name LIKE %s OR u.email LIKE %s OR CAST(u.id AS CHAR) LIKE %s OR sp.grade LIKE %s)")
                param = f"%{student_q}%"
                student_params.extend([param, param, param, param])

            cursor.execute(f"""
                SELECT u.id, u.name, u.email, u.role, sp.grade
                FROM users u
                LEFT JOIN student_profiles sp ON u.id = sp.user_id
                WHERE {' AND '.join(student_conditions)}
                ORDER BY u.name
            """, tuple(student_params))
            students = cursor.fetchall()

            # Total counts for badge display
            cursor.execute("SELECT COUNT(*) as c FROM users WHERE role IN ('teacher', 'moderator')")
            total_staff_count = cursor.fetchone()['c']
            cursor.execute("SELECT COUNT(*) as c FROM users WHERE role = 'student'")
            total_students_count = cursor.fetchone()['c']

            return render_template(
                'admin_manage_users.html',
                staff=staff,
                students=students,
                staff_q=staff_q,
                student_q=student_q,
                staff_role=staff_role,
                total_staff_count=total_staff_count,
                total_students_count=total_students_count
            )
    finally:
        conn.close()

@admin_bp.route('/admin/delete_user/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    if session.get('role') != 'superadmin':
        return "Unauthorized", 403
        
    if user_id == session.get('user_id'):
        return "Cannot delete your own active administrator account", 400

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM student_profiles WHERE user_id = %s", (user_id,))
            cursor.execute("DELETE FROM teacher_profiles WHERE user_id = %s", (user_id,))
            cursor.execute("DELETE FROM parent_student_links WHERE parent_id = %s OR student_id = %s", (user_id, user_id))
            cursor.execute("DELETE FROM enrollments WHERE student_id = %s", (user_id,))
            cursor.execute("DELETE FROM attendance WHERE student_id = %s", (user_id,))
            cursor.execute("DELETE FROM marks WHERE student_id = %s", (user_id,))
            cursor.execute("DELETE FROM payments WHERE student_id = %s", (user_id,))
            cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
            conn.commit()
            next_url = request.referrer or url_for('admin.manage_users')
            return redirect(next_url)
    finally:
        conn.close()



# ---------------------------------------------------------------------------
# CLASS MANAGEMENT (Super Admin): view, create, edit, reassign, roster, delete
# ---------------------------------------------------------------------------
import random
import string


def _unique_join_code(cursor, length=8):
    alphabet = string.ascii_uppercase + string.digits
    while True:
        code = ''.join(random.choices(alphabet, k=length))
        cursor.execute("SELECT id FROM classes WHERE join_code = %s", (code,))
        if not cursor.fetchone():
            return code


def _admin_guard():
    return session.get('role') == 'superadmin'


@admin_bp.route('/admin/classes', methods=['GET'])
def manage_classes():
    if not _admin_guard():
        return "Unauthorized", 403

    search = (request.args.get('q') or '').strip()
    teacher_filter = request.args.get('teacher_id') or ''

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            query = """
                SELECT c.id, c.subject, c.schedule, c.fee, c.join_code, c.teacher_id,
                       u.name AS teacher_name, u.email AS teacher_email,
                       (SELECT COUNT(*) FROM enrollments e WHERE e.class_id = c.id) AS enrolled,
                       (SELECT COALESCE(SUM(p.amount), 0) FROM payments p WHERE p.class_id = c.id) AS revenue
                FROM classes c
                JOIN users u ON c.teacher_id = u.id
                WHERE 1=1
            """
            params = []
            if search:
                query += " AND (c.subject LIKE %s OR u.name LIKE %s)"
                like = '%' + search + '%'
                params.extend([like, like])
            if teacher_filter.isdigit():
                query += " AND c.teacher_id = %s"
                params.append(int(teacher_filter))
            query += " ORDER BY c.subject ASC, c.id ASC"
            cursor.execute(query, tuple(params))
            classes = cursor.fetchall()
            for c in classes:
                c['fee'] = float(c['fee'])
                c['revenue'] = float(c['revenue'] or 0)

            cursor.execute("SELECT id, name, email FROM users WHERE role = 'teacher' ORDER BY name")
            teachers = cursor.fetchall()

            return render_template('admin_classes.html', classes=classes, teachers=teachers,
                                   search=search, teacher_filter=teacher_filter)
    finally:
        conn.close()


@admin_bp.route('/admin/classes/create', methods=['POST'])
def admin_create_class():
    if not _admin_guard():
        return "Unauthorized", 403

    f = request.form
    teacher_id = f.get('teacher_id')
    subject = (f.get('subject') or '').strip()
    schedule = (f.get('schedule') or '').strip()
    fee = f.get('fee')
    if not (teacher_id and subject and schedule and fee):
        return "Missing fields", 400
    try:
        fee_val = float(fee)
        if fee_val < 0:
            raise ValueError
    except ValueError:
        return "Invalid fee amount", 400

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM users WHERE id = %s AND role = 'teacher'", (teacher_id,))
            if not cursor.fetchone():
                return "Selected teacher does not exist", 400
            code = _unique_join_code(cursor)
            cursor.execute(
                "INSERT INTO classes (teacher_id, subject, schedule, fee, join_code) VALUES (%s, %s, %s, %s, %s)",
                (teacher_id, subject, schedule, fee_val, code))
        conn.commit()
    finally:
        conn.close()
    return redirect(url_for('admin.manage_classes'))


@admin_bp.route('/admin/classes/<int:class_id>/edit', methods=['POST'])
def admin_edit_class(class_id):
    if not _admin_guard():
        return "Unauthorized", 403

    f = request.form
    teacher_id = f.get('teacher_id')
    subject = (f.get('subject') or '').strip()
    schedule = (f.get('schedule') or '').strip()
    fee = f.get('fee')
    if not (teacher_id and subject and schedule and fee):
        return "Missing fields", 400
    try:
        fee_val = float(fee)
        if fee_val < 0:
            raise ValueError
    except ValueError:
        return "Invalid fee amount", 400

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM users WHERE id = %s AND role = 'teacher'", (teacher_id,))
            if not cursor.fetchone():
                return "Selected teacher does not exist", 400
            # Teacher reassignment keeps the class id, so enrollments, attendance and marks are preserved.
            cursor.execute(
                "UPDATE classes SET teacher_id = %s, subject = %s, schedule = %s, fee = %s WHERE id = %s",
                (teacher_id, subject, schedule, fee_val, class_id))
        conn.commit()
    finally:
        conn.close()
    return redirect(request.referrer or url_for('admin.manage_classes'))


@admin_bp.route('/admin/classes/<int:class_id>/regenerate_code', methods=['POST'])
def admin_regenerate_join_code(class_id):
    if not _admin_guard():
        return "Unauthorized", 403

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            code = _unique_join_code(cursor)
            cursor.execute("UPDATE classes SET join_code = %s WHERE id = %s", (code, class_id))
        conn.commit()
    finally:
        conn.close()
    return redirect(request.referrer or url_for('admin.manage_classes'))


@admin_bp.route('/admin/classes/<int:class_id>/delete', methods=['POST'])
def admin_delete_class(class_id):
    if not _admin_guard():
        return "Unauthorized", 403

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Delete dependents explicitly: MyISAM tables (e.g. MySQL 5.1 WAMP) ignore ON DELETE CASCADE.
            from routes.lms import remove_upload
            cursor.execute("SELECT file_path FROM materials WHERE class_id = %s", (class_id,))
            for m in cursor.fetchall():
                remove_upload(m['file_path'])
            cursor.execute("SELECT attachment_path FROM assignments WHERE class_id = %s", (class_id,))
            for a in cursor.fetchall():
                remove_upload(a['attachment_path'])
            cursor.execute("""
                SELECT s.file_path FROM assignment_submissions s
                JOIN assignments a ON s.assignment_id = a.id WHERE a.class_id = %s
            """, (class_id,))
            for s in cursor.fetchall():
                remove_upload(s['file_path'])

            cursor.execute("""
                DELETE FROM assignment_submissions
                WHERE assignment_id IN (SELECT id FROM assignments WHERE class_id = %s)
            """, (class_id,))
            for table in ('assignments', 'materials', 'announcements', 'marks',
                          'attendance', 'payments', 'enrollments'):
                cursor.execute("DELETE FROM " + table + " WHERE class_id = %s", (class_id,))
            cursor.execute("DELETE FROM classes WHERE id = %s", (class_id,))
        conn.commit()
    finally:
        conn.close()
    return redirect(url_for('admin.manage_classes'))


@admin_bp.route('/admin/classes/<int:class_id>/roster', methods=['GET'])
def admin_class_roster(class_id):
    if not _admin_guard():
        return "Unauthorized", 403

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT c.id, c.subject, c.schedule, c.fee, c.join_code, c.teacher_id,
                       u.name AS teacher_name, u.email AS teacher_email
                FROM classes c JOIN users u ON c.teacher_id = u.id
                WHERE c.id = %s
            """, (class_id,))
            cls = cursor.fetchone()
            if not cls:
                return "Class not found", 404
            cls['fee'] = float(cls['fee'])

            cursor.execute("""
                SELECT u.id, u.name, u.email, sp.grade, e.joined_at
                FROM enrollments e
                JOIN users u ON e.student_id = u.id
                LEFT JOIN student_profiles sp ON sp.user_id = u.id
                WHERE e.class_id = %s
                ORDER BY u.name
            """, (class_id,))
            roster = cursor.fetchall()

            cursor.execute("""
                SELECT u.id, u.name, u.email
                FROM users u
                WHERE u.role = 'student'
                  AND u.id NOT IN (SELECT student_id FROM enrollments WHERE class_id = %s)
                ORDER BY u.name
            """, (class_id,))
            available_students = cursor.fetchall()

            cursor.execute("SELECT id, name, email FROM users WHERE role = 'teacher' ORDER BY name")
            teachers = cursor.fetchall()

            return render_template('admin_class_roster.html', cls=cls, roster=roster,
                                   available_students=available_students, teachers=teachers)
    finally:
        conn.close()


@admin_bp.route('/admin/classes/<int:class_id>/enroll', methods=['POST'])
def admin_enroll_student(class_id):
    if not _admin_guard():
        return "Unauthorized", 403

    student_id = request.form.get('student_id')
    if not student_id:
        return "Select a student", 400

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM classes WHERE id = %s", (class_id,))
            if not cursor.fetchone():
                return "Class not found", 404
            cursor.execute("SELECT id FROM users WHERE id = %s AND role = 'student'", (student_id,))
            if not cursor.fetchone():
                return "Student not found", 404
            cursor.execute("SELECT id FROM enrollments WHERE class_id = %s AND student_id = %s",
                           (class_id, student_id))
            if not cursor.fetchone():
                cursor.execute("INSERT INTO enrollments (class_id, student_id) VALUES (%s, %s)",
                               (class_id, student_id))
        conn.commit()
    finally:
        conn.close()
    return redirect(url_for('admin.admin_class_roster', class_id=class_id))


@admin_bp.route('/admin/classes/<int:class_id>/unenroll/<int:student_id>', methods=['POST'])
def admin_unenroll_student(class_id, student_id):
    if not _admin_guard():
        return "Unauthorized", 403

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM enrollments WHERE class_id = %s AND student_id = %s",
                           (class_id, student_id))
        conn.commit()
    finally:
        conn.close()
    return redirect(url_for('admin.admin_class_roster', class_id=class_id))


@admin_bp.route('/admin/exams', methods=['GET'])
def manage_exams():
    if not _admin_guard():
        return "Unauthorized", 403

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Query all distinct exams across all classes
            cursor.execute("""
                SELECT 
                    m.class_id, 
                    m.test_name, 
                    c.subject, 
                    c.schedule,
                    u.id as teacher_id, 
                    u.name as teacher_name, 
                    MAX(m.max_marks) as max_marks, 
                    MIN(m.date_recorded) as date_recorded,
                    COUNT(m.student_id) as student_count,
                    AVG(m.marks_obtained / m.max_marks * 100) as avg_pct
                FROM marks m
                JOIN classes c ON m.class_id = c.id
                JOIN users u ON c.teacher_id = u.id
                GROUP BY m.class_id, m.test_name, c.subject, c.schedule, u.id, u.name
                ORDER BY MIN(m.date_recorded) DESC, m.test_name ASC
            """)
            exams = cursor.fetchall()

            # Teachers for filter
            cursor.execute("SELECT id, name FROM users WHERE role = 'teacher' ORDER BY name")
            teachers = cursor.fetchall()

            # Classes for filter
            cursor.execute("""
                SELECT c.id, c.subject, c.schedule, c.teacher_id, u.name as teacher_name 
                FROM classes c 
                LEFT JOIN users u ON c.teacher_id = u.id 
                ORDER BY c.subject
            """)
            classes = cursor.fetchall()

            # Global summary stats
            cursor.execute("SELECT COUNT(*) as cnt, AVG(marks_obtained / max_marks * 100) as avg_score FROM marks")
            summary = cursor.fetchone()
            total_records_count = summary['cnt'] if summary else 0
            overall_avg_pct = float(summary['avg_score'] or 0.0) if summary else 0.0

            return render_template('admin_exams.html',
                                   exams=exams,
                                   teachers=teachers,
                                   classes=classes,
                                   total_records_count=total_records_count,
                                   overall_avg_pct=overall_avg_pct)
    finally:
        conn.close()


@admin_bp.route('/admin/exams/<int:class_id>/<path:test_name>/edit', methods=['GET', 'POST'])
def edit_exam(class_id, test_name):
    if not _admin_guard():
        return "Unauthorized", 403

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Fetch class details & instructor
            cursor.execute("""
                SELECT c.id, c.subject, c.schedule, c.teacher_id, u.name as teacher_name, u.email as teacher_email
                FROM classes c
                JOIN users u ON c.teacher_id = u.id
                WHERE c.id = %s
            """, (class_id,))
            class_row = cursor.fetchone()
            if not class_row:
                return "Class not found", 404

            class_info = {
                'id': class_row['id'],
                'subject': class_row['subject'],
                'schedule': class_row['schedule']
            }
            teacher = {
                'id': class_row['teacher_id'],
                'name': class_row['teacher_name'],
                'email': class_row['teacher_email']
            }

            if request.method == 'GET':
                # Fetch exam metadata
                cursor.execute("""
                    SELECT MAX(max_marks) as max_marks, MIN(date_recorded) as date_recorded
                    FROM marks
                    WHERE class_id = %s AND test_name = %s
                """, (class_id, test_name))
                meta = cursor.fetchone()
                if not meta or meta['max_marks'] is None:
                    flash(f"Assessment '{test_name}' not found for this class.", "error")
                    return redirect(url_for('admin.manage_exams'))

                max_marks = float(meta['max_marks'] or 100.0)
                date_recorded = str(meta['date_recorded']) if meta['date_recorded'] else ''

                # Fetch enrolled students
                cursor.execute("""
                    SELECT u.id, u.name, u.email
                    FROM enrollments e
                    JOIN users u ON e.student_id = u.id
                    WHERE e.class_id = %s
                    ORDER BY u.name
                """, (class_id,))
                enrolled_students = cursor.fetchall()

                # Fetch existing marks for this exam
                cursor.execute("""
                    SELECT id, student_id, marks_obtained
                    FROM marks
                    WHERE class_id = %s AND test_name = %s
                """, (class_id, test_name))
                existing_marks = cursor.fetchall()
                marks_by_student = {m['student_id']: m for m in existing_marks}

                roster = []
                enrolled_ids = set()
                for s in enrolled_students:
                    enrolled_ids.add(s['id'])
                    m = marks_by_student.get(s['id'])
                    roster.append({
                        'student_id': s['id'],
                        'student_name': s['name'],
                        'student_email': s['email'],
                        'mark_id': m['id'] if m else None,
                        'marks_obtained': float(m['marks_obtained']) if m else None,
                        'has_mark': m is not None
                    })

                # Check if any unenrolled students still hold marks for this test
                for m in existing_marks:
                    if m['student_id'] not in enrolled_ids:
                        cursor.execute("SELECT name, email FROM users WHERE id = %s", (m['student_id'],))
                        u = cursor.fetchone()
                        roster.append({
                            'student_id': m['student_id'],
                            'student_name': (u['name'] + ' (Unenrolled)') if u else f"Learner #{m['student_id']}",
                            'student_email': u['email'] if u else '',
                            'mark_id': m['id'],
                            'marks_obtained': float(m['marks_obtained']),
                            'has_mark': True
                        })

                return render_template('admin_exam_edit.html',
                                       class_info=class_info,
                                       teacher=teacher,
                                       test_name=test_name,
                                       max_marks=max_marks,
                                       date_recorded=date_recorded,
                                       roster=roster)

            # POST: Save updates
            data = request.form
            new_test_name = (data.get('new_test_name') or '').strip()
            date_recorded = (data.get('date_recorded') or '').strip()
            max_marks_str = (data.get('max_marks') or '100').strip()

            if not new_test_name:
                flash('Assessment title cannot be empty.', 'error')
                return redirect(url_for('admin.edit_exam', class_id=class_id, test_name=test_name))

            try:
                max_marks = float(max_marks_str)
                if max_marks <= 0:
                    raise ValueError()
            except ValueError:
                flash('Maximum marks must be a positive number.', 'error')
                return redirect(url_for('admin.edit_exam', class_id=class_id, test_name=test_name))

            # Fetch enrolled & existing student IDs
            cursor.execute("SELECT student_id FROM enrollments WHERE class_id = %s", (class_id,))
            all_sids = {r['student_id'] for r in cursor.fetchall()}
            cursor.execute("SELECT student_id FROM marks WHERE class_id = %s AND test_name = %s", (class_id, test_name))
            all_sids.update(r['student_id'] for r in cursor.fetchall())

            # Validate all scores first
            student_scores = {}
            for sid in all_sids:
                is_delete = data.get(f'delete_{sid}')
                mark_val_str = (data.get(f'mark_{sid}') or '').strip()

                if is_delete or mark_val_str == '':
                    student_scores[sid] = None
                else:
                    try:
                        m_val = float(mark_val_str)
                        if m_val < 0 or m_val > max_marks:
                            cursor.execute("SELECT name FROM users WHERE id = %s", (sid,))
                            s_name = (cursor.fetchone() or {}).get('name', f"Student #{sid}")
                            flash(f"Score for {s_name} ({m_val}) exceeds maximum marks ({max_marks}).", 'error')
                            return redirect(url_for('admin.edit_exam', class_id=class_id, test_name=test_name))
                        student_scores[sid] = m_val
                    except ValueError:
                        flash(f"Invalid score format entered for learner #{sid}.", 'error')
                        return redirect(url_for('admin.edit_exam', class_id=class_id, test_name=test_name))

            # Apply updates / deletions / insertions
            for sid, m_val in student_scores.items():
                if m_val is None:
                    cursor.execute("DELETE FROM marks WHERE class_id = %s AND test_name = %s AND student_id = %s",
                                   (class_id, test_name, sid))
                else:
                    cursor.execute("SELECT id FROM marks WHERE class_id = %s AND test_name = %s AND student_id = %s",
                                   (class_id, test_name, sid))
                    row = cursor.fetchone()
                    if row:
                        cursor.execute("""
                            UPDATE marks
                            SET marks_obtained = %s, max_marks = %s, date_recorded = %s, test_name = %s
                            WHERE id = %s
                        """, (m_val, max_marks, date_recorded, new_test_name, row['id']))
                    else:
                        cursor.execute("""
                            INSERT INTO marks (class_id, student_id, test_name, marks_obtained, max_marks, date_recorded)
                            VALUES (%s, %s, %s, %s, %s, %s)
                        """, (class_id, sid, new_test_name, m_val, max_marks, date_recorded))

            # If test_name changed, rename any remaining unedited records
            if new_test_name != test_name:
                cursor.execute("UPDATE marks SET test_name = %s WHERE class_id = %s AND test_name = %s",
                               (new_test_name, class_id, test_name))

            conn.commit()
            flash(f"Assessment '{new_test_name}' and student scores successfully updated!", 'success')
            return redirect(url_for('admin.manage_exams'))
    finally:
        conn.close()


@admin_bp.route('/admin/exams/<int:class_id>/<path:test_name>/delete', methods=['POST'])
def delete_exam(class_id, test_name):
    if not _admin_guard():
        return "Unauthorized", 403

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM marks WHERE class_id = %s AND test_name = %s", (class_id, test_name))
            conn.commit()
            flash(f"Assessment '{test_name}' and all associated student scores have been permanently deleted.", 'success')
            return redirect(url_for('admin.manage_exams'))
    finally:
        conn.close()
