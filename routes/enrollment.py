from flask import Blueprint, request, jsonify, session, render_template, redirect, url_for, flash
from database.db import get_db_connection

enrollment_bp = Blueprint('enrollment', __name__)

@enrollment_bp.route('/enroll', methods=['GET', 'POST'])
def join_class():
    if session.get('role') != 'student':
        return "Unauthorized", 403
        
    if request.method == 'GET':
        return render_template('join_class.html')
        
    join_code = (request.form.get('join_code') or '').strip().upper()
    if not join_code:
        return render_template('join_class.html', error="Join code is required")
        
    student_id = session['user_id']
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, subject FROM classes WHERE join_code = %s", (join_code,))
            class_row = cursor.fetchone()
            if not class_row:
                return render_template('join_class.html', error="Invalid join code. Please check and try again.")
                
            class_id = class_row['id']
            subject = class_row['subject']
            
            # Check if student is already actively enrolled
            cursor.execute("SELECT id FROM enrollments WHERE class_id = %s AND student_id = %s", (class_id, student_id))
            if cursor.fetchone():
                return render_template('join_class.html', error=f"You are already enrolled in '{subject}'.")
                
            # Check existing join request
            cursor.execute("SELECT id, status FROM class_join_requests WHERE class_id = %s AND student_id = %s", (class_id, student_id))
            existing_req = cursor.fetchone()
            
            if existing_req:
                if existing_req['status'] == 'pending':
                    return render_template('join_class.html', error=f"You already have a pending join request for '{subject}' awaiting approval.")
                elif existing_req['status'] == 'declined':
                    # Allow student to re-request after being declined
                    cursor.execute("""
                        UPDATE class_join_requests 
                        SET status = 'pending', requested_at = CURRENT_TIMESTAMP, actioned_at = NULL, actioned_by = NULL 
                        WHERE id = %s
                    """, (existing_req['id'],))
                    conn.commit()
                    flash(f"Your join request for '{subject}' has been re-submitted for approval.", 'success')
                    return redirect(url_for('classes.view_classes'))
                elif existing_req['status'] == 'approved':
                    cursor.execute("INSERT IGNORE INTO enrollments (class_id, student_id) VALUES (%s, %s)", (class_id, student_id))
                    conn.commit()
                    flash(f"You are now enrolled in '{subject}'.", 'success')
                    return redirect(url_for('classes.view_classes'))
            else:
                cursor.execute("""
                    INSERT INTO class_join_requests (class_id, student_id, status)
                    VALUES (%s, %s, 'pending')
                """, (class_id, student_id))
                conn.commit()
                flash(f"Join request for '{subject}' submitted successfully! Awaiting teacher or admin approval.", 'success')
                return redirect(url_for('classes.view_classes'))
    except Exception as e:
        return render_template('join_class.html', error=str(e))
    finally:
        conn.close()


