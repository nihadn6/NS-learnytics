from flask import Blueprint, request, jsonify, session, render_template, redirect, url_for, flash, send_from_directory
from database.db import get_db_connection
from werkzeug.utils import secure_filename
import os
import datetime

lms_bp = Blueprint('lms', __name__)

# Use /tmp for Vercel (read-only filesystem) or static/uploads locally
UPLOAD_FOLDER = '/tmp/lms_uploads' if os.environ.get('VERCEL') else os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'uploads', 'lms')

# Roles allowed to manage LMS content (teachers: own classes only, superadmin: every class)
STAFF_ROLES = ('teacher', 'superadmin')


def ensure_upload_folder():
    """Create upload folder lazily — only when actually needed."""
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Helper function to check allowed extensions
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'doc', 'docx', 'ppt', 'pptx', 'zip', 'txt'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def save_upload(file):
    """Validate and store an uploaded file. Returns (stored_name, error_message)."""
    if not file or not file.filename:
        return None, None
    if not allowed_file(file.filename):
        return None, 'File format not allowed.'
    ensure_upload_folder()
    fname = secure_filename(file.filename)
    stored = datetime.datetime.now().strftime('%Y%m%d%H%M%S_') + fname
    file.save(os.path.join(UPLOAD_FOLDER, stored))
    return stored, None


def remove_upload(stored_name):
    if not stored_name:
        return
    try:
        os.remove(os.path.join(UPLOAD_FOLDER, stored_name))
    except OSError:
        pass


def class_owner_if_manageable(cursor, class_id):
    """Return the owning teacher_id of a class if the current user may manage it
    (the owning teacher, or a superadmin for any class); otherwise None."""
    role = session.get('role')
    if role == 'teacher':
        cursor.execute("SELECT teacher_id FROM classes WHERE id = %s AND teacher_id = %s",
                       (class_id, session['user_id']))
    elif role == 'superadmin':
        cursor.execute("SELECT teacher_id FROM classes WHERE id = %s", (class_id,))
    else:
        return None
    row = cursor.fetchone()
    return row['teacher_id'] if row else None


def build_overview(cursor, teacher_filter=None):
    """Per-class LMS activity summary used by the admin oversight table."""
    query = """
        SELECT c.id, c.subject, u.name AS teacher_name,
               (SELECT COUNT(*) FROM materials m WHERE m.class_id = c.id) AS materials_count,
               (SELECT COUNT(*) FROM assignments a WHERE a.class_id = c.id) AS assignments_count,
               (SELECT COUNT(*) FROM assignment_submissions s
                  JOIN assignments a ON s.assignment_id = a.id WHERE a.class_id = c.id) AS submitted_count,
               (SELECT COUNT(*) FROM assignment_submissions s
                  JOIN assignments a ON s.assignment_id = a.id
                  WHERE a.class_id = c.id AND s.status = 'graded') AS graded_count,
               (SELECT COUNT(*) FROM assignment_submissions s
                  JOIN assignments a ON s.assignment_id = a.id
                  WHERE a.class_id = c.id AND s.status = 'submitted'
                    AND s.submitted_at < DATE_SUB(NOW(), INTERVAL 7 DAY)) AS overdue_ungraded
        FROM classes c
        JOIN users u ON c.teacher_id = u.id
    """
    params = []
    if teacher_filter:
        query += " WHERE c.teacher_id = %s"
        params.append(int(teacher_filter))
    query += " ORDER BY c.subject, u.name"
    cursor.execute(query, tuple(params))
    rows = cursor.fetchall()
    for r in rows:
        submitted = r['submitted_count'] or 0
        r['graded_pct'] = int(round((r['graded_count'] or 0) * 100.0 / submitted)) if submitted else None
    return rows


