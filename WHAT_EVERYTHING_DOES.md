# What Everything Does — Comprehensive Architecture & File Guide

**Project Limbo — The Payment Certainty Engine** is a digital payments certainty system designed to solve two hidden problems in recurring digital payments (UPI Autopay, NACH Mandates, Credit/Debit Cards):
1. **Pillar 1: Limbo Resolution Engine** — Solves payments stuck between "debited from customer account" and "confirmed by bank/NPCI/gateway".
2. **Pillar 2: Smart Retry Budgeting** — Solves aggressive blind retries by scoring retries and enforcing merchant-bank rolling retry limits to protect merchant approval standing.

This guide provides an exact, component-by-component breakdown of every directory, file, script, database table, algorithm, and module in this codebase.

---

## 📁 Repository Directory Structure

```
limbo/
├── main.py                             # Python entry point booting SQLite DB, workers, & HTTP server
├── README.md                           # Quick Start guide & execution manual
├── WHAT_EVERYTHING_DOES.md             # (This file) Complete technical reference of all Python modules
├── limbo.db                            # SQLite database file storing transactions, logs, & budgets
├── src_py/
│   ├── config.py                       # Bank SLA windows, delay profiles, & recovery rates (HDFC, SBI, ICICI, Axis, Kotak)
│   ├── db.py                           # SQLite connection, WAL mode, schema init, & transactional helpers
│   ├── simulator.py                    # Prototype Step 1 & 2: Fake Bank + NPCI payment simulator & mock status query API
│   ├── predictor.py                    # Prototype Step 4: Resolution & retry probability engine
│   ├── active_poller.py            # Prototype Step 3: Active polling background thread
│   ├── decision_engine.py          # Prototype Step 5: SLA-aware action layer (Wait/Notify/Reverse)
│   ├── retry_budget.py             # Prototype Step 6: Smart Retry Budget tracker & scheduler
│   └── server.py                       # Native Python HTTP API server & Server-Sent Events (SSE) broadcaster
└── public/                             # Prototype Step 7: Minimalist Monochrome Web Dashboard UI
    ├── index.html                      # Clean HTML structure
    ├── css/
    │   └── styles.css                  # High-contrast monochrome CSS design system
    └── js/
        └── app.js                      # Front-end JavaScript connecting REST APIs, SSE, & simulation UI
```

---

## 📄 Python Module-by-Module Technical Reference

### 1. [`main.py`](file:///home/rakshit/projects/limbo/main.py)
- **Role**: Application Bootstrapper.
- **Workflow**:
  - Initializes SQLite database schema via `db.init_db()`.
  - Seeds baseline transaction data if database is empty.
  - Spawns background worker threads: `active_poller`, `decision_engine`, `retry_budget_manager`, and `simulator`.
  - Launches native Python HTTP server on port 3000 via `run_server()`.
  - Supports `--test` CLI flag to run automated test suites.

---

### 2. Configuration & Data Model Layer

#### [`src_py/config.py`](file:///home/rakshit/projects/limbo/src_py/config.py)
- **Role**: Prototype Step 1 Config — Contains bank settlement parameters for **HDFC Bank**, **State Bank of India (SBI)**, **ICICI Bank**, **Axis Bank**, and **Kotak Mahindra Bank**.
- **Parameters**:
  - `expected_window_sec`: Normal confirmation window (UPI Autopay = 30s, NACH = 2h, Card = 15s).
  - `limbo_probability`: Likelihood of payment entering delayed state.
  - `delay_mean_sec`: Average time before status is available at NPCI/Bank.
  - `success_rate`: Percentage of limbo payments resolving to success.
  - `failure_recovery_rates`: Historical recovery rates by decline code (`INSUFFICIENT_FUNDS`, `BANK_TIMEOUT`, `RISK_DECLINE`, `NETWORK_ERROR`).

