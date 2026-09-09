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
        typical student risk patterns (Attendance, Recent Attendance, Avg Marks, Mark Trend, Missed Homework).
        Features: [attendance_pct, recent_att_pct, avg_mark_pct, mark_trend, missed_hw_ratio]
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
        missed_hw = np.random.uniform(0, 1.0, n_samples)

        X = np.column_stack([att_pct, rec_att_pct, avg_marks, mark_trend, missed_hw])
        y = []

        for row in X:
            att, rec_att, marks, trend, hw = row
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
            if hw > 0.5:
                risk_score += 1

            if risk_score >= 3:
                y.append(2) # High Risk
            elif risk_score >= 1:
                y.append(1) # Medium Risk
            else:
                y.append(0) # Low Risk

        self.model.fit(X, y)
        self._is_trained = True

    def predict_student_risk(self, student_id):
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                # 1. Fetch Student Details
                cursor.execute("SELECT id, name, email FROM users WHERE id = %s AND role = 'student'", (student_id,))
                student = cursor.fetchone()
                if not student:
                    return None

                # 2. Calculate Overall & Recent Attendance
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

                # 3. Calculate Academic Performance & Trend
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

                # 4. Check LMS Assignment Missed Ratio
                cursor.execute("""
                    SELECT 
                        COUNT(DISTINCT a.id) as total_assignments,
                        COUNT(DISTINCT s.assignment_id) as submitted_assignments
                    FROM enrollments e
                    JOIN assignments a ON e.class_id = a.class_id
                    LEFT JOIN assignment_submissions s ON a.id = s.assignment_id AND s.student_id = e.student_id
                    WHERE e.student_id = %s
                """, (student_id,))
                lms_data = cursor.fetchone()
                total_hw = float(lms_data['total_assignments'] or 0)
                sub_hw = float(lms_data['submitted_assignments'] or 0)
                missed_hw_ratio = (total_hw - sub_hw) / total_hw if total_hw > 0 else 0.0

                # 5. Feature Vector Construction
                features = np.array([[att_pct, rec_att_pct, avg_mark_pct, mark_trend, missed_hw_ratio]])
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

                # 6. Generate Actionable Risk Factors
                factors = []
                if att_pct < 65:
                    factors.append(f"Critical overall attendance ({att_pct:.1f}%)")
                elif att_pct < 75:
                    factors.append(f"Low overall attendance ({att_pct:.1f}%)")

                if rec_att_pct < att_pct - 10:
                    factors.append(f"Recent attendance drop ({rec_att_pct:.1f}% in 30 days)")

                if avg_mark_pct < 50:
                    factors.append(f"Failing grade average ({avg_mark_pct:.1f}%)")
                elif avg_mark_pct < 60:
                    factors.append(f"Below average exam performance ({avg_mark_pct:.1f}%)")

                if mark_trend <= -10:
                    factors.append(f"Declining score trend ({mark_trend:.1f}% trajectory)")

                if missed_hw_ratio >= 0.4:
                    factors.append(f"Missed {int(missed_hw_ratio*100)}% of LMS homework")

                if not factors and risk_level == 'LOW':
                    factors.append("Good academic & attendance track record")

                return {
                    'student_id': student['id'],
                    'name': student['name'],
                    'email': student['email'],
                    'attendance_pct': round(att_pct, 1),
                    'recent_attendance_pct': round(rec_att_pct, 1),
                    'avg_mark_pct': round(avg_mark_pct, 1),
                    'mark_trend': round(mark_trend, 1),
                    'missed_hw_ratio': round(missed_hw_ratio * 100, 1),
                    'risk_pct': risk_pct,
                    'risk_level': risk_level,
                    'risk_factors': factors
                }
        finally:
            conn.close()

    def get_all_student_risks(self, teacher_id=None, class_id=None):
        """Fetch risk analytics for all active students (or filtered by teacher/class)"""
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
                analysis = self.predict_student_risk(sid)
                if analysis:
                    results.append(analysis)

            # Sort by highest risk score first
            results.sort(key=lambda x: x['risk_pct'], reverse=True)
            return results
        finally:
            conn.close()

# Singleton instance
risk_predictor = StudentRiskPredictor()
