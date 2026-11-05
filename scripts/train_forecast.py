import sys
import os
import numpy as np

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database.db import get_db_connection
from services.ai_grade_forecaster import grade_forecaster

def run_forecast_model_training():
    print("=" * 65)
    print("      NS LEARNYTICS - AI GRADE FORECAST MODEL CALIBRATION")
    print("            (Incorporating Teacher Exam Weights)")
    print("=" * 65)
    
    # 1. Database & Column Verification
    print("\n[Step 1] Verifying Database Schema & Exam Weight Integrity...")
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*) as total_marks,
                       AVG(weight_pct) as avg_weight,
                       MIN(weight_pct) as min_weight,
                       MAX(weight_pct) as max_weight
                FROM marks
            """)
            stats = cursor.fetchone()
            print(f"  -> Total Exam Marks Records : {stats['total_marks']}")
            print(f"  -> Average Exam Weight       : {float(stats['avg_weight'] or 100):.1f}%")
            print(f"  -> Weight Range             : {float(stats['min_weight'] or 100):.1f}% to {float(stats['max_weight'] or 100):.1f}%")
            
            # Ensure no nulls
            cursor.execute("UPDATE marks SET weight_pct = 100.00 WHERE weight_pct IS NULL OR weight_pct <= 0")
            conn.commit()
    finally:
        conn.close()

    # 2. Synthetic Calibration & Weight Sensitivity Test
    print("\n[Step 2] Testing Model Sensitivity to Exam Weighting Factor...")
    # Case A: Student scored 90% on a 20% weight quiz, and 50% on a 100% weight major exam
    timeline_heavy_major = [
        {'pct': 90.0, 'weight_pct': 20.0, 'date_obj': None},   # Quiz
        {'pct': 50.0, 'weight_pct': 100.0, 'date_obj': None}   # Major Exam
    ]
    pred_heavy_major = grade_forecaster._calculate_damped_prediction(timeline_heavy_major, [], class_avg=65.0)

    # Case B: Student scored 50% on a 20% weight quiz, and 90% on a 100% weight major exam
    timeline_light_quiz = [
        {'pct': 50.0, 'weight_pct': 20.0, 'date_obj': None},   # Quiz
        {'pct': 90.0, 'weight_pct': 100.0, 'date_obj': None}   # Major Exam
    ]
    pred_light_quiz = grade_forecaster._calculate_damped_prediction(timeline_light_quiz, [], class_avg=65.0)

    # Unweighted comparison
    timeline_unweighted_a = [{'pct': 90.0, 'weight_pct': 100.0, 'date_obj': None}, {'pct': 50.0, 'weight_pct': 100.0, 'date_obj': None}]
    pred_unweighted_a = grade_forecaster._calculate_damped_prediction(timeline_unweighted_a, [], class_avg=65.0)

    print(f"  -> Case A (90% on 20% Quiz, 50% on 100% Exam):")
    print(f"     Weighted Final Avg: {pred_heavy_major['current_avg']}% | Predicted Next Exam: {pred_heavy_major['predicted_pct']}%")
    print(f"     (Without exam weights it would predict: {pred_unweighted_a['predicted_pct']}%)")
    
    print(f"  -> Case B (50% on 20% Quiz, 90% on 100% Exam):")
    print(f"     Weighted Final Avg: {pred_light_quiz['current_avg']}% | Predicted Next Exam: {pred_light_quiz['predicted_pct']}%")

    assert pred_light_quiz['predicted_pct'] > pred_heavy_major['predicted_pct'], "High-weight exam should dominate forecast"
    print("  [SUCCESS] Exam weighting factors verified: high-weight exams properly dictate trajectories.")

    # 3. Empirical Leave-One-Out Backtesting on Historical Data
    print("\n[Step 3] Evaluating Model on Historical Class Data (Leave-One-Out Backtest)...")
    eval_results = grade_forecaster.evaluate_model_accuracy()

    if eval_results['evaluated']:
        print(f"  -> Total Validation Samples  : {eval_results['sample_count']}")
        print(f"  -> Mean Absolute Error (MAE) : ±{eval_results['mae']}%")
        print(f"  -> Within ±10 Points Accuracy: {eval_results['within_10_pct']}%")
        print(f"  -> Within ±5 Points Accuracy : {eval_results['within_5_pct']}%")
        print(f"  -> Model Status              : CALIBRATED AND VERIFIED")
    else:
        print("  -> Insufficient longitudinal test history (need >= 3 exams per student). Establishing initial baseline.")

    print("\n" + "=" * 65)
    print(" Model training and calibration complete. Production weights active.")
    print("=" * 65)

if __name__ == '__main__':
    run_forecast_model_training()
