from flask import Blueprint, request, jsonify, session, render_template, redirect, url_for, send_file, make_response
from database.db import get_db_connection
import io
import qrcode

profile_bp = Blueprint('profile', __name__)

@profile_bp.route('/profile', methods=['GET'])
def view_profile():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
        
    user_id = session['user_id']
    role = session['role']
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            if role == 'teacher':
                cursor.execute("""
                    SELECT u.name, u.email, t.subjects, t.experience 
                    FROM users u 
                    JOIN teacher_profiles t ON u.id = t.user_id 
                    WHERE u.id = %s
                """, (user_id,))
            elif role == 'student':
                cursor.execute("""
                    SELECT u.name, u.email, s.grade, s.qr_code 
                    FROM users u 
                    JOIN student_profiles s ON u.id = s.user_id 
                    WHERE u.id = %s
                """, (user_id,))
            else:
                # Moderators and Super Admin don't have extended profiles
                cursor.execute("""
                    SELECT u.name, u.email 
                    FROM users u 
                    WHERE u.id = %s
                """, (user_id,))
            
            profile_data = cursor.fetchone()
            if not profile_data:
                return "Profile not found", 404
            return render_template('profile.html', profile=profile_data, role=role)
    except Exception as e:
        return str(e), 500
    finally:
        conn.close()


@profile_bp.route('/profile/qr')
def profile_qr():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    user_id = session['user_id']
    role = session['role']
    # Only students (and moderators) can retrieve student QR codes
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT s.qr_code FROM student_profiles s WHERE s.user_id = %s", (user_id,))
            row = cursor.fetchone()
            if not row or not row.get('qr_code'):
                return "No QR code available", 404
            token = row['qr_code']

            # If download param set, return as attachment
            download = request.args.get('download')

            img = qrcode.make(token)
            buf = io.BytesIO()
            img.save(buf, format='PNG')
            buf.seek(0)

            if download:
                return send_file(buf, mimetype='image/png', as_attachment=True, download_name=f'qr_{user_id}.png')
            # Otherwise inline
            response = make_response(buf.getvalue())
            response.headers.set('Content-Type', 'image/png')
            return response
    finally:
        conn.close()

@profile_bp.route('/profile/edit', methods=['POST'])
def edit_profile():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
        
    user_id = session['user_id']
    role = session['role']
    data = request.form
    name = data.get('name')
    email = data.get('email')
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Update base user
            cursor.execute("UPDATE users SET name = %s, email = %s WHERE id = %s", (name, email, user_id))
            
            if role == 'teacher':
                subjects = data.get('subjects')
                experience = data.get('experience')
                cursor.execute("UPDATE teacher_profiles SET subjects = %s, experience = %s WHERE user_id = %s", 
                               (subjects, experience, user_id))
            elif role == 'student':
                grade = data.get('grade')
                cursor.execute("UPDATE student_profiles SET grade = %s WHERE user_id = %s", 
                               (grade, user_id))
        conn.commit()
        session['name'] = name
        return redirect(url_for('profile.view_profile'))
    except Exception as e:
        return str(e), 500
    finally:
        conn.close()
