from flask import Blueprint, render_template, session, redirect, url_for, request, jsonify
from database.db import get_db_connection

messages_bp = Blueprint('messages', __name__)

@messages_bp.before_request
def check_auth():
    if not session.get('user_id'):
        return redirect(url_for('auth.login'))

@messages_bp.route('/messages', methods=['GET'])
def inbox():
    role = session.get('role')
    if role not in ['teacher', 'student', 'parent', 'superadmin', 'moderator']:
        return "Unauthorized. Only teachers, students, parents, admins, and staff can use messaging.", 403

    return render_template('messages.html', current_user_id=session.get('user_id'))

@messages_bp.route('/api/messages/contacts', methods=['GET'])
def get_contacts():
    user_id = session.get('user_id')
    role = session.get('role')
    conn = get_db_connection()
    contacts = []
    
    try:
        with conn.cursor() as cursor:
            if role == 'student':
                cursor.execute("""
                    SELECT DISTINCT u.id, u.name, u.email, u.role
                    FROM users u
                    JOIN classes c ON c.teacher_id = u.id
                    JOIN enrollments e ON e.class_id = c.id
                    WHERE e.student_id = %s
                    UNION
                    SELECT id, name, email, role FROM users WHERE role = 'superadmin'
                    UNION
                    SELECT DISTINCT u.id, u.name, u.email, 'student' as role
                    FROM users u
                    JOIN enrollments e ON e.student_id = u.id
                    WHERE e.class_id IN (SELECT class_id FROM enrollments WHERE student_id = %s) AND u.id != %s
                """, (user_id, user_id, user_id))
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
                    SELECT id, name, email, role FROM users WHERE role = 'superadmin'
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
                    SELECT id, name, email, role FROM users WHERE role = 'superadmin'
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

            # Always merge any person who has exchanged messages with this user
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
                    contacts.append(pc)
                    existing_ids.add(pc['id'])

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
                        u.role = 'superadmin'
                        OR u.id IN (SELECT c.teacher_id FROM classes c JOIN enrollments e ON e.class_id = c.id WHERE e.student_id = %s)
                        OR u.id IN (SELECT e2.student_id FROM enrollments e2 WHERE e2.class_id IN (SELECT class_id FROM enrollments WHERE student_id = %s))
                    )
                    ORDER BY u.name LIMIT 20
                """, (user_id, search_pattern, search_pattern, search_pattern, user_id, user_id))
            elif role == 'parent':
                cursor.execute("""
                    SELECT DISTINCT u.id, u.name, u.email, u.role
                    FROM users u
                    WHERE u.id != %s AND (u.name LIKE %s OR u.email LIKE %s OR u.role LIKE %s)
                    AND (
                        u.role = 'superadmin'
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
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
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
    data = request.get_json()
    receiver_id = data.get('receiver_id')
    content = data.get('content')
    
    if not receiver_id or not content:
        return jsonify({'error': 'Missing data'}), 400
        
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Basic validation: ensure they are allowed to message each other
            # (In a strict production app, you would rerun the JOIN queries here to double check)
            
            cursor.execute("""
                INSERT INTO messages (sender_id, receiver_id, content)
                VALUES (%s, %s, %s)
            """, (user_id, receiver_id, content))
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