@lms_bp.route('/lms', methods=['GET'])
def index():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    user_id = session['user_id']
    role = session['role']
    conn = get_db_connection()

    try:
        with conn.cursor() as cursor:
            if role in STAFF_ROLES:
                is_admin = role == 'superadmin'
                teacher_filter = (request.args.get('teacher_id') or '').strip()
                teacher_filter = teacher_filter if teacher_filter.isdigit() else ''
                teachers = []
                overview = []

                if is_admin:
                    query = """
                        SELECT c.id, c.subject, c.teacher_id, u.name AS teacher_name
                        FROM classes c JOIN users u ON c.teacher_id = u.id
                    """
                    params = []
                    if teacher_filter:
                        query += " WHERE c.teacher_id = %s"
                        params.append(int(teacher_filter))
                    query += " ORDER BY c.subject, u.name"
                    cursor.execute(query, tuple(params))
                    classes = cursor.fetchall()
                    cursor.execute("SELECT id, name FROM users WHERE role = 'teacher' ORDER BY name")
                    teachers = cursor.fetchall()
                    overview = build_overview(cursor, teacher_filter or None)
                else:
                    cursor.execute("SELECT id, subject FROM classes WHERE teacher_id = %s ORDER BY subject", (user_id,))
                    classes = cursor.fetchall()

                allowed_ids = [c['id'] for c in classes]
                requested = (request.args.get('class_id') or '').strip()
                if requested.isdigit() and int(requested) in allowed_ids:
                    selected_class_id = int(requested)
                else:
                    selected_class_id = classes[0]['id'] if classes else None

                materials = []
                assignments = []
                submissions_map = {}

                if selected_class_id:
                    cursor.execute("""
                        SELECT m.*, c.subject, u.name AS teacher_name
                        FROM materials m
                        JOIN classes c ON m.class_id = c.id
                        JOIN users u ON m.teacher_id = u.id
                        WHERE m.class_id = %s
                        ORDER BY m.created_at DESC
                    """, (selected_class_id,))
                    materials = cursor.fetchall()

                    cursor.execute("""
                        SELECT a.*, c.subject
                        FROM assignments a
                        JOIN classes c ON a.class_id = c.id
                        WHERE a.class_id = %s
                        ORDER BY a.created_at DESC
                    """, (selected_class_id,))
                    assignments = cursor.fetchall()

                    # Fetch submission counts per assignment
                    for a in assignments:
                        cursor.execute("""
                            SELECT
                                COUNT(*) as total_sub,
                                SUM(CASE WHEN status = 'graded' THEN 1 ELSE 0 END) as graded_sub
                            FROM assignment_submissions
                            WHERE assignment_id = %s
                        """, (a['id'],))
                        sub_row = cursor.fetchone()
                        cursor.execute("SELECT COUNT(*) AS n FROM enrollments WHERE class_id = %s",
                                       (selected_class_id,))
                        sub_row['enrolled'] = cursor.fetchone()['n']
                        submissions_map[a['id']] = sub_row

                return render_template('lms_teacher.html',
                                       classes=classes,
                                       selected_class_id=selected_class_id,
                                       materials=materials,
                                       assignments=assignments,
                                       submissions_map=submissions_map,
                                       is_admin=is_admin,
                                       teachers=teachers,
                                       teacher_filter=teacher_filter,
                                       overview=overview,
                                       now=datetime.datetime.now())

            elif role in ('student', 'parent'):
                target_student_id = user_id
                if role == 'parent':
                    target_student_id = session.get('selected_student_id')
                    if not target_student_id:
                        # Pick first approved student
                        cursor.execute("SELECT student_id FROM parent_student_links WHERE parent_id = %s AND status = 'approved' LIMIT 1", (user_id,))
                        row = cursor.fetchone()
                        target_student_id = row['student_id'] if row else None

                if not target_student_id:
                    flash('No student linked or selected.', 'warning')
                    return render_template('lms_student.html', materials=[], assignments=[], student_submissions={})

                # Fetch enrolled classes
                cursor.execute("""
                    SELECT c.id, c.subject, u.name as teacher_name 
                    FROM enrollments e 
                    JOIN classes c ON e.class_id = c.id 
                    JOIN users u ON c.teacher_id = u.id 
                    WHERE e.student_id = %s
                """, (target_student_id,))
                classes = cursor.fetchall()
                selected_class_id = request.args.get('class_id') or (classes[0]['id'] if classes else None)

                materials = []
                assignments = []
                student_submissions = {}

                if selected_class_id:
                    cursor.execute("SELECT m.*, u.name as teacher_name FROM materials m JOIN users u ON m.teacher_id = u.id WHERE m.class_id = %s ORDER BY m.created_at DESC", (selected_class_id,))
                    materials = cursor.fetchall()

                    cursor.execute("SELECT a.*, u.name as teacher_name FROM assignments a JOIN users u ON a.teacher_id = u.id WHERE a.class_id = %s ORDER BY a.due_date ASC", (selected_class_id,))
                    assignments = cursor.fetchall()

                    cursor.execute("""
                        SELECT sub.*, a.id as assignment_id 
                        FROM assignment_submissions sub
                        JOIN assignments a ON sub.assignment_id = a.id
                        WHERE sub.student_id = %s AND a.class_id = %s
                    """, (target_student_id, selected_class_id))
                    subs = cursor.fetchall()
                    for s in subs:
                        student_submissions[s['assignment_id']] = s

                return render_template('lms_student.html', 
                                       classes=classes, 
                                       selected_class_id=int(selected_class_id) if selected_class_id else None,
                                       materials=materials, 
                                       assignments=assignments,
                                       student_submissions=student_submissions,
                                       target_student_id=target_student_id)

            else:
                return "Unauthorized", 403
    finally:
        conn.close()

