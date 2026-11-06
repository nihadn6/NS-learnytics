from flask import Blueprint, render_template, session, redirect, url_for, request, jsonify
from database.db import get_db_connection

messages_bp = Blueprint('messages', __name__)

@messages_bp.before_request
def check_auth():
    if not session.get('user_id'):
        return redirect(url_for('auth.login'))

def get_student_allowed_contact_ids(student_id, cursor):
    """
    Returns the set of user IDs a student is permitted to chat with:
    1. Teachers instructing classes in which this student is actively enrolled.
    2. System administrators ('superadmin' and 'moderator').
    """
    cursor.execute("""
        SELECT DISTINCT c.teacher_id AS id
        FROM classes c
        JOIN enrollments e ON e.class_id = c.id
        WHERE e.student_id = %s
        UNION
        SELECT id FROM users WHERE role IN ('superadmin', 'moderator')
    """, (student_id,))
    rows = cursor.fetchall()
    return {r['id'] for r in rows}

def can_chat_between(user_1_id, user_1_role, user_2_id, cursor):
    """
    Strict authorization gate:
    - If user 1 is a student, user 2 MUST be one of their teachers or an administrator.
    - If user 2 is a student, user 1 MUST be one of their teachers or an administrator.
    - Users cannot message themselves.
    """
    if not user_1_id or not user_2_id or user_1_id == user_2_id:
        return False

    cursor.execute("SELECT id, role FROM users WHERE id = %s", (user_2_id,))
    user_2 = cursor.fetchone()
    if not user_2:
        return False

    user_2_role = user_2['role']

    # When user 1 is a student: recipient MUST be an admin or a teacher of an enrolled class
    if user_1_role == 'student':
        allowed_ids = get_student_allowed_contact_ids(user_1_id, cursor)
        if user_2_id not in allowed_ids:
            return False

    # When user 2 is a student: sender MUST be an admin or a teacher of an enrolled class
    if user_2_role == 'student':
        allowed_ids = get_student_allowed_contact_ids(user_2_id, cursor)
        if user_1_id not in allowed_ids:
            return False

    return True

@messages_bp.route('/messages', methods=['GET'])
def inbox():
    role = session.get('role')
    user_id = session.get('user_id')
    if role not in ['teacher', 'student', 'parent', 'superadmin', 'moderator']:
        return "Unauthorized. Only teachers, students, parents, admins, and staff can use messaging.", 403

    raw_target_id = request.args.get('user_id') or request.args.get('student_id') or request.args.get('contact_id')
    target_user = None
    if raw_target_id and raw_target_id.isdigit():
        target_id = int(raw_target_id)
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                # Enforce chat permission before allowing target user pre-selection
                if can_chat_between(user_id, role, target_id, cursor):
                    cursor.execute("SELECT id, name, email, role FROM users WHERE id = %s", (target_id,))
                    target_user = cursor.fetchone()
        finally:
            conn.close()

    return render_template('messages.html', current_user_id=user_id, target_user=target_user)

