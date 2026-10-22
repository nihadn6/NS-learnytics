import numpy as np
from sklearn.ensemble import RandomForestClassifier
from database.db import get_db_connection
import datetime

class StudentRiskPredictor:
    def __init__(self):
        # Initialize Random Forest Classifier
        self.model = RandomForestClassifier(n_estimators=50, random_state=42)
        self._is_trained = False
        self._bootstrap_model()

    def _bootstrap_model(self):
        """
        Train Random Forest model on synthesized training data representing
        typical student risk patterns (Attendance, Recent Attendance, Avg Marks, Mark Trend).
        Features: [attendance_pct, recent_att_pct, avg_mark_pct, mark_trend]
        Target: 0 = Low Risk, 1 = Medium Risk, 2 = High Risk / At-Risk Dropout
        """
        np.random.seed(42)
        n_samples = 300

        # Generate synthetic training observations
        att_pct = np.random.uniform(30, 100, n_samples)
        rec_att_pct = att_pct + np.random.uniform(-15, 15, n_samples)
        rec_att_pct = np.clip(rec_att_pct, 0, 100)
        
        avg_marks = np.random.uniform(20, 100, n_samples)
        mark_trend = np.random.uniform(-30, 30, n_samples)

        X = np.column_stack([att_pct, rec_att_pct, avg_marks, mark_trend])
        y = []

        for row in X:
            att, rec_att, marks, trend = row
            # Risk rules logic
            risk_score = 0
            if att < 60 or rec_att < 50:
                risk_score += 2
            elif att < 75:
                risk_score += 1

            if marks < 45:
                risk_score += 2
            elif marks < 60:
                risk_score += 1

            if trend < -15:
                risk_score += 1

            if risk_score >= 3:
                y.append(2) # High Risk
            elif risk_score >= 1:
                y.append(1) # Medium Risk
            else:
                y.append(0) # Low Risk

        self.model.fit(X, y)
        self._is_trained = True

    def predict_student_risk(self, student_id, class_id=None):
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                # 1. Fetch Student Details
                cursor.execute("SELECT id, name, email FROM users WHERE id = %s AND role = 'student'", (student_id,))
                student = cursor.fetchone()
                if not student:
                    return None

                class_info = None
                if class_id:
                    cursor.execute("""
                        SELECT c.id, c.subject, c.teacher_id, u.name as teacher_name 
                        FROM classes c
                        LEFT JOIN users u ON c.teacher_id = u.id
                        WHERE c.id = %s
                    """, (class_id,))
                    class_info = cursor.fetchone()

                # 2. Calculate Overall & Recent Attendance (Class-Isolated if class_id provided)
                if class_id:
                    cursor.execute("""
                        SELECT 
                            COUNT(*) as total_sessions,
                            SUM(CASE WHEN status = 'present' THEN 1 ELSE 0 END) as present_sessions,
                            SUM(CASE WHEN status = 'present' AND date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY) THEN 1 ELSE 0 END) as rec_present,
                            SUM(CASE WHEN date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY) THEN 1 ELSE 0 END) as rec_total
                        FROM attendance
                        WHERE student_id = %s AND class_id = %s
                    """, (student_id, class_id))
                else:
                    cursor.execute("""
                        SELECT 
                            COUNT(*) as total_sessions,
                            SUM(CASE WHEN status = 'present' THEN 1 ELSE 0 END) as present_sessions,
                            SUM(CASE WHEN status = 'present' AND date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY) THEN 1 ELSE 0 END) as rec_present,
                            SUM(CASE WHEN date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY) THEN 1 ELSE 0 END) as rec_total
                        FROM attendance
                        WHERE student_id = %s
                    """, (student_id,))
                att_data = cursor.fetchone()

                total_sess = float(att_data['total_sessions'] or 0)
                pres_sess = float(att_data['present_sessions'] or 0)
                att_pct = float(pres_sess / total_sess * 100.0) if total_sess > 0 else 100.0

                rec_total = float(att_data['rec_total'] or 0)
                rec_pres = float(att_data['rec_present'] or 0)
                rec_att_pct = float(rec_pres / rec_total * 100.0) if rec_total > 0 else att_pct

                # 3. Calculate Academic Performance & Trend (Class-Isolated if class_id provided)
                if class_id:
                    cursor.execute("""
                        SELECT marks_obtained, max_marks, date_recorded
                        FROM marks
                        WHERE student_id = %s AND class_id = %s
                        ORDER BY date_recorded ASC
                    """, (student_id, class_id))
                else:
                    cursor.execute("""
                        SELECT marks_obtained, max_marks, date_recorded
                        FROM marks
                        WHERE student_id = %s
                        ORDER BY date_recorded ASC
                    """, (student_id,))
                marks_rows = cursor.fetchall()

                if marks_rows:
                    scores = [(float(m['marks_obtained']) / float(m['max_marks']) * 100.0) for m in marks_rows]
                    avg_mark_pct = sum(scores) / len(scores)
                    if len(scores) >= 2:
                        recent_half = scores[len(scores)//2:]
                        first_half = scores[:len(scores)//2]
                        mark_trend = (sum(recent_half)/len(recent_half)) - (sum(first_half)/len(first_half))
                    else:
                        mark_trend = 0.0
                else:
                    avg_mark_pct = 75.0
                    mark_trend = 0.0

                # 4. Feature Vector Construction (Attendance + Academic Trajectory)
                features = np.array([[att_pct, rec_att_pct, avg_mark_pct, mark_trend]])
                probs = self.model.predict_proba(features)[0] # probabilities for [Low, Med, High]

                # Calculate Risk Percentage (weighted risk score)
                # Classes: 0 (Low), 1 (Med), 2 (High)
                high_prob = probs[2] if len(probs) > 2 else 0.0
                med_prob = probs[1] if len(probs) > 1 else 0.0
                risk_pct = round(float((high_prob * 1.0 + med_prob * 0.45) * 100), 1)

                # Determine Risk Level
                if risk_pct >= 55 or att_pct < 55 or avg_mark_pct < 45:
                    risk_level = 'HIGH'
                elif risk_pct >= 25 or att_pct < 75 or avg_mark_pct < 60:
                    risk_level = 'MEDIUM'
                else:
                    risk_level = 'LOW'

                # 5. Generate Actionable Risk Factors
                factors = []
                if att_pct < 65:
                    factors.append(f"Critical attendance ({att_pct:.1f}%)")
                elif att_pct < 75:
                    factors.append(f"Low attendance ({att_pct:.1f}%)")

                if rec_att_pct < att_pct - 10:
                    factors.append(f"Recent attendance drop ({rec_att_pct:.1f}% in 30d)")

                if avg_mark_pct < 50:
                    factors.append(f"Failing grade avg ({avg_mark_pct:.1f}%)")
                elif avg_mark_pct < 60:
                    factors.append(f"Below avg marks ({avg_mark_pct:.1f}%)")

                if mark_trend <= -10:
                    factors.append(f"Declining score trend ({mark_trend:.1f}%)")

                if not factors and risk_level == 'LOW':
                    factors.append("Consistent performance & attendance")

                return {
                    'student_id': student['id'],
                    'name': student['name'],
                    'email': student['email'],
                    'class_id': class_info['id'] if class_info else None,
                    'class_name': class_info['subject'] if class_info else None,
                    'teacher_id': class_info.get('teacher_id') if class_info else None,
                    'teacher_name': class_info.get('teacher_name') if class_info else None,
                    'attendance_pct': round(att_pct, 1),
                    'recent_attendance_pct': round(rec_att_pct, 1),
                    'avg_mark_pct': round(avg_mark_pct, 1),
                    'mark_trend': round(mark_trend, 1),
                    'risk_pct': risk_pct,
                    'risk_level': risk_level,
                    'risk_factors': factors
                }
        finally:
            conn.close()

    def get_all_student_risks(self, teacher_id=None, class_id=None):
        """Fetch risk analytics isolated per student-class enrollment"""
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                params = []
                if class_id and teacher_id:
                    query = """
                        SELECT e.student_id, e.class_id, c.subject as class_name, u.name as teacher_name
                        FROM enrollments e
                        JOIN classes c ON e.class_id = c.id
                        LEFT JOIN users u ON c.teacher_id = u.id
                        WHERE e.class_id = %s AND c.teacher_id = %s
                        ORDER BY c.subject, e.student_id
                    """
                    params.extend([class_id, teacher_id])
                elif class_id:
                    query = """
                        SELECT e.student_id, e.class_id, c.subject as class_name, u.name as teacher_name
                        FROM enrollments e
                        JOIN classes c ON e.class_id = c.id
                        LEFT JOIN users u ON c.teacher_id = u.id
                        WHERE e.class_id = %s
                        ORDER BY c.subject, e.student_id
                    """
                    params.append(class_id)
                elif teacher_id:
                    query = """
                        SELECT e.student_id, e.class_id, c.subject as class_name, u.name as teacher_name
                        FROM enrollments e
                        JOIN classes c ON e.class_id = c.id
                        LEFT JOIN users u ON c.teacher_id = u.id
                        WHERE c.teacher_id = %s
                        ORDER BY c.subject, e.student_id
                    """
                    params.append(teacher_id)
                else:
                    query = """
                        SELECT e.student_id, e.class_id, c.subject as class_name, u.name as teacher_name
                        FROM enrollments e
                        JOIN classes c ON e.class_id = c.id
                        LEFT JOIN users u ON c.teacher_id = u.id
                        ORDER BY c.subject, e.student_id
                    """

                cursor.execute(query, tuple(params))
                enrollments = cursor.fetchall()

            results = []
            for enr in enrollments:
                analysis = self.predict_student_risk(enr['student_id'], class_id=enr['class_id'])
                if analysis:
                    results.append(analysis)

            # Sort by highest risk score first
            results.sort(key=lambda x: x['risk_pct'], reverse=True)
            return results
        finally:
            conn.close()

# Singleton instance
risk_predictor = StudentRiskPredictor()
