import pymysql
import os
import random
import uuid
from faker import Faker
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash

DB_HOST = os.environ.get('DB_HOST', 'localhost')
DB_USER = os.environ.get('DB_USER', 'root')
DB_PASS = os.environ.get('DB_PASS', '')
DB_NAME = 'ns_learnytics'

def get_connection(db=None):
    return pymysql.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASS,
        database=db,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
        charset='utf8',
        init_command='SET NAMES utf8'
    )

def setup_database():
    print("Setting up database structure...")
    conn = get_connection()
    with conn.cursor() as cursor:
        with open('database/schema.sql', 'r') as f:
            # We must handle multi-statements. Basic split by strictly semicolons:
            sql_statements = f.read().split(';')
            for stmt in sql_statements:
                if stmt.strip():
                    cursor.execute(stmt)
    conn.close()

def seed_data():
    setup_database()
    print("Seeding database...")
    conn = get_connection(DB_NAME)
    faker = Faker()
    
    with conn.cursor() as cursor:
        # Clean existing data securely
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0;")
        tables = ['expenses', 'payments', 'marks', 'attendance', 'enrollments', 'classes', 'student_profiles', 'teacher_profiles', 'users']
        for t in tables:
            cursor.execute(f"TRUNCATE TABLE {t};")
        cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")
        
        # 0. Super Admin
        pw_hash_admin = generate_password_hash('password123')
        cursor.execute("INSERT INTO users (name, email, password_hash, role) VALUES (%s, %s, %s, 'superadmin')", 
                       ('System Admin', 'admin@test.com', pw_hash_admin))

        # 1. Teachers
        teachers = []
        pw_hash = generate_password_hash('password123')
        
        # Insert a fixed test teacher
        cursor.execute("INSERT INTO users (name, email, password_hash, role) VALUES (%s, %s, %s, 'teacher')", 
                       ('Admin Teacher', 'teacher@test.com', pw_hash))
        test_teacher_id = cursor.lastrowid
        teachers.append(test_teacher_id)
        cursor.execute("INSERT INTO teacher_profiles (user_id, subjects, experience) VALUES (%s, %s, %s)",
                       (test_teacher_id, 'Math, Science', '5 years of teaching experience.'))
                       
        for _ in range(2):
            cursor.execute("INSERT INTO users (name, email, password_hash, role) VALUES (%s, %s, %s, 'teacher')", 
                           (faker.name(), faker.email(), pw_hash))
            teacher_id = cursor.lastrowid
            teachers.append(teacher_id)
            cursor.execute("INSERT INTO teacher_profiles (user_id, subjects, experience) VALUES (%s, %s, %s)",
                           (teacher_id, 'Math, Science', '5 years.'))

        # 2. Students
        students = []
        # Insert a fixed test student (with QR token)
        cursor.execute("INSERT INTO users (name, email, password_hash, role) VALUES (%s, %s, %s, 'student')", 
                       ('Demo Student', 'student@test.com', pw_hash))
        test_student_id = cursor.lastrowid
        students.append(test_student_id)
        qr_token = str(uuid.uuid4())
        cursor.execute("INSERT INTO student_profiles (user_id, grade, qr_code) VALUES (%s, %s, %s)",
                       (test_student_id, '10', qr_token))
                       
        for _ in range(19):
            cursor.execute("INSERT INTO users (name, email, password_hash, role) VALUES (%s, %s, %s, 'student')", 
                           (faker.name(), faker.email(), pw_hash))
            student_id = cursor.lastrowid
            students.append(student_id)
            qr_token = str(uuid.uuid4())
            cursor.execute("INSERT INTO student_profiles (user_id, grade, qr_code) VALUES (%s, %s, %s)",
                           (student_id, random.choice(['10', '11', '12']), qr_token))

        # Insert a fixed moderator (clerk) user who can scan and mark attendance
        cursor.execute("INSERT INTO users (name, email, password_hash, role) VALUES (%s, %s, %s, 'moderator')",
                       ('Attendance Clerk', 'clerk@test.com', pw_hash))

        # 3. Classes
        classes = []
        subjects = ['Mathematics', 'Physics', 'Chemistry', 'English', 'Biology']
        for teacher_id in teachers:
            # Each teacher has 2 classes
            for _ in range(2):
                subject = random.choice(subjects)
                join_code = faker.ean8()
                fee = random.choice([2000.00, 2500.00, 3000.00])
                cursor.execute("INSERT INTO classes (teacher_id, subject, schedule, fee, join_code) VALUES (%s, %s, %s, %s, %s)",
                               (teacher_id, subject, 'Sat 9 AM - 11 AM', fee, join_code))
                class_id = cursor.lastrowid
                classes.append({'id': class_id, 'fee': fee, 'teacher_id': teacher_id})

        # 4. Enrollments
        for class_info in classes:
            class_id = class_info['id']
            # Enroll 10-15 students in each class
            enrolled = random.sample(students, random.randint(10, 15))
            for student_id in enrolled:
                cursor.execute("INSERT INTO enrollments (class_id, student_id) VALUES (%s, %s)", (class_id, student_id))
                
                # 5. Attendance (Generate past 10 sessions)
                is_poor_attendee = random.random() < 0.2
                is_high_attendee = random.random() > 0.4
                
                for i in range(10):
                    date = datetime.now().date() - timedelta(days=i*7)
                    if is_poor_attendee:
                        status = 'present' if random.random() < 0.4 else 'absent'
                    elif is_high_attendee:
                        status = 'present' if random.random() < 0.9 else 'absent'
                    else:
                        status = 'present' if random.random() < 0.7 else 'absent'
                        
                    try:
                        cursor.execute("INSERT INTO attendance (class_id, student_id, date, status) VALUES (%s, %s, %s, %s)",
                                       (class_id, student_id, date, status))
                    except Exception:
                        pass # Ignore duplicate date issues
                
                # 6. Marks (3 Tests)
                for test in ['Midterm', 'Assignment', 'Final']:
                    date_recorded = datetime.now().date() - timedelta(days=random.randint(5, 30))
                    if is_poor_attendee:
                        score = random.uniform(30, 60)
                    elif is_high_attendee:
                        score = random.uniform(70, 95)
                    else:
                        score = random.uniform(50, 75)
                    
                    cursor.execute("INSERT INTO marks (class_id, student_id, test_name, marks_obtained, max_marks, date_recorded) VALUES (%s, %s, %s, %s, 100, %s)",
                                   (class_id, student_id, test, round(score, 2), date_recorded))

                # 7. Payments (Last 2 months)
                for i in range(2):
                    period = (datetime.now().replace(day=1) - timedelta(days=i*30)).strftime('%Y-%m')
                    if random.random() < 0.8:
                        payment_date = datetime.now().date() - timedelta(days=i*30 + random.randint(1, 10))
                        cursor.execute("INSERT INTO payments (class_id, student_id, amount, payment_date, period) VALUES (%s, %s, %s, %s, %s)",
                                       (class_id, student_id, class_info['fee'], payment_date, period))

        # 8. Expenses
        for teacher_id in teachers:
            for _ in range(5):
                expense_date = datetime.now().date() - timedelta(days=random.randint(1, 60))
                cursor.execute("INSERT INTO expenses (teacher_id, description, amount, expense_date) VALUES (%s, %s, %s, %s)",
                               (teacher_id, random.choice(['Zoom Pro', 'Notes printing', 'Markers', 'Helpers', 'Internet']), random.randint(500, 2000), expense_date))
                
    conn.close()
    print("Database seeded completely!")

if __name__ == '__main__':
    seed_data()
