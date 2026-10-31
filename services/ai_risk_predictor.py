import numpy as np
from sklearn.ensemble import RandomForestClassifier
from database.db import get_db_connection
import datetime

DEFAULT_RISK_SETTINGS = {
    'preset_name': 'balanced',
    'att_weight': 0.40,
    'marks_weight': 0.40,
    'rec_att_weight': 0.10,
    'trend_weight': 0.10,
    'min_attendance_threshold': 75.0,
    'min_marks_threshold': 50.0,
    'high_risk_threshold': 55.0,
    'medium_risk_threshold': 25.0
}

PRESETS = {
    'balanced': {
        'preset_name': 'balanced',
        'att_weight': 0.40,
        'marks_weight': 0.40,
        'rec_att_weight': 0.10,
        'trend_weight': 0.10,
        'min_attendance_threshold': 75.0,
        'min_marks_threshold': 50.0,
        'high_risk_threshold': 55.0,
        'medium_risk_threshold': 25.0
    },
    'exam_heavy': {
        'preset_name': 'exam_heavy',
        'att_weight': 0.20,
        'marks_weight': 0.55,
        'rec_att_weight': 0.05,
        'trend_weight': 0.20,
        'min_attendance_threshold': 65.0,
        'min_marks_threshold': 55.0,
        'high_risk_threshold': 55.0,
        'medium_risk_threshold': 25.0
    },
    'attendance_strict': {
        'preset_name': 'attendance_strict',
        'att_weight': 0.55,
        'marks_weight': 0.20,
        'rec_att_weight': 0.20,
        'trend_weight': 0.05,
        'min_attendance_threshold': 80.0,
        'min_marks_threshold': 45.0,
        'high_risk_threshold': 50.0,
        'medium_risk_threshold': 25.0
    }
}

