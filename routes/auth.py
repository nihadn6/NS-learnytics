from flask import Blueprint, request, jsonify, session, render_template, redirect, url_for, flash
from database.db import get_db_connection
from werkzeug.security import generate_password_hash, check_password_hash

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'GET':
        return render_template('register.html')
        
    data = request.form
    name = data.get('name')
    email = data.get('email')
    password = data.get('password')
    role = 'student'
    
    if not all([name, email, password]):
        return render_template('register.html', error='Missing fields')
        
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Check if email exists
            cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
            if cursor.fetchone():
                return render_template('register.html', error='Email already registered')
                
            pw_hash = generate_password_hash(password)
            cursor.execute("INSERT INTO users (name, email, password_hash, role) VALUES (%s, %s, %s, %s)",
                           (name, email, pw_hash, role))
            user_id = cursor.lastrowid
            
            # create profile entry
            if role == 'teacher':
                cursor.execute("INSERT INTO teacher_profiles (user_id) VALUES (%s)", (user_id,))
            elif role == 'student':
                import uuid
                qr_token = str(uuid.uuid4())
                cursor.execute("INSERT INTO student_profiles (user_id, qr_code) VALUES (%s, %s)", (user_id, qr_token))
        conn.commit()
        # Inform the new user how to access their QR and inform admins about teacher invites
        flash('Registration successful. Students can view/download their QR from the Profile page after login.\nAdmins can create teacher/moderator accounts from the Super Admin dashboard.')
        return redirect(url_for('auth.login'))
    except Exception as e:
        return render_template('register.html', error=str(e))
    finally:
        conn.close()

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template('login.html')
        
    data = request.form
    email = data.get('email')
    password = data.get('password')
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, name, password_hash, role FROM users WHERE email = %s", (email,))
            user = cursor.fetchone()
            
            if user and check_password_hash(user['password_hash'], password):
                session.permanent = True
                session['user_id'] = user['id']
                session['name'] = user['name']
                session['role'] = user['role']
                
                if user['role'] == 'teacher':
                    return redirect(url_for('analytics.teacher_dashboard'))
                elif user['role'] == 'superadmin':
                    return redirect(url_for('admin.dashboard'))
                elif user['role'] == 'moderator':
                    return redirect(url_for('analytics.moderator_dashboard'))
                else:
                    return redirect(url_for('analytics.student_dashboard'))
            else:
                return render_template('login.html', error="Invalid email or password")
    except Exception as e:
        return render_template('login.html', error=str(e))
    finally:
        conn.close()

@auth_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.login'))
