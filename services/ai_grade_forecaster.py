import numpy as np
from database.db import get_db_connection
import datetime

DEFAULT_FORECAST_SETTINGS = {
    'preset_name': 'sri_lanka_national',
    'cutoff_a': 75.0,
    'cutoff_b': 65.0,
    'cutoff_c': 50.0,
    'cutoff_s': 35.0,
    'exam_weight': 0.90,
    'hw_weight': 0.10,
    'target_threshold': 50.0
}

FORECAST_PRESETS = {
    'sri_lanka_national': {
        'preset_name': 'sri_lanka_national',
        'title': 'Sri Lanka National G.C.E.',
        'cutoff_a': 75.0,
        'cutoff_b': 65.0,
        'cutoff_c': 50.0,
        'cutoff_s': 35.0,
        'exam_weight': 0.90,
        'hw_weight': 0.10,
        'target_threshold': 50.0
    },
    'cambridge_edexcel': {
        'preset_name': 'cambridge_edexcel',
        'title': 'Cambridge / Edexcel UK',
        'cutoff_a': 80.0,
        'cutoff_b': 70.0,
        'cutoff_c': 60.0,
        'cutoff_s': 40.0,
        'exam_weight': 0.85,
        'hw_weight': 0.15,
        'target_threshold': 60.0
    },
    'higher_ed_gpa': {
        'preset_name': 'higher_ed_gpa',
        'title': 'Higher Ed / Continuous Eval',
        'cutoff_a': 85.0,
        'cutoff_b': 70.0,
        'cutoff_c': 55.0,
        'cutoff_s': 45.0,
        'exam_weight': 0.75,
        'hw_weight': 0.25,
        'target_threshold': 55.0
    }
}

