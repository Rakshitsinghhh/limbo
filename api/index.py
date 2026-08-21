"""
Vercel Serverless Function (WSGI Application) for Project Limbo
Processes API requests, executes engine steps per request, and handles database storage in /tmp.
"""

import sys
import os
import json
import urllib.parse
from datetime import datetime

# Set DB_PATH to /tmp/limbo.db for writeable Vercel serverless environment
os.environ["DB_PATH"] = "/tmp/limbo.db"

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src_py import db
from src_py.simulator import simulator
from src_py.active_poller import active_poller
from src_py.decision_engine import decision_engine
from src_py.retry_budget import retry_budget_manager

def ensure_initialized():
    db.init_db()
    count_row = db.fetch_one("SELECT COUNT(*) as count FROM transactions")
    if not count_row or count_row["count"] == 0:
        for _ in range(10):
            simulator.create_transaction()
        simulator.create_transaction({"bank": "SBI", "rail": "UPI_AUTOPAY", "forceLimbo": True})
        simulator.create_transaction({"bank": "HDFC", "rail": "NACH", "forceLimbo": True})

def app(environ, start_response):
    path = environ.get("PATH_INFO", "")
    method = environ.get("REQUEST_METHOD", "GET")
    query_string = environ.get("QUERY_STRING", "")
    query = urllib.parse.parse_qs(query_string)

    ensure_initialized()

    # Process engine lifecycle steps on each API request
    try:
        active_poller.poll_pending_transactions()
        decision_engine.process_limbo_decisions()
        retry_budget_manager.process_failed_transaction_retries()
    except Exception as e:
        print("Engine step error:", e)

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
