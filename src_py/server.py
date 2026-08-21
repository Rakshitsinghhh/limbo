"""
Project Limbo — Python HTTP Server & SSE Broadcaster
Exposes REST API endpoints for metrics, transactions, logs, retry quotas, and simulation triggers,
and serves static web dashboard assets using Python standard library.
"""

import http.server
import socketserver
import json
import os
import urllib.parse
import threading
from typing import Any
from src_py import db
from src_py.simulator import simulator

PUBLIC_DIR = os.path.join(os.path.dirname(__file__), "..", "public")
PORT = int(os.environ.get("PORT", 3000))

sse_clients = []
sse_lock = threading.Lock()

def broadcast_sse(event_type: str, data: dict):
    msg = f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
    with sse_lock:
        to_remove = []
        for wfile in sse_clients:
            try:
                wfile.write(msg.encode("utf-8"))
                wfile.flush()
            except Exception:
                to_remove.append(wfile)
        for w in to_remove:
            sse_clients.remove(w)

class LimboHTTPRequestHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Suppress noisy standard HTTP access logs
        pass

    def send_json(self, status_code: int, data: Any):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        if path == "/api/stats":
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
                "isSimulatorRunning": simulator.is_running
            }
            self.send_json(200, data)

        elif path == "/api/transactions":
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
            self.send_json(200, txns)

        elif path == "/api/events":
            limit = int(query.get("limit", [30])[0])
            events = db.fetch_all("SELECT * FROM event_logs ORDER BY id DESC LIMIT ?", (limit,))
            self.send_json(200, events)

        elif path == "/api/retry-budgets":
            budgets = db.fetch_all("SELECT * FROM retry_budgets ORDER BY merchant_id, issuing_bank")
            self.send_json(200, budgets)

        elif path == "/api/stream":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

            with sse_lock:
                sse_clients.append(self.wfile)

            try:
                while True:
                    time.sleep(15)
                    self.wfile.write(b":ping\n\n")
                    self.wfile.flush()
            except Exception:
                with sse_lock:
                    if self.wfile in sse_clients:
                        sse_clients.remove(self.wfile)

        else:
            # Serve Static Asset from public directory
            rel_path = path.lstrip("/")
            if not rel_path:
                rel_path = "index.html"
            file_path = os.path.join(PUBLIC_DIR, rel_path)

            if os.path.isfile(file_path):
                self.send_response(200)
                if file_path.endswith(".html"):
                    self.send_header("Content-Type", "text/html")
                elif file_path.endswith(".css"):
                    self.send_header("Content-Type", "text/css")
                elif file_path.endswith(".js"):
                    self.send_header("Content-Type", "application/javascript")
                elif file_path.endswith(".json"):
                    self.send_header("Content-Type", "application/json")
                self.end_headers()
                with open(file_path, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self.send_json(404, {"error": "File not found"})

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length > 0 else b"{}"

        try:
            payload = json.loads(body.decode("utf-8"))
        except Exception:
            payload = {}

        if path == "/api/simulate/trigger":
            bank = payload.get("bank")
            rail = payload.get("rail")
            count = payload.get("count", 1)
            force_limbo = payload.get("forceLimbo", False)

            created = []
            for _ in range(count):
                txn = simulator.create_transaction({"bank": bank, "rail": rail, "forceLimbo": force_limbo})
                created.append(txn)

            broadcast_sse("NEW_TRANSACTION", {"count": len(created)})
            self.send_json(200, {"success": True, "count": len(created), "transactions": created})

        elif path == "/api/simulate/toggle":
            action = payload.get("action")
            if action == "start":
                simulator.start(3.0)
            else:
                simulator.stop()

            broadcast_sse("SIMULATOR_STATUS", {"isRunning": simulator.is_running})
            self.send_json(200, {"isRunning": simulator.is_running})

        else:
            self.send_json(404, {"error": "Endpoint not found"})

def run_server(port: int = PORT):
    class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
        daemon_threads = True

    server = ThreadedHTTPServer(("0.0.0.0", port), LimboHTTPRequestHandler)
    print(f"===================================================")
    print(f"🚀 Project Limbo — Python Certainty Engine Live!")
    print(f"🌐 Dashboard running at: http://localhost:{port}")
    print(f"===================================================")
    server.serve_forever()
