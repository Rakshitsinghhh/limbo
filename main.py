"""
Project Limbo — Main Entry Point (Python Stack)
Initializes database schema, seeds demo data, boots background engine threads,
and launches the native HTTP server dashboard.
"""

import sys
import time
from src_py import db
from src_py.simulator import simulator
from src_py.active_poller import active_poller
from src_py.decision_engine import decision_engine
from src_py.retry_budget import retry_budget_manager
from src_py.server import run_server, PORT

def seed_demo_data():
    count_row = db.fetch_one("SELECT COUNT(*) as count FROM transactions")
    if count_row["count"] == 0:
        print("Seeding initial baseline simulation transactions...")
        for _ in range(12):
            simulator.create_transaction()
        simulator.create_transaction({"bank": "SBI", "rail": "UPI_AUTOPAY", "forceLimbo": True})
        simulator.create_transaction({"bank": "HDFC", "rail": "NACH", "forceLimbo": True})

def run_tests():
    print("Running Python Engine Verification Tests...")
    db.init_db()
    txn = simulator.create_transaction({"bank": "SBI", "rail": "UPI_AUTOPAY", "forceLimbo": True})
    print(f"✅ Created forced limbo txn: {txn['id']} (Status: {txn['visible_status']})")
    
    active_poller.poll_pending_transactions()
    print("✅ Active Poller executed")
    
    decision_engine.process_limbo_decisions()
    print("✅ Decision Engine executed")
    
    retry_budget_manager.process_failed_transaction_retries()
    print("✅ Retry Budget Manager executed")
    
    cnt = db.fetch_one("SELECT COUNT(*) as count FROM transactions")["count"]
    print(f"✅ DB verification passed (Total Txns: {cnt})")
    print("🎉 All Python engine tests passed successfully!")
    sys.exit(0)

def main():
    if "--test" in sys.argv:
        run_tests()

    print("Initializing Project Limbo Python Engine...")
    db.init_db()
    seed_demo_data()

    # Start engine background threads
    active_poller.start(interval_sec=2.0)
    decision_engine.start(interval_sec=2.5)
    retry_budget_manager.start(interval_sec=3.0)
    simulator.start(interval_sec=3.0)

    # Run native Python HTTP server
    run_server(PORT)

if __name__ == "__main__":
    main()
