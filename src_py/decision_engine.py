"""
Project Limbo — SLA-Aware Decision & Action Layer
Evaluates prediction confidence scores and SLA timelines to execute automated actions:
Quiet Wait, Proactive Customer Notification, or Automated Fund Reversal.
"""

import time
import json
import threading
from datetime import datetime
from src_py import db

class DecisionEngine:
    def __init__(self):
        self.is_running = False
        self._thread = None

    def process_limbo_decisions(self):
        try:
            ambiguous_txns = db.fetch_all("SELECT * FROM transactions WHERE visible_status = 'pending' AND is_ambiguous = 1")
            now = datetime.utcnow()

            for txn in ambiguous_txns:
                score = txn["probability_score"]
                sla_deadline = datetime.fromisoformat(txn["sla_deadline"].replace('Z', ''))
                
                is_near_sla = (sla_deadline - now).total_seconds() < txn["expected_window_sec"]
                is_sla_breached = now >= sla_deadline

                if score >= 0.75:
                    if txn["action_taken"] != "WAIT_QUIETLY":
                        db.execute("UPDATE transactions SET action_taken = 'WAIT_QUIETLY' WHERE id = ?", (txn["id"],))
                        db.log_event(
                            txn["id"],
                            txn["merchant_id"],
                            "DECISION_WAIT_QUIETLY",
                            f"High confidence (P={score}). Engine waiting quietly for bank confirmation on {txn['id']}."
                        )
                elif score >= 0.35 and is_near_sla:
                    if txn["action_taken"] != "NOTIFY_CUSTOMER":
                        db.execute("UPDATE transactions SET action_taken = 'NOTIFY_CUSTOMER' WHERE id = ?", (txn["id"],))
                        meta = json.dumps({"probability": score, "amount": txn["amount"], "bank": txn["issuing_bank"]})
                        db.log_event(
                            txn["id"],
                            txn["merchant_id"],
                            "NOTIFICATION_SENT",
                            f"Proactive SMS/Email dispatched to Customer {txn['customer_id']}: Payment of ₹{txn['amount']} is debited and being tracked with {txn['issuing_bank']}. No re-payment needed.",
                            meta
                        )
                elif score < 0.35 and is_sla_breached:
                    if txn["action_taken"] != "AUTO_REVERSAL":
                        db.execute("UPDATE transactions SET visible_status = 'reversed', action_taken = 'AUTO_REVERSAL', is_ambiguous = 0 WHERE id = ?", (txn["id"],))
                        meta = json.dumps({"probability": score, "amount": txn["amount"], "bank": txn["issuing_bank"]})
                        db.log_event(
                            txn["id"],
                            txn["merchant_id"],
                            "REVERSAL_TRIGGERED",
                            f"Low confidence (P={score}) & SLA breached. Reversal triggered automatically for {txn['id']} (₹{txn['amount']}). Customer refunded.",
                            meta
                        )

        except Exception as e:
            print(f"Decision Engine error: {e}")

    def _loop(self, interval_sec: float = 2.5):
        while self.is_running:
            self.process_limbo_decisions()
            time.sleep(interval_sec)

    def start(self, interval_sec: float = 2.5):
        if self.is_running:
            return
        self.is_running = True
        self._thread = threading.Thread(target=self._loop, args=(interval_sec,), daemon=True)
        self._thread.start()
        print("Decision Engine started (Python background thread)")

    def stop(self):
        self.is_running = False
        print("Decision Engine stopped")

decision_engine = DecisionEngine()
