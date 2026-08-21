"""
Project Limbo — Smart Retry Budget Manager
Enforces merchant-bank rolling retry limits to protect long-term merchant approval standing.
"""

import time
import json
import random
import threading
from src_py import db
from src_py.config import BANK_PROFILES
from src_py.predictor import predictor

class RetryBudgetManager:
    def __init__(self):
        self.is_running = False
        self._thread = None

    def get_or_create_budget(self, merchant_id: str, issuing_bank: str) -> dict:
        budget = db.fetch_one(
            "SELECT * FROM retry_budgets WHERE merchant_id = ? AND issuing_bank = ?",
            (merchant_id, issuing_bank)
        )
        if not budget:
            profile = BANK_PROFILES.get(issuing_bank, BANK_PROFILES["HDFC"])
            daily_limit = profile["retry_budget"]["daily_limit_per_merchant"]

            db.execute(
                """INSERT INTO retry_budgets (merchant_id, issuing_bank, retries_used, retries_blocked, daily_limit)
                   VALUES (?, ?, 0, 0, ?)""",
                (merchant_id, issuing_bank, daily_limit)
            )

            budget = db.fetch_one(
                "SELECT * FROM retry_budgets WHERE merchant_id = ? AND issuing_bank = ?",
                (merchant_id, issuing_bank)
            )
        return budget

    def process_failed_transaction_retries(self):
        try:
            failed_txns = db.fetch_all(
                """SELECT * FROM transactions 
                   WHERE visible_status = 'failed' 
                     AND retry_count < 3 
                     AND action_taken NOT IN ('RETRY_BLOCKED', 'RECOVERED_BY_RETRY', 'MAX_RETRIES_EXCEEDED')"""
            )

            for txn in failed_txns:
                retry_score = predictor.score_retry_worthiness(txn)
                budget = self.get_or_create_budget(txn["merchant_id"], txn["issuing_bank"])

                db.execute("UPDATE transactions SET retry_score = ? WHERE id = ?", (retry_score, txn["id"]))

                is_budget_exhausted = budget["retries_used"] >= budget["daily_limit"]
                is_low_worthiness = retry_score < 0.45

                if is_budget_exhausted or is_low_worthiness:
                    # Block retry to protect merchant standing
                    db.execute("UPDATE transactions SET action_taken = 'RETRY_BLOCKED' WHERE id = ?", (txn["id"],))
                    db.execute(
                        "UPDATE retry_budgets SET retries_blocked = retries_blocked + 1 WHERE merchant_id = ? AND issuing_bank = ?",
                        (txn["merchant_id"], txn["issuing_bank"])
                    )

                    reason = "Merchant-Bank budget exhausted" if is_budget_exhausted else f"Low retry score (P={retry_score})"
                    meta = json.dumps({"retryScore": retry_score, "failureReason": txn["failure_reason"], "budgetUsed": budget["retries_used"]})

                    db.log_event(
                        txn["id"],
                        txn["merchant_id"],
                        "RETRY_BLOCKED",
                        f"Smart Retry Budgeting blocked retry for {txn['id']} on {txn['issuing_bank']}: {reason}. Merchant standing preserved.",
                        meta
                    )
                else:
                    # Execute smart retry
                    next_retry_count = txn["retry_count"] + 1

                    db.execute(
                        "UPDATE retry_budgets SET retries_used = retries_used + 1 WHERE merchant_id = ? AND issuing_bank = ?",
                        (txn["merchant_id"], txn["issuing_bank"])
                    )

                    retry_successful = random.random() < retry_score

                    if retry_successful:
                        db.execute(
                            "UPDATE transactions SET visible_status = 'success', retry_count = ?, action_taken = 'RECOVERED_BY_RETRY' WHERE id = ?",
                            (next_retry_count, txn["id"])
                        )

                        meta = json.dumps({"attempt": next_retry_count, "retryScore": retry_score, "recoveredAmount": txn["amount"]})
                        db.log_event(
                            txn["id"],
                            txn["merchant_id"],
                            "RETRY_EXECUTED",
                            f"Smart Retry SUCCESS! Recovered ₹{txn['amount']} on attempt #{next_retry_count} (Score: {retry_score}).",
                            meta
                        )
                    else:
                        action = "MAX_RETRIES_EXCEEDED" if next_retry_count >= 3 else "RETRY_FAILED"
                        db.execute(
                            "UPDATE transactions SET retry_count = ?, action_taken = ? WHERE id = ?",
                            (next_retry_count, action, txn["id"])
                        )

                        db.log_event(
                            txn["id"],
                            txn["merchant_id"],
                            "RETRY_EXECUTED",
                            f"Smart Retry Attempt #{next_retry_count} failed for {txn['id']} ({txn['issuing_bank']})."
                        )

        except Exception as e:
            print(f"Retry Budget Manager error: {e}")

    def _loop(self, interval_sec: float = 3.0):
        while self.is_running:
            self.process_failed_transaction_retries()
            time.sleep(interval_sec)

    def start(self, interval_sec: float = 3.0):
        if self.is_running:
            return
        self.is_running = True
        self._thread = threading.Thread(target=self._loop, args=(interval_sec,), daemon=True)
        self._thread.start()
        print("Retry Budget Manager started (Python background thread)")

    def stop(self):
        self.is_running = False
        print("Retry Budget Manager stopped")

retry_budget_manager = RetryBudgetManager()
