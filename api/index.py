"""
Vercel Serverless Function Entry Point for Project Limbo
Configures SQLite in /tmp, handles API routes, and runs engine ticks on serverless invocations.
"""

import sys
import os

# Configure SQLite DB path for Vercel writeable /tmp filesystem
os.environ["DB_PATH"] = "/tmp/limbo.db"

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src_py import db
from src_py.simulator import simulator
from src_py.active_poller import active_poller
from src_py.decision_engine import decision_engine
from src_py.retry_budget import retry_budget_manager
from src_py.server import LimboHTTPRequestHandler

# Initialize SQLite database on Vercel cold start
db.init_db()

# Seed baseline demo transactions if fresh
count_row = db.fetch_one("SELECT COUNT(*) as count FROM transactions")
if not count_row or count_row["count"] == 0:
    for _ in range(12):
        simulator.create_transaction()
    simulator.create_transaction({"bank": "SBI", "rail": "UPI_AUTOPAY", "forceLimbo": True})
    simulator.create_transaction({"bank": "HDFC", "rail": "NACH", "forceLimbo": True})

class handler(LimboHTTPRequestHandler):
    def do_GET(self):
        # Run engine ticks per API call to process pending limbo states in serverless environment
        active_poller.poll_pending_transactions()
        decision_engine.process_limbo_decisions()
        retry_budget_manager.process_failed_transaction_retries()
        super().do_GET()

    def do_POST(self):
        super().do_POST()
        active_poller.poll_pending_transactions()
        decision_engine.process_limbo_decisions()
        retry_budget_manager.process_failed_transaction_retries()
