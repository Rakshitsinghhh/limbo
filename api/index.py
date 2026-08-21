"""
Vercel Serverless Function Handler for Project Limbo API
Uses BaseHTTPRequestHandler class handler expected by @vercel/python builder.
"""

from http.server import BaseHTTPRequestHandler
import sys
import os
import json
import random
import traceback
import urllib.parse
from datetime import datetime, timedelta

# Configure SQLite DB path for Vercel writeable /tmp filesystem
os.environ["DB_PATH"] = "/tmp/limbo.db"

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src_py import db
from src_py.simulator import simulator
from src_py.active_poller import active_poller
from src_py.decision_engine import decision_engine
from src_py.retry_budget import retry_budget_manager

def seed_deterministic_baseline():
    count_row = db.fetch_one("SELECT COUNT(*) as count FROM transactions")
    if count_row and count_row["count"] > 0:
        return

    random.seed(42)
    now = datetime.utcnow()

    baseline_txns = [
        {"id": "TXN_1001_HDFC", "merchant_id": "MERCHANT_ALPHA", "customer_id": "CUST_88412", "issuing_bank": "HDFC", "rail": "UPI_AUTOPAY", "amount": 1450.0, "visible_status": "success", "true_status": "success", "failure_reason": "NONE", "expected_window_sec": 30, "is_ambiguous": 0, "probability_score": 0.92, "retry_count": 0, "action_taken": "NONE"},
        {"id": "TXN_1002_SBI", "merchant_id": "MERCHANT_BETA", "customer_id": "CUST_34190", "issuing_bank": "SBI", "rail": "NACH", "amount": 3200.0, "visible_status": "pending", "true_status": "success", "failure_reason": "NONE", "expected_window_sec": 14400, "is_ambiguous": 1, "probability_score": 0.68, "retry_count": 0, "action_taken": "NOTIFY_CUSTOMER"},
        {"id": "TXN_1003_ICICI", "merchant_id": "MERCHANT_ALPHA", "customer_id": "CUST_90214", "issuing_bank": "ICICI", "rail": "CARD", "amount": 2150.0, "visible_status": "success", "true_status": "success", "failure_reason": "NONE", "expected_window_sec": 15, "is_ambiguous": 0, "probability_score": 0.95, "retry_count": 1, "action_taken": "RECOVERED_BY_RETRY"},
        {"id": "TXN_1004_SBI", "merchant_id": "MERCHANT_DELTA", "customer_id": "CUST_11029", "issuing_bank": "SBI", "rail": "UPI_AUTOPAY", "amount": 1850.0, "visible_status": "pending", "true_status": "success", "failure_reason": "NONE", "expected_window_sec": 45, "is_ambiguous": 1, "probability_score": 0.84, "retry_count": 0, "action_taken": "WAIT_QUIETLY"},
        {"id": "TXN_1005_AXIS", "merchant_id": "MERCHANT_GAMMA", "customer_id": "CUST_77412", "issuing_bank": "AXIS", "rail": "CARD", "amount": 980.0, "visible_status": "reversed", "true_status": "failed", "failure_reason": "BANK_TIMEOUT", "expected_window_sec": 18, "is_ambiguous": 0, "probability_score": 0.22, "retry_count": 0, "action_taken": "AUTO_REVERSAL"},
        {"id": "TXN_1006_KOTAK", "merchant_id": "MERCHANT_ALPHA", "customer_id": "CUST_55198", "issuing_bank": "KOTAK", "rail": "NACH", "amount": 4100.0, "visible_status": "success", "true_status": "success", "failure_reason": "NONE", "expected_window_sec": 6000, "is_ambiguous": 0, "probability_score": 0.88, "retry_count": 0, "action_taken": "NONE"},
        {"id": "TXN_1007_HDFC", "merchant_id": "MERCHANT_BETA", "customer_id": "CUST_66301", "issuing_bank": "HDFC", "rail": "CARD", "amount": 1250.0, "visible_status": "failed", "true_status": "failed", "failure_reason": "INSUFFICIENT_FUNDS", "expected_window_sec": 15, "is_ambiguous": 0, "probability_score": 0.15, "retry_count": 1, "action_taken": "RETRY_BLOCKED"},
        {"id": "TXN_1008_SBI", "merchant_id": "MERCHANT_GAMMA", "customer_id": "CUST_44910", "issuing_bank": "SBI", "rail": "UPI_AUTOPAY", "amount": 2750.0, "visible_status": "pending", "true_status": "success", "failure_reason": "NONE", "expected_window_sec": 45, "is_ambiguous": 1, "probability_score": 0.76, "retry_count": 0, "action_taken": "WAIT_QUIETLY"},
        {"id": "TXN_1009_ICICI", "merchant_id": "MERCHANT_DELTA", "customer_id": "CUST_22891", "issuing_bank": "ICICI", "rail": "UPI_AUTOPAY", "amount": 3400.0, "visible_status": "success", "true_status": "success", "failure_reason": "NONE", "expected_window_sec": 25, "is_ambiguous": 0, "probability_score": 0.91, "retry_count": 1, "action_taken": "RECOVERED_BY_RETRY"}
    ]

    for t in baseline_txns:
        debit_time = (now - timedelta(minutes=random.randint(2, 60))).isoformat()
        sla_time = (now + timedelta(seconds=t["expected_window_sec"] * 2)).isoformat()
        true_res_time = (now + timedelta(seconds=120)).isoformat()

        db.execute(
            """INSERT INTO transactions (
                id, merchant_id, customer_id, issuing_bank, rail, amount,
                visible_status, true_status, failure_reason, debit_timestamp,
                expected_window_sec, sla_deadline, true_resolution_time, is_ambiguous,
                probability_score, retry_count, action_taken
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                t["id"], t["merchant_id"], t["customer_id"], t["issuing_bank"], t["rail"], t["amount"],
                t["visible_status"], t["true_status"], t["failure_reason"], debit_time,
                t["expected_window_sec"], sla_time, true_res_time, t["is_ambiguous"],
                t["probability_score"], t["retry_count"], t["action_taken"]
            )
        )

    db.log_event("TXN_1002_SBI", "MERCHANT_BETA", "NOTIFICATION_SENT", "Proactive SMS/Email dispatched to Customer CUST_34190: Payment ₹3200 debited, tracked with SBI.")
    db.log_event("TXN_1003_ICICI", "MERCHANT_ALPHA", "RETRY_EXECUTED", "Smart Retry SUCCESS! Recovered ₹2150 on attempt #1.")
    db.log_event("TXN_1005_AXIS", "MERCHANT_GAMMA", "REVERSAL_TRIGGERED", "Low confidence & SLA breached. Reversal triggered automatically for TXN_1005_AXIS (₹980).")
    db.log_event("TXN_1007_HDFC", "MERCHANT_BETA", "RETRY_BLOCKED", "Smart Retry Budgeting blocked retry for TXN_1007_HDFC on HDFC. Merchant approval rating preserved.")

    random.seed()

def ensure_initialized():
    db.init_db()
    seed_deterministic_baseline()

class handler(BaseHTTPRequestHandler):
    def send_json_response(self, status_code: int, data: any):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS, HEAD")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS, HEAD")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        try:
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path
            query = urllib.parse.parse_qs(parsed.query)

            ensure_initialized()
            
            try:
                active_poller.poll_pending_transactions()
                decision_engine.process_limbo_decisions()
                retry_budget_manager.process_failed_transaction_retries()
            except Exception as step_err:
                print("Engine step warning:", step_err)

            if path.endswith("/stats") or path.endswith("/api/stats"):
                total_txns = db.fetch_one("SELECT COUNT(*) as count FROM transactions")["count"]
                pending_limbo = db.fetch_one("SELECT COUNT(*) as count FROM transactions WHERE visible_status = 'pending'")["count"]
                auto_resolved = db.fetch_one("SELECT COUNT(*) as count FROM transactions WHERE action_taken IN ('AUTO_RESOLVED_SUCCESS', 'WAIT_QUIETLY') OR visible_status = 'success'")["count"]
                notifications = db.fetch_one("SELECT COUNT(*) as count FROM event_logs WHERE event_type = 'NOTIFICATION_SENT'")["count"]
                reversals = db.fetch_one("SELECT COUNT(*) as count FROM event_logs WHERE event_type = 'REVERSAL_TRIGGERED'")["count"]
                retries_blocked = db.fetch_one("SELECT COUNT(*) as count FROM event_logs WHERE event_type = 'RETRY_BLOCKED'")["count"]
                rev_row = db.fetch_one("SELECT SUM(amount) as total FROM transactions WHERE action_taken = 'RECOVERED_BY_RETRY'")
                revenue = rev_row["total"] if rev_row and rev_row["total"] else 0.0

                total_retries = db.fetch_one("SELECT COUNT(*) as count FROM event_logs WHERE event_type IN ('RETRY_EXECUTED', 'RETRY_BLOCKED')")["count"]
                approval_standing = min(99.4, 85.0 + (retries_blocked / total_retries) * 14.4) if total_retries > 0 else 98.2

                data = {
                    "totalTransactions": total_txns,
                    "limboPending": pending_limbo,
                    "autoResolvedCount": auto_resolved,
                    "notificationsSent": notifications,
                    "reversalsTriggered": reversals,
                    "retriesBlocked": retries_blocked,
                    "revenueRecoveredAmount": round(revenue, 2),
                    "avgLimboResolutionSec": 42,
                    "merchantApprovalStanding": round(approval_standing, 1),
                    "isSimulatorRunning": True
                }
                self.send_json_response(200, data)

            elif path.endswith("/transactions") or path.endswith("/api/transactions"):
                status_filter = query.get("status", ["all"])[0]
                bank_filter = query.get("bank", ["all"])[0]
                limit = int(query.get("limit", [50])[0])

                sql = "SELECT * FROM transactions"
                conditions = []
                params = []

                if status_filter != "all":
                    conditions.append("visible_status = ?")
                    params.append(status_filter)

                if bank_filter != "all":
                    conditions.append("issuing_bank = ?")
                    params.append(bank_filter)

                if conditions:
                    sql += " WHERE " + " AND ".join(conditions)

                sql += " ORDER BY created_at DESC LIMIT ?"
                params.append(limit)

                txns = db.fetch_all(sql, tuple(params))
                self.send_json_response(200, txns)

            elif path.endswith("/events") or path.endswith("/api/events"):
                limit = int(query.get("limit", [30])[0])
                events = db.fetch_all("SELECT * FROM event_logs ORDER BY id DESC LIMIT ?", (limit,))
                self.send_json_response(200, events)

            elif path.endswith("/retry-budgets") or path.endswith("/api/retry-budgets"):
                budgets = db.fetch_all("SELECT * FROM retry_budgets ORDER BY merchant_id, issuing_bank")
                self.send_json_response(200, budgets)

            else:
                self.send_json_response(200, {"status": "Project Limbo Engine API Active", "path": path})

        except Exception as fatal_err:
            err_msg = traceback.format_exc()
            print("Fatal BaseHTTPRequestHandler Error:", err_msg)
            self.send_json_response(500, {"error": "Internal Server Error", "detail": str(fatal_err)})

    def do_POST(self):
        try:
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path

            content_length = int(self.headers.get("Content-Length", 0) or 0)
            body_data = self.rfile.read(content_length) if content_length > 0 else b"{}"
            try:
                payload = json.loads(body_data.decode("utf-8"))
            except Exception:
                payload = {}

            ensure_initialized()

            if path.endswith("/trigger") or path.endswith("/api/simulate/trigger"):
                bank = payload.get("bank")
                rail = payload.get("rail")
                count = payload.get("count", 1)
                force_limbo = payload.get("forceLimbo", False)

                created = []
                for _ in range(count):
                    txn = simulator.create_transaction({"bank": bank, "rail": rail, "forceLimbo": force_limbo})
                    created.append(txn)

                self.send_json_response(200, {"success": True, "count": len(created), "transactions": created})

            elif path.endswith("/toggle") or path.endswith("/api/simulate/toggle"):
                self.send_json_response(200, {"isRunning": True})

            else:
                self.send_json_response(200, {"status": "Project Limbo Engine API Active"})

        except Exception as fatal_err:
            err_msg = traceback.format_exc()
            print("Fatal BaseHTTPRequestHandler POST Error:", err_msg)
            self.send_json_response(500, {"error": "Internal Server Error", "detail": str(fatal_err)})
