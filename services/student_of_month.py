import datetime
from database.db import get_db_connection

def get_or_calculate_student_of_the_month(conn, month_period=None):
    """
    Retrieves or calculates the 'Student of the Month' for each subject.
    The honoree is chosen based on the highest average test score
    (AVG(marks_obtained / max_marks * 100)) recorded in the evaluation month.
    
    Compatible with MySQL 5.1+.
    """
    now = datetime.datetime.now()
    if not month_period:
        month_period = now.strftime('%Y-%m')

    with conn.cursor() as cursor:
        # 1. Check if already calculated and saved for this month_period
        cursor.execute("""
            SELECT som.id, som.month_period, som.subject, som.student_id, 
                   som.average_score, som.tests_count,
                   u.name as student_name, sp.grade
            FROM student_of_the_month som
            JOIN users u ON som.student_id = u.id
            LEFT JOIN student_profiles sp ON u.id = sp.user_id
            WHERE som.month_period = %s
            ORDER BY som.subject ASC
        """, (month_period,))
        existing = cursor.fetchall()
        
        if existing:
            # Format month display e.g. "September 2026"
            try:
                dt = datetime.datetime.strptime(month_period, '%Y-%m')
                month_display = dt.strftime('%B %Y')
            except Exception:
                month_display = month_period
                
            for item in existing:
                item['month_display'] = month_display
                item['average_score'] = round(float(item['average_score']), 1)
            return existing, month_display

        # 2. Not yet calculated for this month_period. Compute from marks table.
        # First, check if marks exist in this month_period
        cursor.execute("""
            SELECT 
                c.subject,
                m.student_id,
                u.name as student_name,
                sp.grade,
                AVG(m.marks_obtained / m.max_marks * 100) as avg_score,
                COUNT(m.id) as tests_taken
            FROM marks m
            JOIN classes c ON m.class_id = c.id
            JOIN users u ON m.student_id = u.id
            LEFT JOIN student_profiles sp ON u.id = sp.user_id
            WHERE DATE_FORMAT(m.date_recorded, '%%Y-%%m') = %s
            GROUP BY c.subject, m.student_id, u.name, sp.grade
            ORDER BY c.subject ASC, avg_score DESC, tests_taken DESC
        """, (month_period,))
        candidate_rows = cursor.fetchall()

        effective_period = month_period

        # 3. If no marks in requested month (e.g. month just started or seed data),
        # fallback to the latest month that has assessment marks recorded
        if not candidate_rows:
            cursor.execute("SELECT DATE_FORMAT(MAX(date_recorded), '%%Y-%%m') as latest_period FROM marks")
            latest_row = cursor.fetchone()
            if latest_row and latest_row['latest_period']:
                effective_period = latest_row['latest_period']
                cursor.execute("""
                    SELECT 
                        c.subject,
                        m.student_id,
                        u.name as student_name,
                        sp.grade,
                        AVG(m.marks_obtained / m.max_marks * 100) as avg_score,
                        COUNT(m.id) as tests_taken
                    FROM marks m
                    JOIN classes c ON m.class_id = c.id
                    JOIN users u ON m.student_id = u.id
                    LEFT JOIN student_profiles sp ON u.id = sp.user_id
                    WHERE DATE_FORMAT(m.date_recorded, '%%Y-%%m') = %s
                    GROUP BY c.subject, m.student_id, u.name, sp.grade
                    ORDER BY c.subject ASC, avg_score DESC, tests_taken DESC
                """, (effective_period,))
                candidate_rows = cursor.fetchall()

        # If still no marks at all, return empty
        if not candidate_rows:
            return [], now.strftime('%B %Y')

        # 4. Filter top performer per subject
        top_per_subject = {}
        for row in candidate_rows:
            subj = row['subject']
            if subj not in top_per_subject:
                top_per_subject[subj] = row

        # 5. Persist calculated winners to student_of_the_month table for month_period
        try:
            dt = datetime.datetime.strptime(effective_period, '%Y-%m')
            month_display = dt.strftime('%B %Y')
        except Exception:
            month_display = effective_period

        results = []
        for subj, row in top_per_subject.items():
            avg_score = round(float(row['avg_score']), 1)
            tests_count = int(row['tests_taken'])
            student_id = int(row['student_id'])

            cursor.execute("""
                INSERT INTO student_of_the_month 
                    (month_period, subject, student_id, average_score, tests_count)
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE 
                    average_score = VALUES(average_score), 
                    tests_count = VALUES(tests_count)
            """, (month_period, subj, student_id, avg_score, tests_count))

            results.append({
                'subject': subj,
                'student_id': student_id,
                'student_name': row['student_name'],
                'grade': row['grade'] or 'N/A',
                'average_score': avg_score,
                'tests_count': tests_count,
                'month_period': month_period,
                'month_display': month_display
            })

        conn.commit()
        # Sort alphabetically by subject
        results.sort(key=lambda x: x['subject'])
        return results, month_display