# --- MATERIAL ROUTES ---

@lms_bp.route('/lms/material/upload', methods=['POST'])
def upload_material():
    if session.get('role') not in STAFF_ROLES:
        return "Unauthorized", 403

    class_id = request.form.get('class_id')
    title = (request.form.get('title') or '').strip()
    description = request.form.get('description')
    file = request.files.get('file')

    if not class_id or not title:
        flash('Class and Title are required.', 'error')
        return redirect(url_for('lms.index'))

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Teachers may only upload to their own classes; superadmin to any class.
            owner_id = class_owner_if_manageable(cursor, class_id)
            if not owner_id:
                return "Unauthorized class", 403

            filename_saved, err = save_upload(file)
            if err:
                flash(err, 'error')
                return redirect(url_for('lms.index', class_id=class_id))

            # Material is attributed to the class's teacher, even when uploaded by an admin.
            cursor.execute("""
                INSERT INTO materials (class_id, teacher_id, title, description, file_path)
                VALUES (%s, %s, %s, %s, %s)
            """, (class_id, owner_id, title, description, filename_saved))
            conn.commit()
            flash('Study Material uploaded successfully!', 'success')
    finally:
        conn.close()

    return redirect(url_for('lms.index', class_id=class_id))


@lms_bp.route('/lms/material/delete/<int:material_id>', methods=['POST'])
def delete_material(material_id):
    if session.get('role') not in STAFF_ROLES:
        return "Unauthorized", 403

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT class_id, file_path FROM materials WHERE id = %s", (material_id,))
            row = cursor.fetchone()
            if row and class_owner_if_manageable(cursor, row['class_id']):
                remove_upload(row['file_path'])
                cursor.execute("DELETE FROM materials WHERE id = %s", (material_id,))
                conn.commit()
                flash('Material deleted successfully.', 'success')
                return redirect(url_for('lms.index', class_id=row['class_id']))
    finally:
        conn.close()

    return redirect(url_for('lms.index'))


# --- ASSIGNMENT ROUTES ---

