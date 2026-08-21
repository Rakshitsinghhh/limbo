-- Project Limbo Database Schema
-- SQLite schema for storing transaction lifecycle, event audit trail, and merchant retry budget counters

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