@messages_bp.route('/api/messages/contacts', methods=['GET'])
def get_contacts():
    user_id = session.get('user_id')
    role = session.get('role')
    conn = get_db_connection()
    contacts = []
    
    try:
        with conn.cursor() as cursor:
            if role == 'student':
                # Students can only chat with their teachers and admins
                cursor.execute("""
                    SELECT DISTINCT u.id, u.name, u.email, u.role
                    FROM users u
                    JOIN classes c ON c.teacher_id = u.id
                    JOIN enrollments e ON e.class_id = c.id
                    WHERE e.student_id = %s
                    UNION
                    SELECT id, name, email, role 
                    FROM users 
                    WHERE role IN ('superadmin', 'moderator')
                    ORDER BY role, name
                """, (user_id,))
                contacts = cursor.fetchall()
                
            elif role == 'parent':
                cursor.execute("""
                    SELECT DISTINCT u.id, u.name, u.email, u.role
                    FROM users u
                    JOIN classes c ON c.teacher_id = u.id
                    JOIN enrollments e ON e.class_id = c.id
                    JOIN parent_student_links psl ON psl.student_id = e.student_id
                    WHERE psl.parent_id = %s AND psl.status = 'approved'
                    UNION
                    SELECT id, name, email, role FROM users WHERE role IN ('superadmin', 'moderator')
                """, (user_id,))
                contacts = cursor.fetchall()
                
            elif role == 'teacher':
                cursor.execute("""
                    SELECT DISTINCT u.id, u.name, u.email, 'student' as role
                    FROM users u
                    JOIN enrollments e ON e.student_id = u.id
                    JOIN classes c ON e.class_id = c.id
                    WHERE c.teacher_id = %s
                    UNION
                    SELECT DISTINCT u.id, u.name, u.email, 'parent' as role
                    FROM users u
                    JOIN parent_student_links psl ON psl.parent_id = u.id
                    JOIN enrollments e ON psl.student_id = e.student_id
                    JOIN classes c ON e.class_id = c.id
                    WHERE c.teacher_id = %s AND psl.status = 'approved'
                    UNION
                    SELECT id, name, email, role FROM users WHERE role IN ('superadmin', 'moderator')
                    UNION
                    SELECT id, name, email, role FROM users WHERE role = 'teacher' AND id != %s
                """, (user_id, user_id, user_id))
                contacts = cursor.fetchall()

            elif role in ['superadmin', 'moderator']:
                cursor.execute("""
                    SELECT id, name, email, role
                    FROM users
                    WHERE id != %s
                    ORDER BY role, name
                """, (user_id,))
                contacts = cursor.fetchall()

            # Merge previous conversations
            cursor.execute("""
                SELECT DISTINCT u.id, u.name, u.email, u.role
                FROM users u
                JOIN messages m ON (m.sender_id = u.id AND m.receiver_id = %s) 
                                OR (m.receiver_id = u.id AND m.sender_id = %s)
                WHERE u.id != %s
            """, (user_id, user_id, user_id))
            past_contacts = cursor.fetchall()
            existing_ids = {c['id'] for c in contacts}
            for pc in past_contacts:
                if pc['id'] not in existing_ids:
                    # Enforce student permission: only add if permitted
                    if role == 'student' and not can_chat_between(user_id, role, pc['id'], cursor):
                        continue
                    contacts.append(pc)
                    existing_ids.add(pc['id'])

            # Final filter for student: ensure no unauthorized contact is returned
            if role == 'student':
                allowed_ids = get_student_allowed_contact_ids(user_id, cursor)
                contacts = [c for c in contacts if c['id'] in allowed_ids]

            # For each contact, fetch the unread message count and latest message timestamp
            for c in contacts:
                cursor.execute("""
                    SELECT COUNT(*) as unread_count 
                    FROM messages 
                    WHERE sender_id = %s AND receiver_id = %s AND is_read = FALSE
                """, (c['id'], user_id))
                c['unread'] = cursor.fetchone()['unread_count']
                
                cursor.execute("""
                    SELECT created_at 
                    FROM messages 
                    WHERE (sender_id = %s AND receiver_id = %s) 
                       OR (sender_id = %s AND receiver_id = %s)
                    ORDER BY created_at DESC LIMIT 1
                """, (c['id'], user_id, user_id, c['id']))
                latest = cursor.fetchone()
                c['latest_msg_time'] = latest['created_at'].timestamp() if latest else 0

            # Sort contacts by latest_msg_time DESC (most recent first), then by name ASC
            contacts.sort(key=lambda x: (-x['latest_msg_time'], x['name']))

        return jsonify(contacts)
    finally:
        conn.close()

@messages_bp.route('/api/messages/search', methods=['GET'])
def search_contacts():
    user_id = session.get('user_id')
    role = session.get('role')
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify([])

    conn = get_db_connection()
    try:
        search_pattern = f"%{query}%"
        with conn.cursor() as cursor:
            if role in ['superadmin', 'moderator']:
                cursor.execute("""
                    SELECT id, name, email, role
                    FROM users
                    WHERE id != %s AND (name LIKE %s OR email LIKE %s OR role LIKE %s)
                    ORDER BY name LIMIT 20
                """, (user_id, search_pattern, search_pattern, search_pattern))
            elif role == 'teacher':
                cursor.execute("""
                    SELECT DISTINCT u.id, u.name, u.email, u.role
                    FROM users u
                    WHERE u.id != %s AND (u.name LIKE %s OR u.email LIKE %s OR u.role LIKE %s)
                    AND (
                        u.role IN ('teacher', 'superadmin')
                        OR u.id IN (SELECT e.student_id FROM enrollments e JOIN classes c ON e.class_id = c.id WHERE c.teacher_id = %s)
                        OR u.id IN (SELECT psl.parent_id FROM parent_student_links psl JOIN enrollments e ON psl.student_id = e.student_id JOIN classes c ON e.class_id = c.id WHERE c.teacher_id = %s AND psl.status = 'approved')
                    )
                    ORDER BY u.name LIMIT 20
                """, (user_id, search_pattern, search_pattern, search_pattern, user_id, user_id))
            elif role == 'student':
                cursor.execute("""
                    SELECT DISTINCT u.id, u.name, u.email, u.role
                    FROM users u
                    WHERE u.id != %s AND (u.name LIKE %s OR u.email LIKE %s OR u.role LIKE %s)
                    AND (
                        u.role IN ('superadmin', 'moderator')
                        OR u.id IN (SELECT c.teacher_id FROM classes c JOIN enrollments e ON e.class_id = c.id WHERE e.student_id = %s)
                    )
                    ORDER BY u.name LIMIT 20
                """, (user_id, search_pattern, search_pattern, search_pattern, user_id))
            elif role == 'parent':
                cursor.execute("""
                    SELECT DISTINCT u.id, u.name, u.email, u.role
                    FROM users u
                    WHERE u.id != %s AND (u.name LIKE %s OR u.email LIKE %s OR u.role LIKE %s)
                    AND (
                        u.role IN ('superadmin', 'moderator')
                        OR u.id IN (SELECT c.teacher_id FROM classes c JOIN enrollments e ON e.class_id = c.id JOIN parent_student_links psl ON psl.student_id = e.student_id WHERE psl.parent_id = %s AND psl.status = 'approved')
                    )
                    ORDER BY u.name LIMIT 20
                """, (user_id, search_pattern, search_pattern, search_pattern, user_id))
            else:
                return jsonify([])

            results = cursor.fetchall()
            return jsonify(results)
    finally:
        conn.close()

