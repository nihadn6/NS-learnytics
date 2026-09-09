from database.db import get_db_connection

def create_notification(user_id, message, msg_type='general'):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO notifications (user_id, message, type) 
                VALUES (%s, %s, %s)
            """, (user_id, message, msg_type))
            conn.commit()
    finally:
        conn.close()

def notify_parents_of_absence(student_id, student_name, class_name, date):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Find all approved parents for this student
            cursor.execute("""
                SELECT parent_id FROM parent_student_links 
                WHERE student_id = %s AND status = 'approved'
            """, (student_id,))
            parents = cursor.fetchall()
            
            for p in parents:
                msg = f"Absence Alert: {student_name} was marked absent for {class_name} on {date}."
                cursor.execute("""
                    INSERT INTO notifications (user_id, message, type) 
                    VALUES (%s, %s, 'absence')
                """, (p['parent_id'], msg))
            conn.commit()
    finally:
        conn.close()

def notify_parents_of_marks(student_id, student_name, class_name, test_name, marks, max_marks):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT parent_id FROM parent_student_links 
                WHERE student_id = %s AND status = 'approved'
            """, (student_id,))
            parents = cursor.fetchall()
            
            for p in parents:
                msg = f"New Marks Published: {student_name} scored {marks}/{max_marks} in {test_name} ({class_name})."
                cursor.execute("""
                    INSERT INTO notifications (user_id, message, type) 
                    VALUES (%s, %s, 'marks')
                """, (p['parent_id'], msg))
            conn.commit()
    finally:
        conn.close()