@enrollment_bp.route('/classes/requests/<int:request_id>/<string:action>', methods=['POST'])
def manage_join_request(request_id, action):
    role = session.get('role')
    user_id = session.get('user_id')
    
    if role not in ('teacher', 'superadmin', 'moderator'):
        return "Unauthorized", 403
        
    action = action.lower()
    if action not in ('accept', 'approve', 'decline', 'reject'):
        return "Invalid action", 400

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT r.id, r.class_id, r.student_id, r.status, c.teacher_id, c.subject, u.name as student_name
                FROM class_join_requests r
                JOIN classes c ON r.class_id = c.id
                JOIN users u ON r.student_id = u.id
                WHERE r.id = %s
            """, (request_id,))
            req = cursor.fetchone()
            
            if not req:
                return "Request not found", 404

            # Permission check: Teachers can only accept/decline for their own classes
            if role == 'teacher' and req['teacher_id'] != user_id:
                return "Unauthorized for this class", 403

            if action in ('accept', 'approve'):
                # Add to enrollments table
                cursor.execute("INSERT IGNORE INTO enrollments (class_id, student_id) VALUES (%s, %s)", 
                               (req['class_id'], req['student_id']))
                cursor.execute("""
                    UPDATE class_join_requests 
                    SET status = 'approved', actioned_at = CURRENT_TIMESTAMP, actioned_by = %s 
                    WHERE id = %s
                """, (user_id, request_id))
                conn.commit()
                flash(f"Approved {req['student_name']}'s request to join '{req['subject']}'.", 'success')
            else:
                cursor.execute("""
                    UPDATE class_join_requests 
                    SET status = 'declined', actioned_at = CURRENT_TIMESTAMP, actioned_by = %s 
                    WHERE id = %s
                """, (user_id, request_id))
                conn.commit()
                flash(f"Declined {req['student_name']}'s join request for '{req['subject']}'.", 'warning')
                
        # Redirect back to where the request came from
        next_url = request.form.get('next') or request.referrer
        if next_url:
            return redirect(next_url)
        if role == 'teacher':
            return redirect(url_for('enrollment.teacher_class_requests'))
        return redirect(url_for('admin.view_class_requests'))
    finally:
        conn.close()


@enrollment_bp.route('/teacher/class-requests', methods=['GET'])
def teacher_class_requests():
    if session.get('role') != 'teacher':
        return "Unauthorized", 403
        
    teacher_id = session['user_id']
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Pending requests for this teacher's classes
            cursor.execute("""
                SELECT r.id as request_id, r.requested_at, c.id as class_id, c.subject, c.schedule,
                       u.id as student_id, u.name as student_name, u.email as student_email, sp.grade
                FROM class_join_requests r
                JOIN classes c ON r.class_id = c.id
                JOIN users u ON r.student_id = u.id
                LEFT JOIN student_profiles sp ON sp.user_id = u.id
                WHERE c.teacher_id = %s AND r.status = 'pending'
                ORDER BY r.requested_at ASC
            """, (teacher_id,))
            pending_requests = cursor.fetchall()
            
            # Recent actioned requests history
            cursor.execute("""
                SELECT r.id as request_id, r.requested_at, r.actioned_at, r.status, c.subject,
                       u.name as student_name, u.email as student_email, sp.grade,
                       act.name as actioned_by_name
                FROM class_join_requests r
                JOIN classes c ON r.class_id = c.id
                JOIN users u ON r.student_id = u.id
                LEFT JOIN student_profiles sp ON sp.user_id = u.id
                LEFT JOIN users act ON r.actioned_by = act.id
                WHERE c.teacher_id = %s AND r.status != 'pending'
                ORDER BY r.actioned_at DESC LIMIT 30
            """, (teacher_id,))
            history = cursor.fetchall()
            
            return render_template('teacher_class_requests.html', 
                                   pending_requests=pending_requests, 
                                   history=history)
    finally:
        conn.close()


@enrollment_bp.route('/api/classes/<int:class_id>/students', methods=['GET'])
def api_class_students(class_id):
    # Allow teacher (if owner), moderator, superadmin to fetch enrolled students for AJAX
    if session.get('role') not in ('teacher', 'moderator', 'superadmin'):
        return jsonify({'error': 'Unauthorized'}), 403

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # If teacher, ensure they own the class
            if session.get('role') == 'teacher':
                cursor.execute("SELECT 1 FROM classes WHERE id = %s AND teacher_id = %s", (class_id, session['user_id']))
                if not cursor.fetchone():
                    return jsonify({'error': 'Unauthorized for this class'}), 403

            # also fetch class info (fee) to allow client to prefill amounts
            cursor.execute("SELECT fee FROM classes WHERE id = %s", (class_id,))
            class_info = cursor.fetchone() or {}
            cursor.execute("SELECT u.id, u.name, u.email FROM enrollments e JOIN users u ON e.student_id = u.id WHERE e.class_id = %s ORDER BY u.name", (class_id,))
            rows = cursor.fetchall()
            # return a JSON-friendly list
            students = [{'id': r['id'], 'name': r['name'], 'email': r.get('email')} for r in rows]
            return jsonify({'students': students, 'fee': class_info.get('fee')})
    finally:
        conn.close()

@enrollment_bp.route('/classes/<int:class_id>/students', methods=['GET'])
def view_students(class_id):
    if session.get('role') != 'teacher':
        return "Unauthorized", 403
        
    teacher_id = session['user_id']
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT subject FROM classes WHERE id = %s AND teacher_id = %s", (class_id, teacher_id))
            class_info = cursor.fetchone()
            if not class_info:
                return "Class not found", 404
                
            cursor.execute("""
                SELECT u.id, u.name, u.email, s.grade, e.joined_at 
                FROM enrollments e
                JOIN users u ON e.student_id = u.id
                JOIN student_profiles s ON u.id = s.user_id
                WHERE e.class_id = %s
                ORDER BY u.name
            """, (class_id,))
            students = cursor.fetchall()
            
            # Pending join requests for this specific class
            cursor.execute("""
                SELECT r.id as request_id, r.requested_at, u.id as student_id, u.name, u.email, sp.grade
                FROM class_join_requests r
                JOIN users u ON r.student_id = u.id
                LEFT JOIN student_profiles sp ON sp.user_id = u.id
                WHERE r.class_id = %s AND r.status = 'pending'
                ORDER BY r.requested_at ASC
            """, (class_id,))
            pending_requests = cursor.fetchall()
            
            return render_template('class_students.html', 
                                   students=students, 
                                   pending_requests=pending_requests,
                                   class_subject=class_info['subject'], 
                                   class_id=class_id)
    finally:
        conn.close()
