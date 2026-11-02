import numpy as np
from database.db import get_db_connection
import datetime

class GradeForecaster:
    def __init__(self):
        pass

    def _get_letter_grade(self, pct):
        """
        Standardized educational grading scale (matching system-wide benchmarks):
        A: 75% - 100% (Distinction)
        B: 65% - 74.9% (Very Good)
        C: 50% - 64.9% (Credit Pass)
        S: 35% - 49.9% (Simple Pass)
        F: Below 35%  (Needs Support / Fail)
        """
        if pct >= 75.0:
            return 'A'
        elif pct >= 65.0:
            return 'B'
        elif pct >= 50.0:
            return 'C'
        elif pct >= 35.0:
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

    def _calculate_target_pathway(self, curr_avg, scores):
        """
        Calculate required score on next exam to attain or sustain grade tiers:
        A: 75% | B: 65% | C: 50% | S: 35%
        """
        if not scores:
            return None

        n = len(scores)
        s = sum(scores)

        if curr_avg < 35.0:
            target_grade = 'S'
            target_thresh = 35.0
            is_maintain = False
        elif curr_avg < 50.0:
            target_grade = 'C'
            target_thresh = 50.0
            is_maintain = False
        elif curr_avg < 65.0:
            target_grade = 'B'
            target_thresh = 65.0
            is_maintain = False
        elif curr_avg < 75.0:
            target_grade = 'A'
            target_thresh = 75.0
            is_maintain = False
        else:
            target_grade = 'A'
            target_thresh = 75.0
            is_maintain = True

        needed = round(float((n + 1) * target_thresh - s), 1)

        if is_maintain:
            if needed <= 0.0:
                msg = "Firmly in Distinction: Normal passing exam sustains Grade A"
            else:
                msg = f"Maintain 'A': Score >= {needed}% on next exam"
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
                    SELECT m.student_id, m.class_id, m.marks_obtained, m.max_marks, m.date_recorded
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
                grouped[key].append(pct)

            errors = []
            within_10 = 0
            within_5 = 0

            for (sid, cid), scores in grouped.items():
                if len(scores) >= 3:
                    train_scores = scores[:-1]
                    actual = scores[-1]
                    c_avg = class_averages.get(cid, 65.0)

                    mock_timeline = [{'pct': s, 'date_obj': datetime.date.min} for s in train_scores]
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

    def _calculate_damped_prediction(self, exam_timeline, hw_timeline, class_avg):
        """
        Tier 1 Robust Statistical Forecast:
        1. Primary focus on supervised exam records.
        2. Recency-weighted Moving Average (recent exams have higher importance).
        3. Damped regression trend (prevents wild linear runaway extrapolation).
        4. Bayesian shrinkage towards class mean based on assessment count.
        5. Conservative auxiliary integration of homework effort.
        """
        exam_scores = [e['pct'] for e in exam_timeline]
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

        # Primary analysis is strictly on chronological exam assessments
        curr_avg = round(float(sum(exam_scores) / n_exams), 1)

        # 1. Single Exam: Bayesian shrinkage toward class mean
        if n_exams == 1:
            s0 = exam_scores[0]
            pred = (0.70 * s0) + (0.30 * class_avg)
            slope = 0.0
            trend_status = 'Stable Performance'
            trend_class = 'text-primary'

        # 2. Two Exams: Damped slope with recency weighting
        elif n_exams == 2:
            s0, s1 = exam_scores[0], exam_scores[1]
            raw_diff = s1 - s0
            # Recency-weighted average (60% test2, 40% test1)
            rec_avg = (0.60 * s1) + (0.40 * s0)
            # Damp the slope by 50% to prevent overreacting to 2-point variance
            damped_slope = raw_diff * 0.50
            # Clamp slope change to maximum +/- 8 points
            damped_slope = max(-8.0, min(8.0, damped_slope))

            raw_pred = rec_avg + damped_slope
            # Bayesian blend with class mean (80% personal, 20% class mean)
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

        # 3. Three or More Exams (N >= 3): Recency-Weighted Damped Linear Regression
        else:
            weights = np.array([1.0 + (0.35 * i) for i in range(n_exams)])
            weights /= weights.sum()
            x = np.arange(n_exams)
            y = np.array(exam_scores)

            x_bar = np.sum(weights * x)
            y_bar = np.sum(weights * y)

            denom = np.sum(weights * (x - x_bar) ** 2)
            if denom > 1e-6:
                raw_slope = float(np.sum(weights * (x - x_bar) * (y - y_bar)) / denom)
            else:
                raw_slope = 0.0

            # Slope damping scales with sample size (prevents runaway lines)
            damping = min(0.70, 0.30 + (0.05 * n_exams))
            damped_slope = raw_slope * damping
            # Prevent excessive single-step leaps: cap slope shift at +/- 10 points
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

        # 4. If homework exists, incorporate conservatively as an effort adjustment (10% weight)
        if n_hw > 0:
            hw_avg = sum(hw_scores) / n_hw
            pred = (0.90 * pred) + (0.10 * hw_avg)

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

    def forecast_student_performance(self, student_id, class_id=None, teacher_id=None, conn=None, class_averages=None):
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
                           m.test_name, m.marks_obtained, m.max_marks, m.date_recorded
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
                date_val = self._parse_date(m.get('date_recorded'))

                subject_data[cid]['exam_timeline'].append({
                    'name': m['test_name'],
                    'type': 'Exam',
                    'pct': pct,
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

                calc = self._calculate_damped_prediction(exam_timeline, hw_timeline, class_avg)
                if not calc:
                    continue

                curr_avg = calc['current_avg']
                predicted_pct = calc['predicted_pct']
                slope = calc['slope']
                trend_status = calc['trend_status']
                trend_class = calc['trend_class']
                scores = calc['all_scores']

                predicted_grade = self._get_letter_grade(predicted_pct)
                current_grade = self._get_letter_grade(curr_avg)

                conf = self._calculate_confidence(scores, calc['assessment_count'])
                margin = conf['margin']
                pred_low = round(max(0.0, predicted_pct - margin), 1)
                pred_high = round(min(100.0, predicted_pct + margin), 1)
                pathway = self._calculate_target_pathway(curr_avg, scores)

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

    def forecast_all_students(self, teacher_id=None, class_id=None):
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
                    class_averages=class_averages
                )
                if f_data and f_data['forecasts']:
                    results.append(f_data)

            return results
        finally:
            conn.close()

grade_forecaster = GradeForecaster()