@lms_bp.route('/lms/assignment/create', methods=['POST'])
def create_assignment():
    if session.get('role') not in STAFF_ROLES:
        return "Unauthorized", 403

    class_id = request.form.get('class_id')
    title = (request.form.get('title') or '').strip()
    description = request.form.get('description')
    due_date = request.form.get('due_date')
    max_points = request.form.get('max_points') or 100.0
    file = request.files.get('file')

    if not class_id or not title or not due_date:
        flash('Class, Title, and Due Date are required.', 'error')
        return redirect(url_for('lms.index'))

    try:
        max_points = float(max_points)
        if max_points <= 0:
            raise ValueError
    except ValueError:
        flash('Max Points must be a positive number.', 'error')
        return redirect(url_for('lms.index', class_id=class_id))

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            owner_id = class_owner_if_manageable(cursor, class_id)
            if not owner_id:
                return "Unauthorized class", 403

            filename_saved, err = save_upload(file)
            if err:
                flash(err, 'error')
                return redirect(url_for('lms.index', class_id=class_id))

            cursor.execute("""
                INSERT INTO assignments (class_id, teacher_id, title, description, due_date, max_points, attachment_path)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (class_id, owner_id, title, description, due_date, max_points, filename_saved))
            conn.commit()

            # Notify enrolled students
            cursor.execute("SELECT student_id FROM enrollments WHERE class_id = %s", (class_id,))
            students = cursor.fetchall()
            for s in students:
                cursor.execute("""
                    INSERT INTO notifications (user_id, message, type)
                    VALUES (%s, %s, 'assignment')
                """, (s['student_id'], f"New Assignment posted: '{title}' due on {due_date}"))
            conn.commit()

            flash('Assignment published successfully!', 'success')
    finally:
        conn.close()

    return redirect(url_for('lms.index', class_id=class_id))


@lms_bp.route('/lms/assignment/<int:assignment_id>/edit', methods=['POST'])
def edit_assignment(assignment_id):
    if session.get('role') not in STAFF_ROLES:
        return "Unauthorized", 403

    title = (request.form.get('title') or '').strip()
    description = request.form.get('description')
    due_date = request.form.get('due_date')
    max_points = request.form.get('max_points') or 100.0
    file = request.files.get('file')

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT class_id, attachment_path FROM assignments WHERE id = %s", (assignment_id,))
            row = cursor.fetchone()
            if not row or not class_owner_if_manageable(cursor, row['class_id']):
                return "Assignment not found or unauthorized", 404
            class_id = row['class_id']

            if not title or not due_date:
                flash('Title and Due Date are required.', 'error')
                return redirect(url_for('lms.index', class_id=class_id))
            try:
                max_points = float(max_points)
                if max_points <= 0:
                    raise ValueError
            except ValueError:
                flash('Max Points must be a positive number.', 'error')
                return redirect(url_for('lms.index', class_id=class_id))

            new_attachment, err = save_upload(file)
            if err:
                flash(err, 'error')
                return redirect(url_for('lms.index', class_id=class_id))

            if new_attachment:
                remove_upload(row['attachment_path'])
                cursor.execute("""
                    UPDATE assignments
                    SET title = %s, description = %s, due_date = %s, max_points = %s, attachment_path = %s
                    WHERE id = %s
                """, (title, description, due_date, max_points, new_attachment, assignment_id))
            else:
                cursor.execute("""
                    UPDATE assignments
                    SET title = %s, description = %s, due_date = %s, max_points = %s
                    WHERE id = %s
                """, (title, description, due_date, max_points, assignment_id))
            conn.commit()
            flash('Assignment updated successfully!', 'success')
            return redirect(url_for('lms.index', class_id=class_id))
    finally:
        conn.close()


@lms_bp.route('/lms/assignment/<int:assignment_id>/delete', methods=['POST'])
def delete_assignment(assignment_id):
    if session.get('role') not in STAFF_ROLES:
        return "Unauthorized", 403

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT class_id, attachment_path FROM assignments WHERE id = %s", (assignment_id,))
            row = cursor.fetchone()
            if not row or not class_owner_if_manageable(cursor, row['class_id']):
                return "Assignment not found or unauthorized", 404

            cursor.execute("SELECT file_path FROM assignment_submissions WHERE assignment_id = %s", (assignment_id,))
            for sub in cursor.fetchall():
                remove_upload(sub['file_path'])
            remove_upload(row['attachment_path'])

            # Delete children explicitly: MyISAM tables (e.g. MySQL 5.1 WAMP) do not enforce ON DELETE CASCADE
            cursor.execute("DELETE FROM assignment_submissions WHERE assignment_id = %s", (assignment_id,))
            cursor.execute("DELETE FROM assignments WHERE id = %s", (assignment_id,))
            conn.commit()
            flash('Assignment and its submissions were deleted.', 'success')
            return redirect(url_for('lms.index', class_id=row['class_id']))
    finally:
        conn.close()


@lms_bp.route('/lms/assignment/<int:assignment_id>/submissions', methods=['GET'])
def view_submissions(assignment_id):
    if session.get('role') not in STAFF_ROLES:
        return "Unauthorized", 403

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT a.*, c.subject, u.name AS teacher_name
                FROM assignments a 
                JOIN classes c ON a.class_id = c.id 
                JOIN users u ON c.teacher_id = u.id
                WHERE a.id = %s
            """, (assignment_id,))
            assignment = cursor.fetchone()
            if not assignment or not class_owner_if_manageable(cursor, assignment['class_id']):
                return "Assignment not found or unauthorized", 404

            cursor.execute("""
                SELECT u.id as student_id, u.name as student_name, u.email,
                       sub.id as submission_id, sub.submission_text, sub.file_path,
                       sub.submitted_at, sub.marks_obtained, sub.feedback, sub.status
                FROM enrollments e
                JOIN users u ON e.student_id = u.id
                LEFT JOIN assignment_submissions sub ON sub.assignment_id = %s AND sub.student_id = u.id
                WHERE e.class_id = %s
                ORDER BY u.name
            """, (assignment_id, assignment['class_id']))
            roster = cursor.fetchall()

            counts = {
                'total': len(roster),
                'submitted': sum(1 for r in roster if r['submission_id']),
                'graded': sum(1 for r in roster if r['status'] == 'graded'),
                'pending': sum(1 for r in roster if not r['submission_id']),
            }

            return render_template('lms_submissions.html', assignment=assignment, roster=roster, counts=counts)
    finally:
        conn.close()