class StudentRiskPredictor:
    def __init__(self):
        # Initialize Random Forest Classifier
        self.model = RandomForestClassifier(n_estimators=50, random_state=42)
        self._is_trained = False
        self._bootstrap_model()
        self._ensure_settings_table()

    def _ensure_settings_table(self):
        """Ensure the user_risk_settings table exists in database"""
        try:
            conn = get_db_connection()
            with conn.cursor() as cursor:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS user_risk_settings (
                        user_id INT PRIMARY KEY,
                        preset_name VARCHAR(50) DEFAULT 'balanced',
                        att_weight FLOAT DEFAULT 0.40,
                        marks_weight FLOAT DEFAULT 0.40,
                        rec_att_weight FLOAT DEFAULT 0.10,
                        trend_weight FLOAT DEFAULT 0.10,
                        min_attendance_threshold FLOAT DEFAULT 75.0,
                        min_marks_threshold FLOAT DEFAULT 50.0,
                        high_risk_threshold FLOAT DEFAULT 55.0,
                        medium_risk_threshold FLOAT DEFAULT 25.0,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                    );
                """)
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Warning: unable to ensure user_risk_settings table: {e}")

    def get_user_risk_settings(self, user_id):
        """Retrieve stored risk settings for a teacher or admin, or return default balanced settings"""
        if not user_id:
            return dict(DEFAULT_RISK_SETTINGS)
        try:
            conn = get_db_connection()
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM user_risk_settings WHERE user_id = %s", (user_id,))
                row = cursor.fetchone()
                if row:
                    return {
                        'preset_name': row.get('preset_name') or 'custom',
                        'att_weight': float(row.get('att_weight') if row.get('att_weight') is not None else 0.40),
                        'marks_weight': float(row.get('marks_weight') if row.get('marks_weight') is not None else 0.40),
                        'rec_att_weight': float(row.get('rec_att_weight') if row.get('rec_att_weight') is not None else 0.10),
                        'trend_weight': float(row.get('trend_weight') if row.get('trend_weight') is not None else 0.10),
                        'min_attendance_threshold': float(row.get('min_attendance_threshold') if row.get('min_attendance_threshold') is not None else 75.0),
                        'min_marks_threshold': float(row.get('min_marks_threshold') if row.get('min_marks_threshold') is not None else 50.0),
                        'high_risk_threshold': float(row.get('high_risk_threshold') if row.get('high_risk_threshold') is not None else 55.0),
                        'medium_risk_threshold': float(row.get('medium_risk_threshold') if row.get('medium_risk_threshold') is not None else 25.0)
                    }
            conn.close()
        except Exception as e:
            print(f"Error fetching user_risk_settings for user {user_id}: {e}")
        return dict(DEFAULT_RISK_SETTINGS)

    def save_user_risk_settings(self, user_id, settings):
        """Save customized risk parameters for the given user"""
        if not user_id:
            return False
        try:
            conn = get_db_connection()
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO user_risk_settings 
                    (user_id, preset_name, att_weight, marks_weight, rec_att_weight, trend_weight, 
                     min_attendance_threshold, min_marks_threshold, high_risk_threshold, medium_risk_threshold)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        preset_name = VALUES(preset_name),
                        att_weight = VALUES(att_weight),
                        marks_weight = VALUES(marks_weight),
                        rec_att_weight = VALUES(rec_att_weight),
                        trend_weight = VALUES(trend_weight),
                        min_attendance_threshold = VALUES(min_attendance_threshold),
                        min_marks_threshold = VALUES(min_marks_threshold),
                        high_risk_threshold = VALUES(high_risk_threshold),
                        medium_risk_threshold = VALUES(medium_risk_threshold)
                """, (
                    user_id,
                    settings.get('preset_name', 'custom'),
                    float(settings.get('att_weight', 0.40)),
                    float(settings.get('marks_weight', 0.40)),
                    float(settings.get('rec_att_weight', 0.10)),
                    float(settings.get('trend_weight', 0.10)),
                    float(settings.get('min_attendance_threshold', 75.0)),
                    float(settings.get('min_marks_threshold', 50.0)),
                    float(settings.get('high_risk_threshold', 55.0)),
                    float(settings.get('medium_risk_threshold', 25.0))
                ))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Error saving user_risk_settings for user {user_id}: {e}")
            return False

    def reset_user_risk_settings(self, user_id):
        """Reset user risk settings to defaults"""
        if not user_id:
            return False
        try:
            conn = get_db_connection()
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM user_risk_settings WHERE user_id = %s", (user_id,))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Error resetting user_risk_settings for user {user_id}: {e}")
            return False


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

    def predict_student_risk(self, student_id, class_id=None, settings=None):
        if settings is None:
            settings = DEFAULT_RISK_SETTINGS

        w_att = float(settings.get('att_weight', 0.40))
        w_marks = float(settings.get('marks_weight', 0.40))
        w_rec = float(settings.get('rec_att_weight', 0.10))
        w_trend = float(settings.get('trend_weight', 0.10))
        min_att = float(settings.get('min_attendance_threshold', 75.0))
        min_marks = float(settings.get('min_marks_threshold', 50.0))
        high_cutoff = float(settings.get('high_risk_threshold', 55.0))
        med_cutoff = float(settings.get('medium_risk_threshold', 25.0))

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

                # 4. Custom Weighted Score + ML Feature Calibration
                att_deficit = max(0.0, min(100.0, 100.0 - att_pct))
                rec_att_deficit = max(0.0, min(100.0, 100.0 - rec_att_pct))
                marks_deficit = max(0.0, min(100.0, 100.0 - avg_mark_pct))
                trend_deficit = max(0.0, min(100.0, -mark_trend * 2.5)) if mark_trend < 0 else 0.0

                total_w = w_att + w_marks + w_rec + w_trend
                if total_w <= 0:
                    total_w = 1.0
                nw_att = w_att / total_w
                nw_marks = w_marks / total_w
                nw_rec = w_rec / total_w
                nw_trend = w_trend / total_w

                custom_score = (nw_att * att_deficit) + (nw_marks * marks_deficit) + (nw_rec * rec_att_deficit) + (nw_trend * trend_deficit)

                features = np.array([[att_pct, rec_att_pct, avg_mark_pct, mark_trend]])
                probs = self.model.predict_proba(features)[0] # probabilities for [Low, Med, High]
                high_prob = probs[2] if len(probs) > 2 else 0.0
                med_prob = probs[1] if len(probs) > 1 else 0.0
                ml_score = (high_prob * 1.0 + med_prob * 0.45) * 100.0

                # Blended risk percentage honoring teacher weights (70%) with ML adjustment (30%)
                raw_risk = (0.70 * custom_score) + (0.30 * ml_score)
                risk_pct = round(float(max(0.0, min(100.0, raw_risk))), 1)

                # 5. Determine Risk Level using teacher's custom thresholds
                is_critical_att = att_pct < max(35.0, min_att - 15.0)
                is_critical_marks = avg_mark_pct < max(30.0, min_marks - 10.0)

                if risk_pct >= high_cutoff or is_critical_att or is_critical_marks:
                    risk_level = 'HIGH'
                elif risk_pct >= med_cutoff or att_pct < min_att or avg_mark_pct < min_marks:
                    risk_level = 'MEDIUM'
                else:
                    risk_level = 'LOW'

                # 6. Generate Actionable Risk Factors customized to teacher's thresholds
                factors = []
                if is_critical_att:
                    factors.append(f"Critical attendance ({att_pct:.1f}% vs {min_att:.0f}% target)")
                elif att_pct < min_att:
                    factors.append(f"Low attendance ({att_pct:.1f}% vs {min_att:.0f}% target)")

                if rec_att_pct < att_pct - 10:
                    factors.append(f"Recent attendance drop ({rec_att_pct:.1f}% in 30d)")

                if is_critical_marks:
                    factors.append(f"Failing grade avg ({avg_mark_pct:.1f}% vs {min_marks:.0f}% target)")
                elif avg_mark_pct < min_marks:
                    factors.append(f"Below target marks ({avg_mark_pct:.1f}% vs {min_marks:.0f}% target)")

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

    def get_all_student_risks(self, teacher_id=None, class_id=None, user_risk_settings=None):
        """Fetch risk analytics isolated per student-class enrollment with custom risk preferences"""
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
                analysis = self.predict_student_risk(enr['student_id'], class_id=enr['class_id'], settings=user_risk_settings)
                if analysis:
                    results.append(analysis)

            # Sort by highest risk score first
            results.sort(key=lambda x: x['risk_pct'], reverse=True)
            return results
        finally:
            conn.close()

# Singleton instance
risk_predictor = StudentRiskPredictor()
