import numpy as np
from sklearn.linear_model import LinearRegression
from database.db import get_db_connection
import datetime

class GradeForecaster:
    def __init__(self):
        pass

    def _get_letter_grade(self, pct):
        if pct >= 85:
            return 'A'
        elif pct >= 75:
            return 'B'
        elif pct >= 65:
            return 'C'
        elif pct >= 50:
            return 'S'
        else:
            return 'F'

    def forecast_student_performance(self, student_id, class_id=None):
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                # Fetch Student
                cursor.execute("SELECT id, name, email FROM users WHERE id = %s AND role = 'student'", (student_id,))
                student = cursor.fetchone()
                if not student:
                    return None

                # Build SQL query for assessment marks
                query_marks = """
                    SELECT m.class_id, c.subject, m.test_name, m.marks_obtained, m.max_marks, m.date_recorded
                    FROM marks m
                    JOIN classes c ON m.class_id = c.id
                    WHERE m.student_id = %s
                """
                params = [student_id]
                if class_id:
                    query_marks += " AND m.class_id = %s"
                    params.append(class_id)
                query_marks += " ORDER BY m.date_recorded ASC"

                cursor.execute(query_marks, tuple(params))
                marks_rows = cursor.fetchall()

                # Fetch LMS assignment scores
                query_hw = """
                    SELECT a.class_id, c.subject, sub.marks_obtained, a.max_points, sub.submitted_at
                    FROM assignment_submissions sub
                    JOIN assignments a ON sub.assignment_id = a.id
                    JOIN classes c ON a.class_id = c.id
                    WHERE sub.student_id = %s AND sub.status = 'graded' AND sub.marks_obtained IS NOT NULL
                """
                hw_params = [student_id]
                if class_id:
                    query_hw += " AND a.class_id = %s"
                    hw_params.append(class_id)
                query_hw += " ORDER BY sub.submitted_at ASC"

                cursor.execute(query_hw, tuple(hw_params))
                hw_rows = cursor.fetchall()

            # Group scores by class/subject
            subject_data = {}

            for m in marks_rows:
                cid = m['class_id']
                if cid not in subject_data:
                    subject_data[cid] = {'subject': m['subject'], 'timeline': []}
                
                max_pts = float(m['max_marks']) if m['max_marks'] else 100.0
                pts = float(m['marks_obtained']) if m['marks_obtained'] else 0.0
                pct = (pts / max_pts * 100.0) if max_pts > 0 else 0.0

                subject_data[cid]['timeline'].append({
                    'name': m['test_name'],
                    'type': 'Exam',
                    'pct': pct,
                    'date': m['date_recorded'].strftime('%Y-%m-%d') if m['date_recorded'] else ''
                })

            for h in hw_rows:
                cid = h['class_id']
                if cid not in subject_data:
                    subject_data[cid] = {'subject': h['subject'], 'timeline': []}

                max_pts = float(h['max_points']) if h['max_points'] else 100.0
                pts = float(h['marks_obtained']) if h['marks_obtained'] else 0.0
                pct = (pts / max_pts * 100.0) if max_pts > 0 else 0.0

                subject_data[cid]['timeline'].append({
                    'name': 'LMS Homework',
                    'type': 'Assignment',
                    'pct': pct,
                    'date': h['submitted_at'].strftime('%Y-%m-%d') if h['submitted_at'] else ''
                })

            forecasts = []

            for cid, sinfo in subject_data.items():
                timeline = sinfo['timeline']
                if not timeline:
                    continue

                scores = [t['pct'] for t in timeline]

                # Run Scikit-Learn Linear Regression model over time index
                if len(scores) >= 2:
                    X = np.array(range(len(scores))).reshape(-1, 1)
                    y = np.array(scores)
                    reg = LinearRegression()
                    reg.fit(X, y)

                    next_idx = len(scores)
                    predicted_pct = float(reg.predict([[next_idx]])[0])
                    slope = float(reg.coef_[0])
                else:
                    predicted_pct = float(scores[0])
                    slope = 0.0

                # Clip prediction between 0% and 100%
                predicted_pct = round(max(0.0, min(100.0, predicted_pct)), 1)
                curr_avg = round(float(sum(scores) / len(scores)), 1)

                if slope > 1.5:
                    trend_status = 'Improving Trajectory'
                    trend_class = 'text-success'
                elif slope < -1.5:
                    trend_status = 'Declining Trajectory'
                    trend_class = 'text-danger'
                else:
                    trend_status = 'Stable Performance'
                    trend_class = 'text-primary'

                predicted_grade = self._get_letter_grade(predicted_pct)
                current_grade = self._get_letter_grade(curr_avg)

                forecasts.append({
                    'class_id': cid,
                    'subject': sinfo['subject'],
                    'historical_scores': scores,
                    'assessment_count': len(scores),
                    'current_avg_pct': curr_avg,
                    'current_grade': current_grade,
                    'predicted_next_exam_pct': predicted_pct,
                    'predicted_final_grade': predicted_grade,
                    'trend_slope': round(slope, 2),
                    'trend_status': trend_status,
                    'trend_class': trend_class
                })

            return {
                'student_id': student['id'],
                'name': student['name'],
                'email': student['email'],
                'forecasts': forecasts
            }
        finally:
            conn.close()

    def forecast_all_students(self, teacher_id=None, class_id=None):
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                query = "SELECT DISTINCT u.id FROM users u WHERE u.role = 'student'"
                params = []

                if class_id:
                    query = """
                        SELECT DISTINCT u.id 
                        FROM users u 
                        JOIN enrollments e ON u.id = e.student_id 
                        WHERE u.role = 'student' AND e.class_id = %s
                    """
                    params.append(class_id)
                elif teacher_id:
                    query = """
                        SELECT DISTINCT u.id 
                        FROM users u 
                        JOIN enrollments e ON u.id = e.student_id 
                        JOIN classes c ON e.class_id = c.id
                        WHERE u.role = 'student' AND c.teacher_id = %s
                    """
                    params.append(teacher_id)

                cursor.execute(query, tuple(params))
                student_ids = [row['id'] for row in cursor.fetchall()]

            results = []
            for sid in student_ids:
                f_data = self.forecast_student_performance(sid, class_id=class_id)
                if f_data and f_data['forecasts']:
                    results.append(f_data)

            return results
        finally:
            conn.close()

grade_forecaster = GradeForecaster()