@messages_bp.route('/api/messages/history/<int:other_id>', methods=['GET'])
def get_history(other_id):
    user_id = session.get('user_id')
    role = session.get('role')
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Enforce chat permissions
            if not can_chat_between(user_id, role, other_id, cursor):
                return jsonify({'error': 'Unauthorized. Students can only chat with their teachers and administrators.'}), 403

            # Mark messages as read
            cursor.execute("""
                UPDATE messages SET is_read = TRUE 
                WHERE sender_id = %s AND receiver_id = %s
            """, (other_id, user_id))
            conn.commit()

            cursor.execute("""
                SELECT id, sender_id, receiver_id, content, created_at, is_read, is_edited, is_deleted
                FROM messages
                WHERE (sender_id = %s AND receiver_id = %s) 
                   OR (sender_id = %s AND receiver_id = %s)
                ORDER BY created_at ASC
            """, (user_id, other_id, other_id, user_id))
            messages = cursor.fetchall()
            
            # Format dates
            for m in messages:
                m['created_at'] = m['created_at'].strftime('%Y-%m-%d %H:%M')
                
        return jsonify(messages)
    finally:
        conn.close()

@messages_bp.route('/api/messages/send', methods=['POST'])
def send_message():
    user_id = session.get('user_id')
    role = session.get('role')
    data = request.get_json() or {}
    receiver_id = data.get('receiver_id')
    content = data.get('content')
    
    if not receiver_id or not content or not str(content).strip():
        return jsonify({'error': 'Missing recipient or content.'}), 400
        
    try:
        receiver_id = int(receiver_id)
    except (ValueError, TypeError):
        return jsonify({'error': 'Invalid recipient ID.'}), 400

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Enforce strict chat permission
            if not can_chat_between(user_id, role, receiver_id, cursor):
                return jsonify({'error': 'Unauthorized. Students can only chat with their teachers and administrators.'}), 403
            
            cursor.execute("""
                INSERT INTO messages (sender_id, receiver_id, content)
                VALUES (%s, %s, %s)
            """, (user_id, receiver_id, str(content).strip()))
            conn.commit()
            
            # Return the sent message data
            msg_id = cursor.lastrowid
            cursor.execute("SELECT id, sender_id, receiver_id, content, created_at, is_read, is_edited, is_deleted FROM messages WHERE id = %s", (msg_id,))
            new_msg = cursor.fetchone()
            new_msg['created_at'] = new_msg['created_at'].strftime('%Y-%m-%d %H:%M')
            
        return jsonify({'success': True, 'message': new_msg})
    finally:
        conn.close()

@messages_bp.route('/api/messages/edit/<int:message_id>', methods=['PUT'])
def edit_message(message_id):
    user_id = session.get('user_id')
    data = request.get_json()
    new_content = data.get('content')
    if not new_content:
        return jsonify({'error': 'Missing content'}), 400
        
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                UPDATE messages SET content = %s, is_edited = TRUE 
                WHERE id = %s AND sender_id = %s AND is_deleted = FALSE
            """, (new_content, message_id, user_id))
            if cursor.rowcount == 0:
                return jsonify({'error': 'Unauthorized or deleted'}), 403
            conn.commit()
        return jsonify({'success': True})
    finally:
        conn.close()

@messages_bp.route('/api/messages/delete/<int:message_id>', methods=['DELETE'])
def delete_message(message_id):
    user_id = session.get('user_id')
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                UPDATE messages SET is_deleted = TRUE 
                WHERE id = %s AND sender_id = %s
            """, (message_id, user_id))
            if cursor.rowcount == 0:
                return jsonify({'error': 'Unauthorized'}), 403
            conn.commit()
        return jsonify({'success': True})
    finally:
        conn.close()