@lms_bp.route('/lms/assignment/submit', methods=['POST'])
def submit_assignment():
    if session.get('role') != 'student':
        return "Unauthorized", 403

    assignment_id = request.form.get('assignment_id')
    submission_text = request.form.get('submission_text')
    file = request.files.get('file')

    filename_saved = None
    if file and file.filename:
        if allowed_file(file.filename):
            ensure_upload_folder()
            fname = secure_filename(file.filename)
            timestamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S_')
            filename_saved = timestamp + fname
            file.save(os.path.join(UPLOAD_FOLDER, filename_saved))

    student_id = session['user_id']
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO assignment_submissions (assignment_id, student_id, submission_text, file_path)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE 
                    submission_text = VALUES(submission_text),
                    file_path = IF(VALUES(file_path) IS NOT NULL, VALUES(file_path), file_path),
                    submitted_at = CURRENT_TIMESTAMP,
                    status = 'submitted'
            """, (assignment_id, student_id, submission_text, filename_saved))
            conn.commit()

            cursor.execute("SELECT class_id FROM assignments WHERE id = %s", (assignment_id,))
            assign_row = cursor.fetchone()
            flash('Assignment submitted successfully!', 'success')
            return redirect(url_for('lms.index', class_id=assign_row['class_id'] if assign_row else None))
    finally:
        conn.close()


@lms_bp.route('/lms/submission/<int:submission_id>/grade', methods=['POST'])
def grade_submission(submission_id):
    if session.get('role') not in STAFF_ROLES:
        return "Unauthorized", 403

    marks_obtained = request.form.get('marks_obtained')
    feedback = request.form.get('feedback')

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT sub.assignment_id, sub.student_id, a.title as assign_title,
                       a.class_id, a.max_points
                FROM assignment_submissions sub
                JOIN assignments a ON sub.assignment_id = a.id
                WHERE sub.id = %s
            """, (submission_id,))
            row = cursor.fetchone()
            if not row or not class_owner_if_manageable(cursor, row['class_id']):
                return "Submission not found or unauthorized", 404

            try:
                marks_val = float(marks_obtained)
                if marks_val < 0 or marks_val > float(row['max_points']):
                    raise ValueError
            except (TypeError, ValueError):
                flash(f"Marks must be a number between 0 and {row['max_points']}.", 'error')
                return redirect(url_for('lms.view_submissions', assignment_id=row['assignment_id']))

            cursor.execute("""
                UPDATE assignment_submissions 
                SET marks_obtained = %s, feedback = %s, status = 'graded'
                WHERE id = %s
            """, (marks_val, feedback, submission_id))

            # Send notification to student
            cursor.execute("""
                INSERT INTO notifications (user_id, message, type)
                VALUES (%s, %s, 'grade')
            """, (row['student_id'], f"Your assignment '{row['assign_title']}' has been graded: {marks_val:g} marks."))
            conn.commit()

            flash('Grade and feedback saved successfully!', 'success')
            return redirect(url_for('lms.view_submissions', assignment_id=row['assignment_id']))
    finally:
        conn.close()


@lms_bp.route('/lms/download/<filename>', methods=['GET'])
def download_file(filename):
    if 'user_id' not in session:
        return "Unauthorized", 403
    return send_from_directory(UPLOAD_FOLDER, filename, as_attachment=True)
