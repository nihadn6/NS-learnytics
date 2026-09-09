import os
import sys
# Add parent dir to path so database.db import works
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database.db import get_db_connection

def run_migration():
    print("Running migration for LMS and Announcements...")
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # 1. Materials table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS materials (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    class_id INT NOT NULL,
                    teacher_id INT NOT NULL,
                    title VARCHAR(255) NOT NULL,
                    description TEXT,
                    file_path VARCHAR(255),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE,
                    FOREIGN KEY (teacher_id) REFERENCES users(id) ON DELETE CASCADE
                );
            """)

            # 2. Assignments table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS assignments (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    class_id INT NOT NULL,
                    teacher_id INT NOT NULL,
                    title VARCHAR(255) NOT NULL,
                    description TEXT,
                    due_date DATETIME NOT NULL,
                    max_points DECIMAL(5,2) DEFAULT 100.00,
                    attachment_path VARCHAR(255),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE,
                    FOREIGN KEY (teacher_id) REFERENCES users(id) ON DELETE CASCADE
                );
            """)

            # 3. Assignment Submissions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS assignment_submissions (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    assignment_id INT NOT NULL,
                    student_id INT NOT NULL,
                    submission_text TEXT,
                    file_path VARCHAR(255),
                    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    marks_obtained DECIMAL(5,2) DEFAULT NULL,
                    feedback TEXT DEFAULT NULL,
                    status ENUM('submitted', 'graded') DEFAULT 'submitted',
                    FOREIGN KEY (assignment_id) REFERENCES assignments(id) ON DELETE CASCADE,
                    FOREIGN KEY (student_id) REFERENCES users(id) ON DELETE CASCADE,
                    UNIQUE(assignment_id, student_id)
                );
            """)

            # 4. Announcements table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS announcements (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    class_id INT NOT NULL,
                    teacher_id INT NOT NULL,
                    title VARCHAR(255) NOT NULL,
                    content TEXT NOT NULL,
                    target_audience ENUM('all', 'students_only', 'parents_only') DEFAULT 'all',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE,
                    FOREIGN KEY (teacher_id) REFERENCES users(id) ON DELETE CASCADE
                );
            """)

            conn.commit()
            print("Migration completed successfully!")
    finally:
        conn.close()

if __name__ == '__main__':
    run_migration()