#### [`src_py/db.py`](file:///home/rakshit/projects/limbo/src_py/db.py)
- **Role**: Prototype Step 2 Data Layer — Thread-safe SQLite connection manager (`sqlite3`).
- **Database Tables**:
  - `transactions`: ID, merchant ID, customer ID, bank, rail, amount, visible status (`pending`, `success`, `failed`, `reversed`), true status (`success`, `failed`), failure reason, timestamps, ambiguity flag, probability score, retry count, action taken.
  - `event_logs`: Audit trail of all engine actions.
  - `retry_budgets`: Merchant-bank rolling 24h retry counters.
  - `engine_metrics`: Periodic aggregated KPI snapshots.

---

### 3. Engine & Simulator Layer

#### [`src_py/simulator.py`](file:///home/rakshit/projects/limbo/src_py/simulator.py)
- **Role**: Prototype Step 1 & 2 Ecosystem Simulator — Generates synthetic payments with weighted random outcomes:
  - 65% Instant Success
  - 10% Instant Failure
  - 25% Limbo State (`visible_status = 'pending'`, `true_status` hidden until `true_resolution_time`).
- Exposes `query_bank_api(txn_id)` mock status check API.

#### [`src_py/predictor.py`](file:///home/rakshit/projects/limbo/src_py/predictor.py)
- **Role**: Prototype Step 4 Machine Learning & Statistical Engine — Calculates probability scores:
  - `predict_resolution_probability(txn)`: Calculates $P(\text{self-resolution})$ using bank historical settlement rates, expected window, exponential age decay factor, and off-peak hour adjustments.
  - `score_retry_worthiness(txn)`: Calculates $P(\text{retry\_success})$ using decline codes, attempt decay ($0.65^{\text{retry\_count}}$), salary credit window boost (1st-5th of month), and maintenance window penalties.

#### [`src_py/active_poller.py`](file:///home/rakshit/projects/limbo/src_py/active_poller.py)
- **Role**: Prototype Step 3 Active Poller — Background thread scanning pending transactions, flagging ambiguity when expected windows are breached, calculating probability scores, and querying mock bank APIs to auto-resolve transactions.

#### [`src_py/decision_engine.py`](file:///home/rakshit/projects/limbo/src_py/decision_engine.py)
- **Role**: Prototype Step 5 Action Layer — Background thread executing SLA policy matrix:
  - $P \ge 0.75$: `WAIT_QUIETLY` — No customer alarm.
  - $0.35 \le P < 0.75$ & Near SLA: `NOTIFY_CUSTOMER` — Dispatches proactive SMS/Email.
  - $P < 0.35$ & SLA Breached: `AUTO_REVERSAL` — Executes automated fund reversal.

#### [`src_py/retry_budget.py`](file:///home/rakshit/projects/limbo/src_py/retry_budget.py)
- **Role**: Prototype Step 6 Smart Retry Budget Tracker — Background thread evaluating failed transaction retries against merchant-bank rolling budgets. Blocks low-probability retries (`RETRY_BLOCKED`) to protect merchant bank standing.

---

### 4. Server & UI Layer

#### [`src_py/server.py`](file:///home/rakshit/projects/limbo/src_py/server.py)
- **Role**: Native Python HTTP Server & SSE Broadcaster — Implements multi-threaded `http.server` handling REST endpoints (`/api/stats`, `/api/transactions`, `/api/events`, `/api/retry-budgets`, `/api/simulate/trigger`, `/api/simulate/toggle`), Server-Sent Events (`/api/stream`), and static web dashboard assets.

#### [`public/index.html`](file:///home/rakshit/projects/limbo/public/index.html) & [`public/css/styles.css`](file:///home/rakshit/projects/limbo/public/css/styles.css)
- **Role**: Prototype Step 7 Dashboard UI — Clean, high-contrast monochrome interface displaying KPI cards, simulation controls, limbo transaction monitor, retry budget quotas, and live engine audit log feed.
