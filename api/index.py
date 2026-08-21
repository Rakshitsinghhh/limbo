"""
Vercel Serverless Function (WSGI Application with Static Fallback) for Project Limbo
Handles both API routes and static frontend file serving safely.
"""

import sys
import os
import json
import random
import urllib.parse
from datetime import datetime, timedelta

# Set DB_PATH to /tmp/limbo.db for writeable Vercel serverless environment
os.environ["DB_PATH"] = "/tmp/limbo.db"

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PUBLIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "public")

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

def app(environ, start_response):
    path = environ.get("PATH_INFO", "")
    method = environ.get("REQUEST_METHOD", "GET")
    query_string = environ.get("QUERY_STRING", "")
    query = urllib.parse.parse_qs(query_string)

    ensure_initialized()

    # Serve static assets if root or asset path is requested directly
    if path in ["/", "", "/index.html"]:
        file_path = os.path.join(PUBLIC_DIR, "index.html")
        if os.path.exists(file_path):
            with open(file_path, "rb") as f:
                body = f.read()
            start_response("200 OK", [("Content-Type", "text/html"), ("Content-Length", str(len(body)))])
            return [body]

    if path.startswith("/css/") or path.startswith("/js/"):
        rel_path = path.lstrip("/")
        file_path = os.path.join(PUBLIC_DIR, rel_path)
        if os.path.exists(file_path):
            content_type = "text/css" if path.startswith("/css/") else "application/javascript"
            with open(file_path, "rb") as f:
                body = f.read()
            start_response("200 OK", [("Content-Type", content_type), ("Content-Length", str(len(body)))])
            return [body]

    # Process engine lifecycle steps safely
    try:
        active_poller.poll_pending_transactions()
        decision_engine.process_limbo_decisions()
        retry_budget_manager.process_failed_transaction_retries()
    except Exception as e:
        print("Engine step warning:", e)

    headers = [
        ("Content-Type", "application/json"),
        ("Access-Control-Allow-Origin", "*"),
        ("Access-Control-Allow-Methods", "GET, POST, OPTIONS"),
        ("Access-Control-Allow-Headers", "Content-Type")
    ]

    if method == "OPTIONS":
        start_response("200 OK", headers)
        return [b""]

    if path.endswith("/api/stats") or path == "/api/stats":
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
        body = json.dumps(data).encode("utf-8")
        start_response("200 OK", headers)
        return [body]

    elif path.endswith("/api/transactions") or path == "/api/transactions":
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
        body = json.dumps(txns).encode("utf-8")
        start_response("200 OK", headers)
        return [body]

    elif path.endswith("/api/events") or path == "/api/events":
        limit = int(query.get("limit", [30])[0])
        events = db.fetch_all("SELECT * FROM event_logs ORDER BY id DESC LIMIT ?", (limit,))
        body = json.dumps(events).encode("utf-8")
        start_response("200 OK", headers)
        return [body]

    elif path.endswith("/api/retry-budgets") or path == "/api/retry-budgets":
        budgets = db.fetch_all("SELECT * FROM retry_budgets ORDER BY merchant_id, issuing_bank")
        body = json.dumps(budgets).encode("utf-8")
        start_response("200 OK", headers)
        return [body]

    elif path.endswith("/api/simulate/trigger") or path == "/api/simulate/trigger":
        content_length = int(environ.get("CONTENT_LENGTH", 0) or 0)
        body_data = environ["wsgi.input"].read(content_length) if content_length > 0 else b"{}"
        try:
            payload = json.loads(body_data.decode("utf-8"))
        except Exception:
            payload = {}

        bank = payload.get("bank")
        rail = payload.get("rail")
        count = payload.get("count", 1)
        force_limbo = payload.get("forceLimbo", False)

        created = []
        for _ in range(count):
            txn = simulator.create_transaction({"bank": bank, "rail": rail, "forceLimbo": force_limbo})
            created.append(txn)

        body = json.dumps({"success": True, "count": len(created), "transactions": created}).encode("utf-8")
        start_response("200 OK", headers)
        return [body]

    elif path.endswith("/api/simulate/toggle") or path == "/api/simulate/toggle":
        body = json.dumps({"isRunning": True}).encode("utf-8")
        start_response("200 OK", headers)
        return [body]

    else:
        body = json.dumps({"error": "Route not found", "path": path}).encode("utf-8")
        start_response("404 Not Found", headers)
        return [body]
