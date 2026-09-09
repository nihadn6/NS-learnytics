from flask import Blueprint, request, jsonify, session, render_template, redirect, url_for, flash
from database.db import get_db_connection

announcements_bp = Blueprint('announcements', __name__)

@announcements_bp.route('/announcements', methods=['GET'])
def feed():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    user_id = session['user_id']
    role = session['role']
    conn = get_db_connection()

    try:
        with conn.cursor() as cursor:
            if role == 'teacher':
                cursor.execute("SELECT id, subject FROM classes WHERE teacher_id = %s ORDER BY subject", (user_id,))
                classes = cursor.fetchall()
                selected_class_id = request.args.get('class_id')

                query = """
                    SELECT a.*, c.subject 
                    FROM announcements a
                    JOIN classes c ON a.class_id = c.id
                    WHERE a.teacher_id = %s
                """
                params = [user_id]
                if selected_class_id:
                    query += " AND a.class_id = %s"
                    params.append(selected_class_id)
                query += " ORDER BY a.created_at DESC"

                cursor.execute(query, tuple(params))
                announcements = cursor.fetchall()

                return render_template('announcements.html', 
                                       classes=classes, 
                                       selected_class_id=int(selected_class_id) if selected_class_id else None,
                                       announcements=announcements)

            elif role in ('student', 'parent'):
                target_student_id = user_id
                if role == 'parent':
                    target_student_id = session.get('selected_student_id')
                    if not target_student_id:
                        cursor.execute("SELECT student_id FROM parent_student_links WHERE parent_id = %s AND status = 'approved' LIMIT 1", (user_id,))
                        row = cursor.fetchone()
                        target_student_id = row['student_id'] if row else None

                if not target_student_id:
                    return render_template('announcements.html', announcements=[])

                audience_filter = "('all', 'students_only')" if role == 'student' else "('all', 'parents_only')"

                cursor.execute(f"""
                    SELECT a.*, c.subject, u.name as teacher_name
                    FROM announcements a
                    JOIN classes c ON a.class_id = c.id
                    JOIN users u ON a.teacher_id = u.id
                    JOIN enrollments e ON e.class_id = c.id
                    WHERE e.student_id = %s AND a.target_audience IN {audience_filter}
                    ORDER BY a.created_at DESC
                """, (target_student_id,))
                announcements = cursor.fetchall()

                return render_template('announcements.html', announcements=announcements)

            else:
                # Moderators / Superadmins can see all announcements
                cursor.execute("""
                    SELECT a.*, c.subject, u.name as teacher_name
                    FROM announcements a
                    JOIN classes c ON a.class_id = c.id
                    JOIN users u ON a.teacher_id = u.id
                    ORDER BY a.created_at DESC LIMIT 50
                """)
                announcements = cursor.fetchall()
                return render_template('announcements.html', announcements=announcements)
    finally:
        conn.close()


@announcements_bp.route('/announcements/create', methods=['POST'])
def create_announcement():
    if session.get('role') != 'teacher':
        return "Unauthorized", 403

    class_id = request.form.get('class_id')
    title = request.form.get('title')
    content = request.form.get('content')
    target_audience = request.form.get('target_audience', 'all')

    if not class_id or not title or not content:
        flash('Class, Title, and Content are required.', 'error')
        return redirect(url_for('announcements.feed'))

    teacher_id = session['user_id']
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Verify ownership
            cursor.execute("SELECT subject FROM classes WHERE id = %s AND teacher_id = %s", (class_id, teacher_id))
            class_row = cursor.fetchone()
            if not class_row:
                return "Unauthorized class", 403

            cursor.execute("""
                INSERT INTO announcements (class_id, teacher_id, title, content, target_audience)
                VALUES (%s, %s, %s, %s, %s)
            """, (class_id, teacher_id, title, content, target_audience))
            conn.commit()

            # Dispatch Notifications
            # 1. Students
            if target_audience in ('all', 'students_only'):
                cursor.execute("SELECT student_id FROM enrollments WHERE class_id = %s", (class_id,))
                students = cursor.fetchall()
                for s in students:
                    cursor.execute("""
                        INSERT INTO notifications (user_id, message, type)
                        VALUES (%s, %s, 'announcement')
                    """, (s['student_id'], f"Broadcast Announcement in {class_row['subject']}: '{title}'"))

            # 2. Parents
            if target_audience in ('all', 'parents_only'):
                cursor.execute("""
                    SELECT DISTINCT psl.parent_id
                    FROM parent_student_links psl
                    JOIN enrollments e ON psl.student_id = e.student_id
                    WHERE e.class_id = %s AND psl.status = 'approved'
                """, (class_id,))
                parents = cursor.fetchall()
                for p in parents:
                    cursor.execute("""
                        INSERT INTO notifications (user_id, message, type)
                        VALUES (%s, %s, 'announcement')
                    """, (p['parent_id'], f"Announcement for {class_row['subject']}: '{title}'"))

            conn.commit()
            flash('Broadcast Announcement published successfully!', 'success')
    finally:
        conn.close()

    return redirect(url_for('announcements.feed', class_id=class_id))
