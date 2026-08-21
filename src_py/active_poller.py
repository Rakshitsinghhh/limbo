"""
Project Limbo — Active Status Check Polling Layer
Background worker scanning pending transactions exceeding expected windows,
flagging ambiguity, and querying bank status APIs at smart intervals.
"""

import time
import threading
from datetime import datetime
from src_py import db
from src_py.simulator import simulator
from src_py.predictor import predictor

class ActivePoller:
    def __init__(self):
        self.is_running = False
        self._thread = None

    def poll_pending_transactions(self):
        try:
            pending_txns = db.fetch_all("SELECT * FROM transactions WHERE visible_status = 'pending'")
            now = datetime.utcnow()

            for txn in pending_txns:
                debit_time = datetime.fromisoformat(txn["debit_timestamp"].replace('Z', ''))
                age_sec = (now - debit_time).total_seconds()

                # Step 1: Spot ambiguity early
                if age_sec > txn["expected_window_sec"] and txn["is_ambiguous"] == 0:
                    db.execute("UPDATE transactions SET is_ambiguous = 1 WHERE id = ?", (txn["id"],))
                    db.log_event(
                        txn["id"],
                        txn["merchant_id"],
                        "AMBIGUITY_FLAGGED",
                        f"Transaction {txn['id']} crossed confirmation window ({txn['expected_window_sec']}s). Flagged AMBIGUOUS."
                    )

                # Step 2 & 3: Predict probability & query status
                prob_score = predictor.predict_resolution_probability(txn)
                db.execute(
                    "UPDATE transactions SET probability_score = ?, last_polled_at = ? WHERE id = ?",
                    (prob_score, now.isoformat(), txn["id"])
                )

                bank_resp = simulator.query_bank_api(txn["id"])
                status = bank_resp.get("status")

                if status == "SUCCESS":
                    db.execute(
                        "UPDATE transactions SET visible_status = 'success', is_ambiguous = 0, action_taken = 'AUTO_RESOLVED_SUCCESS' WHERE id = ?",
                        (txn["id"],)
                    )
                    db.log_event(
                        txn["id"],
                        txn["merchant_id"],
                        "STATUS_POLLED",
                        f"Active polling confirmed resolution for {txn['id']}: SETTLED (P={prob_score})"
                    )
                elif status == "FAILED":
                    failure_reason = bank_resp.get("failure_reason", "BANK_TIMEOUT")
                    db.execute(
                        "UPDATE transactions SET visible_status = 'failed', is_ambiguous = 0, failure_reason = ? WHERE id = ?",
                        (failure_reason, txn["id"])
                    )
                    db.log_event(
                        txn["id"],
                        txn["merchant_id"],
                        "STATUS_POLLED",
                        f"Active polling confirmed failure for {txn['id']}: {failure_reason} (P={prob_score})"
                    )

        except Exception as e:
            print(f"Active Poller error: {e}")

    def _loop(self, interval_sec: float = 2.0):
        while self.is_running:
            self.poll_pending_transactions()
            time.sleep(interval_sec)

    def start(self, interval_sec: float = 2.0):
        if self.is_running:
            return
        self.is_running = True
        self._thread = threading.Thread(target=self._loop, args=(interval_sec,), daemon=True)
        self._thread.start()
        print("Active Poller started (Python background thread)")

    def stop(self):
        self.is_running = False
        print("Active Poller stopped")

active_poller = ActivePoller()
