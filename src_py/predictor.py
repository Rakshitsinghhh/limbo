"""
Project Limbo — Machine Learning & Statistical Prediction Engine
Calculates self-resolution probability scores P(success) for limbo payments
and evaluates retry-worthiness scores P(retry_success) for failed payments.
"""

import math
from datetime import datetime
from src_py.config import BANK_PROFILES

class Predictor:
    def predict_resolution_probability(self, txn: dict) -> float:
        """
        Pillar 1 - Step 3: Calculates probability P(self-resolution) for pending limbo payments.
        """
        bank_key = txn.get("issuing_bank", "HDFC")
        rail = txn.get("rail", "UPI_AUTOPAY")

        profile = BANK_PROFILES.get(bank_key, BANK_PROFILES["HDFC"])
        rail_config = profile["rails"].get(rail, profile["rails"]["UPI_AUTOPAY"])

        base_success_rate = rail_config["success_rate"]

        debit_time = datetime.fromisoformat(txn["debit_timestamp"].replace('Z', ''))
        now = datetime.utcnow()
        age_sec = max(0, (now - debit_time).total_seconds())
        expected_window = txn["expected_window_sec"]

        # Exponential time decay factor when age exceeds normal confirmation window
        time_factor = 1.0
        if age_sec > expected_window:
            excess_sec = age_sec - expected_window
            lambda_val = 0.005 if rail == "UPI_AUTOPAY" else (0.01 if rail == "CARD" else 0.0001)
            time_factor = math.exp(-lambda_val * excess_sec)

        # Off-peak bank batch processing adjustment (1 AM - 4 AM)
        hour = debit_time.hour
        tod_factor = 0.90 if (1 <= hour <= 4) else 1.0

        score = base_success_rate * time_factor * tod_factor
        score = min(0.99, max(0.05, score))

        return round(score, 3)

    def score_retry_worthiness(self, txn: dict) -> float:
        """
        Pillar 2 - Step 1: Scores likelihood of success if a failed transaction is retried right now.
        """
        bank_key = txn.get("issuing_bank", "HDFC")
        failure_reason = txn.get("failure_reason") or "BANK_TIMEOUT"
        retry_count = txn.get("retry_count", 0)

        profile = BANK_PROFILES.get(bank_key, BANK_PROFILES["HDFC"])
        recovery_rates = profile.get("failure_recovery_rates", {})

        base_recovery = recovery_rates.get(failure_reason, 0.50)

        # Attempt decay multiplier: consecutive retries decrease likelihood of success
        attempt_decay = math.pow(0.65, retry_count)

        # Salary credit date boost (1st - 5th of month) for INSUFFICIENT_FUNDS
        now = datetime.utcnow()
        day_of_month = now.day
        salary_boost = 1.35 if (failure_reason == "INSUFFICIENT_FUNDS" and (day_of_month <= 5 or day_of_month >= 28)) else 1.0

        # Bank maintenance window penalty (1 AM - 3 AM)
        maintenance_penalty = 0.40 if (1 <= now.hour <= 3) else 1.0

        score = base_recovery * attempt_decay * salary_boost * maintenance_penalty
        score = min(0.98, max(0.02, score))

        return round(score, 3)

predictor = Predictor()