class GradeForecaster:
    def __init__(self):
        self._ensure_settings_table()

    def _ensure_settings_table(self):
        """Ensure the user_grade_forecast_settings table exists in database"""
        try:
            conn = get_db_connection()
            with conn.cursor() as cursor:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS user_grade_forecast_settings (
                        user_id INT PRIMARY KEY,
                        preset_name VARCHAR(50) DEFAULT 'sri_lanka_national',
                        cutoff_a FLOAT DEFAULT 75.0,
                        cutoff_b FLOAT DEFAULT 65.0,
                        cutoff_c FLOAT DEFAULT 50.0,
                        cutoff_s FLOAT DEFAULT 35.0,
                        exam_weight FLOAT DEFAULT 0.90,
                        hw_weight FLOAT DEFAULT 0.10,
                        target_threshold FLOAT DEFAULT 50.0,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                    );
                """)
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Warning: unable to ensure user_grade_forecast_settings table: {e}")

    def get_user_forecast_settings(self, user_id):
        """Retrieve stored grading forecast settings for a user, or return default settings"""
        if not user_id:
            return dict(DEFAULT_FORECAST_SETTINGS)
        try:
            conn = get_db_connection()
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM user_grade_forecast_settings WHERE user_id = %s", (user_id,))
                row = cursor.fetchone()
                if row:
                    return {
                        'preset_name': row.get('preset_name') or 'custom',
                        'cutoff_a': float(row.get('cutoff_a') if row.get('cutoff_a') is not None else 75.0),
                        'cutoff_b': float(row.get('cutoff_b') if row.get('cutoff_b') is not None else 65.0),
                        'cutoff_c': float(row.get('cutoff_c') if row.get('cutoff_c') is not None else 50.0),
                        'cutoff_s': float(row.get('cutoff_s') if row.get('cutoff_s') is not None else 35.0),
                        'exam_weight': float(row.get('exam_weight') if row.get('exam_weight') is not None else 0.90),
                        'hw_weight': float(row.get('hw_weight') if row.get('hw_weight') is not None else 0.10),
                        'target_threshold': float(row.get('target_threshold') if row.get('target_threshold') is not None else 50.0)
                    }
            conn.close()
        except Exception as e:
            print(f"Error fetching user_grade_forecast_settings for user {user_id}: {e}")
        return dict(DEFAULT_FORECAST_SETTINGS)

    def save_user_forecast_settings(self, user_id, settings):
        """Save customized grade thresholds & component weights for the given user"""
        if not user_id:
            return False
        try:
            conn = get_db_connection()
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO user_grade_forecast_settings
                    (user_id, preset_name, cutoff_a, cutoff_b, cutoff_c, cutoff_s, exam_weight, hw_weight, target_threshold)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        preset_name = VALUES(preset_name),
                        cutoff_a = VALUES(cutoff_a),
                        cutoff_b = VALUES(cutoff_b),
                        cutoff_c = VALUES(cutoff_c),
                        cutoff_s = VALUES(cutoff_s),
                        exam_weight = VALUES(exam_weight),
                        hw_weight = VALUES(hw_weight),
                        target_threshold = VALUES(target_threshold)
                """, (
                    user_id,
                    settings.get('preset_name', 'custom'),
                    float(settings.get('cutoff_a', 75.0)),
                    float(settings.get('cutoff_b', 65.0)),
                    float(settings.get('cutoff_c', 50.0)),
                    float(settings.get('cutoff_s', 35.0)),
                    float(settings.get('exam_weight', 0.90)),
                    float(settings.get('hw_weight', 0.10)),
                    float(settings.get('target_threshold', 50.0))
                ))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Error saving user_grade_forecast_settings for user {user_id}: {e}")
            return False

    def reset_user_forecast_settings(self, user_id):
        """Reset user grade forecasting settings to default"""
        if not user_id:
            return False
        try:
            conn = get_db_connection()
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM user_grade_forecast_settings WHERE user_id = %s", (user_id,))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Error resetting user_grade_forecast_settings for user {user_id}: {e}")
            return False

    def _get_letter_grade(self, pct, settings=None):
        """
        Determine letter grade using user customized or default scale cutoffs:
        A: >= cutoff_a (default 75.0%)
        B: >= cutoff_b (default 65.0%)
        C: >= cutoff_c (default 50.0%)
        S: >= cutoff_s (default 35.0%)
        F: < cutoff_s
        """
        cutoff_a = float(settings.get('cutoff_a', 75.0)) if settings else 75.0
        cutoff_b = float(settings.get('cutoff_b', 65.0)) if settings else 65.0
        cutoff_c = float(settings.get('cutoff_c', 50.0)) if settings else 50.0
        cutoff_s = float(settings.get('cutoff_s', 35.0)) if settings else 35.0

        if pct >= cutoff_a:
            return 'A'
        elif pct >= cutoff_b:
            return 'B'
        elif pct >= cutoff_c:
            return 'C'
        elif pct >= cutoff_s:
            return 'S'
        else:
            return 'F'

    def _parse_date(self, d):
        if not d:
            return datetime.date.min
        if isinstance(d, datetime.datetime):
            return d.date()
        if isinstance(d, datetime.date):
            return d
        try:
            return datetime.datetime.strptime(str(d)[:10], '%Y-%m-%d').date()
        except Exception:
            return datetime.date.min

    def _calculate_confidence(self, scores, n_assessments):
        """
        Determine confidence margin of error and reliability tier:
        - Sample size N (1 test is provisional, 4+ is highly reliable)
        - Variance / consistency of past scores
        """
        if not scores or n_assessments <= 0:
            return {
                'margin': 12.0,
                'level': 'LOW',
                'label': 'Developing Baseline',
                'badge_class': 'badge-warning',
                'star_count': 1
            }

        n = len(scores)
        std_dev = float(np.std(scores)) if n >= 2 else 0.0

        if n >= 4:
            base_margin = 4.5
            base_tier = 'HIGH'
        elif n == 3:
            base_margin = 6.5
            base_tier = 'MEDIUM'
        elif n == 2:
            base_margin = 8.5
            base_tier = 'MEDIUM'
        else:
            base_margin = 12.0
            base_tier = 'LOW'

        if std_dev > 15.0:
            variance_adj = 2.0
            if base_tier == 'HIGH':
                base_tier = 'MEDIUM'
        elif std_dev < 6.0 and n >= 3:
            variance_adj = -1.0
            base_tier = 'HIGH'
        else:
            variance_adj = 0.0

        margin = round(max(3.0, min(15.0, base_margin + variance_adj)), 1)

        if base_tier == 'HIGH':
            label = 'High Confidence'
            badge_class = 'badge-success'
            star_count = 3
        elif base_tier == 'MEDIUM':
            label = 'Moderate Confidence'
            badge_class = 'badge-primary'
            star_count = 2
        else:
            label = 'Developing Baseline'
            badge_class = 'badge-warning'
            star_count = 1

        return {
            'margin': margin,
            'level': base_tier,
            'label': label,
            'badge_class': badge_class,
            'star_count': star_count,
            'std_dev': round(std_dev, 1)
        }

    def _calculate_target_pathway(self, curr_avg, scores, settings=None):
        """
        Calculate required score on next exam to attain or sustain grade tiers
        based on user-configured or standard grade cutoffs.
        """
        if not scores:
            return None

        cutoff_a = float(settings.get('cutoff_a', 75.0)) if settings else 75.0
        cutoff_b = float(settings.get('cutoff_b', 65.0)) if settings else 65.0
        cutoff_c = float(settings.get('cutoff_c', 50.0)) if settings else 50.0
        cutoff_s = float(settings.get('cutoff_s', 35.0)) if settings else 35.0

        n = len(scores)
        s = sum(scores)

        if curr_avg < cutoff_s:
            target_grade = 'S'
            target_thresh = cutoff_s
            is_maintain = False
        elif curr_avg < cutoff_c:
            target_grade = 'C'
            target_thresh = cutoff_c
            is_maintain = False
        elif curr_avg < cutoff_b:
            target_grade = 'B'
            target_thresh = cutoff_b
            is_maintain = False
        elif curr_avg < cutoff_a:
            target_grade = 'A'
            target_thresh = cutoff_a
            is_maintain = False
        else:
            target_grade = 'A'
            target_thresh = cutoff_a
            is_maintain = True

        needed = round(float((n + 1) * target_thresh - s), 1)

        if is_maintain:
            if needed <= 0.0:
                msg = f"Firmly in Distinction: Normal passing exam sustains Grade {target_grade}"
            else:
                msg = f"Maintain '{target_grade}': Score >= {needed}% on next exam"
        else:
            if needed <= 0.0:
                msg = f"Target '{target_grade}': Already within reach with steady exam score"
            elif needed > 100.0:
                msg = f"Target '{target_grade}': Requires multi-exam upward trajectory"
            else:
                msg = f"Level Up to '{target_grade}': Needs {needed}% on next exam"

        return {
            'target_grade': target_grade,
            'needed_score': needed,
            'pathway_message': msg,
            'is_maintain': is_maintain
        }

    def evaluate_model_accuracy(self, teacher_id=None, class_id=None, conn=None):
        """
        Empirical leave-one-out historical backtest validation:
        Tests prediction accuracy on actual historical exams across students.
        """
        should_close = False
        if conn is None:
            conn = get_db_connection()
            should_close = True

        try:
            with conn.cursor() as cursor:
                query = """
                    SELECT m.student_id, m.class_id, m.marks_obtained, m.max_marks, m.weight_pct, m.date_recorded
                    FROM marks m
                    JOIN classes c ON m.class_id = c.id
                    WHERE m.max_marks > 0
                """
                params = []
                if class_id:
                    query += " AND m.class_id = %s"
                    params.append(class_id)
                if teacher_id:
                    query += " AND c.teacher_id = %s"
                    params.append(teacher_id)

                query += " ORDER BY m.student_id, m.class_id, m.date_recorded ASC"
                cursor.execute(query, tuple(params))
                rows = cursor.fetchall()

                class_averages = self._fetch_class_averages(cursor)

            grouped = {}
            for r in rows:
                key = (r['student_id'], r['class_id'])
                if key not in grouped:
                    grouped[key] = []
                pct = float(r['marks_obtained']) / float(r['max_marks']) * 100.0
                wt = float(r['weight_pct']) if r.get('weight_pct') is not None and float(r['weight_pct']) > 0 else 100.0
                grouped[key].append({'pct': pct, 'weight_pct': wt})

            errors = []
            within_10 = 0
            within_5 = 0

            for (sid, cid), score_items in grouped.items():
                if len(score_items) >= 3:
                    train_items = score_items[:-1]
                    actual = score_items[-1]['pct']
                    c_avg = class_averages.get(cid, 65.0)

                    mock_timeline = [{'pct': it['pct'], 'weight_pct': it['weight_pct'], 'date_obj': datetime.date.min} for it in train_items]
                    calc = self._calculate_damped_prediction(mock_timeline, [], c_avg)
                    if calc:
                        pred = calc['predicted_pct']
                        err = abs(pred - actual)
                        errors.append(err)
                        if err <= 10.0:
                            within_10 += 1
                        if err <= 5.0:
                            within_5 += 1

            if errors:
                mae = round(float(sum(errors) / len(errors)), 1)
                pct_10 = round(float(within_10 / len(errors) * 100.0), 1)
                pct_5 = round(float(within_5 / len(errors) * 100.0), 1)
                return {
                    'evaluated': True,
                    'sample_count': len(errors),
                    'mae': mae,
                    'within_10_pct': pct_10,
                    'within_5_pct': pct_5,
                    'badge_text': f"Empirical Accuracy: ±{mae}% MAE ({pct_10}% within ±10 pts)"
                }
            else:
                return {
                    'evaluated': False,
                    'sample_count': 0,
                    'mae': 0.0,
                    'within_10_pct': 0.0,
                    'within_5_pct': 0.0,
                    'badge_text': "Empirical Accuracy: Establishing Baseline"
                }
        finally:
            if should_close:
                conn.close()

    def _fetch_class_averages(self, cursor):
        """Fetch average exam score per class for Bayesian shrinkage calibration"""
        cursor.execute("""
            SELECT class_id, AVG(marks_obtained / max_marks * 100.0) as avg_pct
            FROM marks
            WHERE max_marks > 0
            GROUP BY class_id
        """)
        averages = {}
        for r in cursor.fetchall():
            if r['avg_pct'] is not None:
                averages[r['class_id']] = float(r['avg_pct'])
        return averages

    def _calculate_damped_prediction(self, exam_timeline, hw_timeline, class_avg, settings=None):
        """
        Tier 1 Robust Statistical Forecast:
        1. Primary focus on supervised exam records.
        2. Recency-weighted Moving Average (recent exams have higher importance).
        3. Damped regression trend (prevents wild linear runaway extrapolation).
        4. Bayesian shrinkage towards class mean based on assessment count.
        5. Conservative auxiliary integration of homework effort according to custom weights.
        """
        exam_scores = [e['pct'] for e in exam_timeline]
        exam_weights = [float(e.get('weight_pct', 100.0) or 100.0) for e in exam_timeline]
        hw_scores = [h['pct'] for h in hw_timeline]

        n_exams = len(exam_scores)
        n_hw = len(hw_scores)

        if n_exams == 0 and n_hw == 0:
            return None

        # Fallback if only homework exists (no supervised exams yet recorded)
        if n_exams == 0:
            hw_avg = sum(hw_scores) / n_hw
            pred = round(float(0.70 * (hw_avg * 0.88) + 0.30 * class_avg), 1)
            pred = max(0.0, min(100.0, pred))
            return {
                'predicted_pct': pred,
                'current_avg': round(float(hw_avg), 1),
                'slope': 0.0,
                'trend_status': 'Stable Performance',
                'trend_class': 'text-primary',
                'all_scores': hw_scores,
                'assessment_count': n_hw
            }

        # Weighted final grade average calculation across exams based on teacher assigned weights
        sum_weights = sum(exam_weights)
        if sum_weights > 0:
            curr_avg = round(float(sum(s * w for s, w in zip(exam_scores, exam_weights)) / sum_weights), 1)
        else:
            curr_avg = round(float(sum(exam_scores) / n_exams), 1)

        # 1. Single Exam: Bayesian shrinkage toward class mean
        if n_exams == 1:
            s0 = exam_scores[0]
            pred = (0.70 * s0) + (0.30 * class_avg)
            slope = 0.0
            trend_status = 'Stable Performance'
            trend_class = 'text-primary'

        # 2. Two Exams: Damped slope with recency + exam weight calibration
        elif n_exams == 2:
            s0, s1 = exam_scores[0], exam_scores[1]
            w0, w1 = exam_weights[0], exam_weights[1]
            tot_w = (w0 + w1) if (w0 + w1) > 0 else 200.0

            # Scale recency weights (0.40 & 0.60) by the teacher's exam weight ratio
            eff_w0 = 0.40 * (w0 / tot_w * 2.0)
            eff_w1 = 0.60 * (w1 / tot_w * 2.0)
            rec_avg = ((eff_w0 * s0) + (eff_w1 * s1)) / (eff_w0 + eff_w1)

            raw_diff = s1 - s0
            # Higher weight on exam 2 gives its trajectory pull greater impact
            weight_factor = min(1.5, max(0.5, (w1 / (tot_w / 2.0))))
            damped_slope = raw_diff * 0.50 * weight_factor
            damped_slope = max(-8.0, min(8.0, damped_slope))

            raw_pred = rec_avg + damped_slope
            pred = (0.80 * raw_pred) + (0.20 * class_avg)
            slope = round(damped_slope, 2)

            if slope >= 2.0:
                trend_status = 'Improving Trajectory'
                trend_class = 'text-success'
            elif slope <= -2.0:
                trend_status = 'Declining Trajectory'
                trend_class = 'text-danger'
            else:
                trend_status = 'Stable Performance'
                trend_class = 'text-primary'

        # 3. Three or More Exams (N >= 3): Recency-Weighted & Exam-Weighted Damped Linear Regression
        else:
            rec_weights = np.array([1.0 + (0.35 * i) for i in range(n_exams)])
            exam_w_arr = np.array(exam_weights, dtype=float)
            mean_w = np.mean(exam_w_arr) if np.mean(exam_w_arr) > 0 else 1.0
            norm_exam_weights = np.clip(exam_w_arr / mean_w, 0.25, 2.5)

            # Combined weight factor: both recency and exam weighting determine the slope and baseline
            combined_weights = rec_weights * norm_exam_weights
            combined_weights /= combined_weights.sum()

            x = np.arange(n_exams)
            y = np.array(exam_scores)

            x_bar = np.sum(combined_weights * x)
            y_bar = np.sum(combined_weights * y)

            denom = np.sum(combined_weights * (x - x_bar) ** 2)
            if denom > 1e-6:
                raw_slope = float(np.sum(combined_weights * (x - x_bar) * (y - y_bar)) / denom)
            else:
                raw_slope = 0.0

            # Slope damping scales with sample size (prevents runaway lines)
            damping = min(0.70, 0.30 + (0.05 * n_exams))
            damped_slope = raw_slope * damping
            damped_slope = max(-10.0, min(10.0, damped_slope))

            base_pred = y_bar + damped_slope

            # Bayesian shrinkage weight: more tests -> trust personal data more
            personal_weight = min(0.92, 0.70 + (0.04 * n_exams))
            pred = (personal_weight * base_pred) + ((1.0 - personal_weight) * class_avg)
            slope = round(damped_slope, 2)

            # Classify trajectory
            recent_avg = sum(exam_scores[-2:]) / 2.0
            if slope >= 1.5 and recent_avg >= curr_avg:
                trend_status = 'Improving Trajectory'
                trend_class = 'text-success'
            elif slope <= -1.5 and recent_avg <= curr_avg:
                trend_status = 'Declining Trajectory'
                trend_class = 'text-danger'
            else:
                trend_status = 'Stable Performance'
                trend_class = 'text-primary'

        # 4. If homework exists, incorporate according to user configured weights (default: 90% exam, 10% hw)
        exam_w = float(settings.get('exam_weight', 0.90)) if settings else 0.90
        hw_w = float(settings.get('hw_weight', 0.10)) if settings else 0.10
        total_w = exam_w + hw_w
        if total_w > 0:
            exam_w = exam_w / total_w
            hw_w = hw_w / total_w
        else:
            exam_w, hw_w = 0.90, 0.10

        if n_hw > 0 and hw_w > 0:
            hw_avg = sum(hw_scores) / n_hw
            pred = (exam_w * pred) + (hw_w * hw_avg)

        # Final bounding & rounding
        predicted_pct = round(max(0.0, min(100.0, float(pred))), 1)

        return {
            'predicted_pct': predicted_pct,
            'current_avg': curr_avg,
            'slope': slope,
            'trend_status': trend_status,
            'trend_class': trend_class,
            'all_scores': exam_scores,
            'assessment_count': n_exams
        }

    def forecast_student_performance(self, student_id, class_id=None, teacher_id=None, conn=None, class_averages=None, user_forecast_settings=None):
        should_close = False
        if conn is None:
            conn = get_db_connection()
            should_close = True

        try:
            with conn.cursor() as cursor:
                # Fetch Student
                cursor.execute("SELECT id, name, email FROM users WHERE id = %s AND role = 'student'", (student_id,))
                student = cursor.fetchone()
                if not student:
                    return None

                # Pre-fetch class averages if not provided
                if class_averages is None:
                    class_averages = self._fetch_class_averages(cursor)

                # Fetch Assessment Marks (chronologically sorted)
                query_marks = """
                    SELECT m.class_id, c.subject, c.teacher_id, u.name as teacher_name, 
                           m.test_name, m.marks_obtained, m.max_marks, m.weight_pct, m.date_recorded
                    FROM marks m
                    JOIN classes c ON m.class_id = c.id
                    LEFT JOIN users u ON c.teacher_id = u.id
                    WHERE m.student_id = %s
                """
                params = [student_id]
                if class_id:
                    query_marks += " AND m.class_id = %s"
                    params.append(class_id)
                if teacher_id:
                    query_marks += " AND c.teacher_id = %s"
                    params.append(teacher_id)
                query_marks += " ORDER BY m.date_recorded ASC"

                cursor.execute(query_marks, tuple(params))
                marks_rows = cursor.fetchall()

                # Fetch LMS homework scores (chronologically sorted)
                query_hw = """
                    SELECT a.class_id, c.subject, c.teacher_id, u.name as teacher_name, 
                           sub.marks_obtained, a.max_points, sub.submitted_at
                    FROM assignment_submissions sub
                    JOIN assignments a ON sub.assignment_id = a.id
                    JOIN classes c ON a.class_id = c.id
                    LEFT JOIN users u ON c.teacher_id = u.id
                    WHERE sub.student_id = %s AND sub.status = 'graded' AND sub.marks_obtained IS NOT NULL
                """
                hw_params = [student_id]
                if class_id:
                    query_hw += " AND a.class_id = %s"
                    hw_params.append(class_id)
                if teacher_id:
                    query_hw += " AND c.teacher_id = %s"
                    hw_params.append(teacher_id)
                query_hw += " ORDER BY sub.submitted_at ASC"

                cursor.execute(query_hw, tuple(hw_params))
                hw_rows = cursor.fetchall()

            # Group assessments by class
            subject_data = {}

            for m in marks_rows:
                cid = m['class_id']
                if cid not in subject_data:
                    subject_data[cid] = {
                        'subject': m['subject'],
                        'teacher_name': m.get('teacher_name', ''),
                        'teacher_id': m.get('teacher_id'),
                        'exam_timeline': [],
                        'hw_timeline': []
                    }

                max_pts = float(m['max_marks']) if m['max_marks'] else 100.0
                pts = float(m['marks_obtained']) if m['marks_obtained'] else 0.0
                pct = (pts / max_pts * 100.0) if max_pts > 0 else 0.0
                wt = float(m['weight_pct']) if m.get('weight_pct') is not None and float(m['weight_pct']) > 0 else 100.0
                date_val = self._parse_date(m.get('date_recorded'))

                subject_data[cid]['exam_timeline'].append({
                    'name': m['test_name'],
                    'type': 'Exam',
                    'pct': pct,
                    'weight_pct': wt,
                    'date': date_val.strftime('%Y-%m-%d') if date_val != datetime.date.min else '',
                    'date_obj': date_val
                })

            for h in hw_rows:
                cid = h['class_id']
                if cid not in subject_data:
                    subject_data[cid] = {
                        'subject': h['subject'],
                        'teacher_name': h.get('teacher_name', ''),
                        'teacher_id': h.get('teacher_id'),
                        'exam_timeline': [],
                        'hw_timeline': []
                    }

                max_pts = float(h['max_points']) if h['max_points'] else 100.0
                pts = float(h['marks_obtained']) if h['marks_obtained'] else 0.0
                pct = (pts / max_pts * 100.0) if max_pts > 0 else 0.0
                date_val = self._parse_date(h.get('submitted_at'))

                subject_data[cid]['hw_timeline'].append({
                    'name': 'LMS Homework',
                    'type': 'Assignment',
                    'pct': pct,
                    'date': date_val.strftime('%Y-%m-%d') if date_val != datetime.date.min else '',
                    'date_obj': date_val
                })

            forecasts = []

            for cid, sinfo in subject_data.items():
                exam_timeline = sinfo['exam_timeline']
                hw_timeline = sinfo['hw_timeline']

                # Sort each timeline strictly chronologically by date
                exam_timeline.sort(key=lambda t: t['date_obj'])
                hw_timeline.sort(key=lambda t: t['date_obj'])

                # Class benchmark fallback
                class_avg = class_averages.get(cid, 65.0)

                calc = self._calculate_damped_prediction(exam_timeline, hw_timeline, class_avg, settings=user_forecast_settings)
                if not calc:
                    continue

                curr_avg = calc['current_avg']
                predicted_pct = calc['predicted_pct']
                slope = calc['slope']
                trend_status = calc['trend_status']
                trend_class = calc['trend_class']
                scores = calc['all_scores']

                predicted_grade = self._get_letter_grade(predicted_pct, settings=user_forecast_settings)
                current_grade = self._get_letter_grade(curr_avg, settings=user_forecast_settings)

                conf = self._calculate_confidence(scores, calc['assessment_count'])
                margin = conf['margin']
                pred_low = round(max(0.0, predicted_pct - margin), 1)
                pred_high = round(min(100.0, predicted_pct + margin), 1)
                pathway = self._calculate_target_pathway(curr_avg, scores, settings=user_forecast_settings)

                forecasts.append({
                    'class_id': cid,
                    'subject': sinfo['subject'],
                    'teacher_name': sinfo.get('teacher_name', ''),
                    'teacher_id': sinfo.get('teacher_id'),
                    'historical_scores': scores,
                    'assessment_count': calc['assessment_count'],
                    'current_avg_pct': curr_avg,
                    'current_grade': current_grade,
                    'predicted_next_exam_pct': predicted_pct,
                    'predicted_final_grade': predicted_grade,
                    'pred_range_low': pred_low,
                    'pred_range_high': pred_high,
                    'confidence_margin': margin,
                    'confidence_level': conf['level'],
                    'confidence_label': conf['label'],
                    'confidence_badge': conf['badge_class'],
                    'confidence_stars': conf['star_count'],
                    'target_pathway': pathway,
                    'trend_slope': slope,
                    'trend_status': trend_status,
                    'trend_class': trend_class,
                    'class_avg_pct': round(class_avg, 1)
                })

            return {
                'student_id': student['id'],
                'name': student['name'],
                'email': student['email'],
                'forecasts': forecasts
            }
        finally:
            if should_close:
                conn.close()

    def forecast_all_students(self, teacher_id=None, class_id=None, user_forecast_settings=None):
        """Batch-optimized student forecasting with single connection reuse"""
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                # 1. Fetch class averages once for all students
                class_averages = self._fetch_class_averages(cursor)

                # 2. Fetch target student IDs
                query = "SELECT DISTINCT u.id FROM users u WHERE u.role = 'student'"
                params = []

                if class_id and teacher_id:
                    query = """
                        SELECT DISTINCT u.id 
                        FROM users u 
                        JOIN enrollments e ON u.id = e.student_id 
                        JOIN classes c ON e.class_id = c.id
                        WHERE u.role = 'student' AND e.class_id = %s AND c.teacher_id = %s
                    """
                    params.extend([class_id, teacher_id])
                elif class_id:
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

            # 3. Forecast using the shared connection
            results = []
            for sid in student_ids:
                f_data = self.forecast_student_performance(
                    sid, 
                    class_id=class_id, 
                    teacher_id=teacher_id, 
                    conn=conn, 
                    class_averages=class_averages,
                    user_forecast_settings=user_forecast_settings
                )
                if f_data and f_data['forecasts']:
                    results.append(f_data)

            return results
        finally:
            conn.close()

grade_forecaster = GradeForecaster()

