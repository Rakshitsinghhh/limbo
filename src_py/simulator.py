"""
Project Limbo — Payment Simulator Engine
Simulates NPCI and issuing bank infrastructure locally, generating realistic delayed (limbo)
and failed transactions with hidden true statuses and mock bank API queries.
"""

import random
import time
import json
import threading
from datetime import datetime, timedelta
from src_py.config import BANK_PROFILES
from src_py import db

MERCHANTS = ['MERCHANT_ALPHA', 'MERCHANT_BETA', 'MERCHANT_GAMMA', 'MERCHANT_DELTA']
BANKS = ['HDFC', 'SBI', 'ICICI', 'AXIS', 'KOTAK']
RAILS = ['UPI_AUTOPAY', 'NACH', 'CARD']
FAILURE_REASONS = ['INSUFFICIENT_FUNDS', 'BANK_TIMEOUT', 'RISK_DECLINE', 'NETWORK_ERROR']

class PaymentSimulator:
    def __init__(self):
        self.is_running = False
        self._thread = None

    def generate_random_transaction(self, custom_params: dict = None) -> dict:
        if custom_params is None:
            custom_params = {}

        bank_key = custom_params.get("bank") or random.choice(BANKS)
        rail = custom_params.get("rail") or random.choice(RAILS)
        merchant_id = custom_params.get("merchantId") or random.choice(MERCHANTS)
        amount = custom_params.get("amount") or random.randint(100, 4500)
        customer_id = custom_params.get("customerId") or f"CUST_{random.randint(10000, 99999)}"

        profile = BANK_PROFILES.get(bank_key, BANK_PROFILES["HDFC"])
        rail_config = profile["rails"].get(rail, profile["rails"]["UPI_AUTOPAY"])

        random_val = random.random()
        force_limbo = custom_params.get("forceLimbo", False)

        if not force_limbo and random_val < 0.65:
            # Instant Success
            visible_status = "success"
            true_status = "success"
            failure_reason = "NONE"
            delay_sec = 0
        elif not force_limbo and random_val < 0.75:
            # Instant Failure
            visible_status = "failed"
            true_status = "failed"
            failure_reason = random.choice(FAILURE_REASONS)
            delay_sec = 0
        else:
            # Limbo state (Delayed confirmation)
            visible_status = "pending"
            resolves_to_success = random.random() < rail_config["success_rate"]
            true_status = "success" if resolves_to_success else "failed"
            failure_reason = "NONE" if resolves_to_success else random.choice(FAILURE_REASONS)

            base_delay = rail_config["delay_mean_sec"] / 2.0
            delay_sec = int(base_delay * (0.5 + random.random()))

        now = datetime.utcnow()
        debit_timestamp = now.isoformat()
        expected_window_sec = rail_config["expected_window_sec"]
        
        sla_deadline = (now + timedelta(seconds=expected_window_sec * 2)).isoformat()
        true_resolution_time = (now + timedelta(seconds=delay_sec)).isoformat()

        txn_id = f"TXN_{int(time.time() * 1000)}_{random.randint(100, 999)}"

        return {
            "id": txn_id,
            "merchant_id": merchant_id,
            "customer_id": customer_id,
            "issuing_bank": bank_key,
            "rail": rail,
            "amount": float(amount),
            "visible_status": visible_status,
            "true_status": true_status,
            "failure_reason": failure_reason,
            "debit_timestamp": debit_timestamp,
            "expected_window_sec": expected_window_sec,
            "sla_deadline": sla_deadline,
            "true_resolution_time": true_resolution_time,
            "is_ambiguous": 0,
            "probability_score": 0.0,
            "retry_count": 0,
            "action_taken": "NONE"
        }

    def create_transaction(self, custom_params: dict = None) -> dict:
        txn = self.generate_random_transaction(custom_params)

        db.execute(
            """INSERT INTO transactions (
                id, merchant_id, customer_id, issuing_bank, rail, amount,
                visible_status, true_status, failure_reason, debit_timestamp,
                expected_window_sec, sla_deadline, true_resolution_time, is_ambiguous,
                probability_score, retry_count, action_taken
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                txn["id"], txn["merchant_id"], txn["customer_id"], txn["issuing_bank"], txn["rail"], txn["amount"],
                txn["visible_status"], txn["true_status"], txn["failure_reason"], txn["debit_timestamp"],
                txn["expected_window_sec"], txn["sla_deadline"], txn["true_resolution_time"], txn["is_ambiguous"],
                txn["probability_score"], txn["retry_count"], txn["action_taken"]
            )
        )

        db.log_event(
            txn["id"],
            txn["merchant_id"],
            "TRANSACTION_CREATED",
            f"Transaction {txn['id']} created via {txn['rail']} ({txn['issuing_bank']}) with status: {txn['visible_status'].upper()}"
        )

        return txn

    def query_bank_api(self, txn_id: str) -> dict:
        txn = db.fetch_one("SELECT * FROM transactions WHERE id = ?", (txn_id,))
        if not txn:
            return {"status": "NOT_FOUND"}

        now = datetime.utcnow()
        res_time = datetime.fromisoformat(txn["true_resolution_time"].replace('Z', ''))

        if now < res_time:
            return {
                "status": "PENDING_BANK_PROCESSING",
                "message": "Transaction debited at bank; awaiting settlement message"
            }
        else:
            return {
                "status": "SUCCESS" if txn["true_status"] == "success" else "FAILED",
                "failure_reason": txn["failure_reason"],
                "message": "Settled successfully" if txn["true_status"] == "success" else f"Declined: {txn['failure_reason']}"
            }

    def _loop(self, interval_sec: float = 3.0):
        while self.is_running:
            try:
                self.create_transaction()
            except Exception as e:
                print(f"Simulator error: {e}")
            time.sleep(interval_sec)

    def start(self, interval_sec: float = 3.0):
        if self.is_running:
            return
        self.is_running = True
        self._thread = threading.Thread(target=self._loop, args=(interval_sec,), daemon=True)
        self._thread.start()
        print("Payment Simulator started (Python background thread)")

    def stop(self):
        self.is_running = False
        print("Payment Simulator stopped")

simulator = PaymentSimulator()
