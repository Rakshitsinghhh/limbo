"""
Project Limbo — SQLite Database Management Layer
Provides thread-safe database connections, WAL mode configuration, table initialization,
and helper methods for transaction CRUD operations and event logging.
"""

import sqlite3
import os
import threading
from typing import Dict, Any, List, Optional

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "..", "limbo.db"))
_local = threading.local()

def get_connection():
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = sqlite3.connect(DB_PATH, timeout=20.0)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode = WAL;")
    return _local.conn

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode = WAL;")
    cursor = conn.cursor()

    cursor.executescript("""
    CREATE TABLE IF NOT EXISTS transactions (
        id TEXT PRIMARY KEY,
        merchant_id TEXT NOT NULL,
        customer_id TEXT NOT NULL,
        issuing_bank TEXT NOT NULL,
        rail TEXT NOT NULL,
        amount REAL NOT NULL,
        visible_status TEXT NOT NULL CHECK(visible_status IN ('pending', 'success', 'failed', 'reversed')),
        true_status TEXT NOT NULL CHECK(true_status IN ('success', 'failed')),
        failure_reason TEXT DEFAULT 'NONE',
        debit_timestamp DATETIME NOT NULL,
        expected_window_sec INTEGER NOT NULL,
        sla_deadline DATETIME NOT NULL,
        true_resolution_time DATETIME NOT NULL,
        is_ambiguous INTEGER DEFAULT 0,
        probability_score REAL DEFAULT 0.0,
        last_polled_at DATETIME,
        retry_count INTEGER DEFAULT 0,
        retry_score REAL DEFAULT 0.0,
        action_taken TEXT DEFAULT 'NONE',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS event_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        transaction_id TEXT NOT NULL,
        merchant_id TEXT,
        event_type TEXT NOT NULL,
        message TEXT NOT NULL,
        metadata TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS retry_budgets (
        merchant_id TEXT NOT NULL,
        issuing_bank TEXT NOT NULL,
        retries_used INTEGER DEFAULT 0,
        retries_blocked INTEGER DEFAULT 0,
        daily_limit INTEGER DEFAULT 100,
        last_reset DATETIME DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (merchant_id, issuing_bank)
    );

    CREATE TABLE IF NOT EXISTS engine_metrics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        total_transactions INTEGER DEFAULT 0,
        limbo_pending INTEGER DEFAULT 0,
        auto_resolved INTEGER DEFAULT 0,
        notifications_sent INTEGER DEFAULT 0,
        reversals_triggered INTEGER DEFAULT 0,
        retries_blocked INTEGER DEFAULT 0,
        retries_recovered INTEGER DEFAULT 0,
        avg_limbo_resolution_sec REAL DEFAULT 0.0,
        merchant_approval_standing REAL DEFAULT 95.0
    );
    """)

    conn.commit()
    conn.close()

def execute(sql: str, params: tuple = ()) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(sql, params)
    conn.commit()
    return cursor.rowcount

def fetch_one(sql: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(sql, params)
    row = cursor.fetchone()
    if row:
        return dict(row)
    return None

def fetch_all(sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(sql, params)
    rows = cursor.fetchall()
    return [dict(row) for row in rows]

def log_event(transaction_id: str, merchant_id: str, event_type: str, message: str, metadata: str = None):
    execute(
        """INSERT INTO event_logs (transaction_id, merchant_id, event_type, message, metadata)
           VALUES (?, ?, ?, ?, ?)""",
        (transaction_id, merchant_id, event_type, message, metadata)
    )
