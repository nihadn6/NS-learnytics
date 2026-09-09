import unittest
import os
import sys
import datetime

# Ensure project root is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app
from database.seed import seed_data
from database.db import get_db_connection

class TestLMSAndAnnouncements(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        print("Setting up test database seed...")
        seed_data()

    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True

    def login(self, email, password):
        return self.app.post('/login', data=dict(
            email=email,
            password=password
        ), follow_redirects=True)

    def logout(self):
        return self.app.get('/logout', follow_redirects=True)

    def test_01_teacher_dashboard_and_class_access(self):
        print("Test 1: Teacher login and LMS hub rendering...")
        res = self.login('teacher@test.com', 'password123')
        self.assertIn(b'Teacher Dashboard', res.data)

        res_lms = self.app.get('/lms')
        self.assertEqual(res_lms.status_code, 200)
        self.assertIn(b'Learning Management Hub', res_lms.data)

    def test_02_create_assignment_and_announcement(self):
        print("Test 2: Creating Assignment & Broadcast Announcement...")
        self.login('teacher@test.com', 'password123')

        # Fetch first class owned by teacher
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM classes WHERE teacher_id = (SELECT id FROM users WHERE email = 'teacher@test.com') LIMIT 1")
            class_row = cursor.fetchone()
        conn.close()

        class_id = class_row['id']

        # 1. Create Assignment
        due_str = (datetime.datetime.now() + datetime.timedelta(days=2)).strftime('%Y-%m-%dT%H:%M')
        res_assign = self.app.post('/lms/assignment/create', data=dict(
            class_id=class_id,
            title='Unit Test Assignment 1',
            description='Solve Quantum Mechanics problems 1 through 5.',
            due_date=due_str,
            max_points=100.0
        ), follow_redirects=True)

        self.assertEqual(res_assign.status_code, 200)
        self.assertIn(b'Assignment published successfully!', res_assign.data)

        # 2. Create Broadcast Announcement
        res_ann = self.app.post('/announcements/create', data=dict(
            class_id=class_id,
            target_audience='all',
            title='Midterm Exam Alert',
            content='Please review Chapter 1-4 for the upcoming midterm.'
        ), follow_redirects=True)

        self.assertEqual(res_ann.status_code, 200)
        self.assertIn(b'Broadcast Announcement published successfully!', res_ann.data)

    def test_03_student_lms_view_and_submission(self):
        print("Test 3: Student LMS view, homework submission, and announcements feed...")
        self.login('student@test.com', 'password123')

        res_lms = self.app.get('/lms')
        self.assertEqual(res_lms.status_code, 200)
        self.assertIn(b'Student Learning Hub', res_lms.data)

        # Fetch assignment id
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM assignments WHERE title = 'Unit Test Assignment 1' LIMIT 1")
            assign_row = cursor.fetchone()
        conn.close()

        assign_id = assign_row['id']

        # Submit work
        res_sub = self.app.post('/lms/assignment/submit', data=dict(
            assignment_id=assign_id,
            submission_text='Here is my completed solution for Quantum Mechanics.'
        ), follow_redirects=True)

        self.assertEqual(res_sub.status_code, 200)
        self.assertIn(b'Assignment submitted successfully!', res_sub.data)

        # Check announcements feed
        res_feed = self.app.get('/announcements')
        self.assertEqual(res_feed.status_code, 200)
        self.assertIn(b'Midterm Exam Alert', res_feed.data)

    def test_04_teacher_grading_roster(self):
        print("Test 4: Teacher grading student submission...")
        self.login('teacher@test.com', 'password123')

        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM assignments WHERE title = 'Unit Test Assignment 1' LIMIT 1")
            assign_id = cursor.fetchone()['id']

            cursor.execute("SELECT id FROM assignment_submissions WHERE assignment_id = %s LIMIT 1", (assign_id,))
            sub_id = cursor.fetchone()['id']
        conn.close()

        res_grade = self.app.post(f'/lms/submission/{sub_id}/grade', data=dict(
            marks_obtained='95.5',
            feedback='Excellent mathematical derivations!'
        ), follow_redirects=True)

        self.assertEqual(res_grade.status_code, 200)
        self.assertIn(b'Grade and feedback saved successfully!', res_grade.data)
        self.assertIn(b'95.5', res_grade.data)

    def test_05_csv_template_and_bulk_upload(self):
        print("Test 5: CSV Template Download & Bulk Marks Import...")
        self.login('teacher@test.com', 'password123')

        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM classes WHERE teacher_id = (SELECT id FROM users WHERE email = 'teacher@test.com') LIMIT 1")
            class_id = cursor.fetchone()['id']
            cursor.execute("SELECT u.id FROM enrollments e JOIN users u ON e.student_id = u.id WHERE e.class_id = %s LIMIT 2", (class_id,))
            students = cursor.fetchall()
        conn.close()

        # 1. Download Template
        res_tmpl = self.app.get(f'/marks/template/{class_id}')
        self.assertEqual(res_tmpl.status_code, 200)
        self.assertIn(b'student_id,student_name,marks_obtained', res_tmpl.data)

        # 2. Bulk Upload CSV
        csv_data = f"student_id,student_name,marks_obtained\n{students[0]['id']},Student A,88.5\n{students[1]['id']},Student B,92.0\n"
        from io import BytesIO
        csv_file = (BytesIO(csv_data.encode('utf-8')), 'test_marks.csv')

        res_bulk = self.app.post('/marks/bulk-upload', data=dict(
            class_id=class_id,
            test_name='CSV Quiz 1',
            max_marks='100',
            date_recorded=datetime.date.today().isoformat(),
            file=csv_file
        ), content_type='multipart/form-data', follow_redirects=True)

        self.assertEqual(res_bulk.status_code, 200)
        self.assertIn(b'Successfully imported marks', res_bulk.data)

if __name__ == '__main__':
    unittest.main()
