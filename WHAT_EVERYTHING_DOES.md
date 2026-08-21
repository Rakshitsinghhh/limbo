# What Everything Does — Comprehensive Architecture & File Guide

**Project Limbo — The Payment Certainty Engine** is a digital payments certainty system designed to solve two hidden problems in recurring digital payments (UPI Autopay, NACH Mandates, Credit/Debit Cards):
1. **Pillar 1: Limbo Resolution Engine** — Solves payments stuck between "debited from customer account" and "confirmed by bank/NPCI/gateway".
2. **Pillar 2: Smart Retry Budgeting** — Solves aggressive blind retries by scoring retries and enforcing merchant-bank rolling retry limits to protect merchant approval standing.

This guide provides an exact, component-by-component breakdown of every directory, file, script, database table, algorithm, and module in this codebase.

---

## 📁 Repository Directory Structure

```
limbo/
├── README.md                           # Step-by-step Quick Start guide & system manual
├── WHAT_EVERYTHING_DOES.md             # (This file) Complete technical reference of all files & logic
├── package.json                        # Node.js dependencies, scripts, and configuration
├── limbo.db                            # SQLite database file storing transactions, logs, & budgets
├── src/
│   ├── config/
│   │   └── bank_profiles.json          # Bank-wise SLA windows, limbo probabilities, & recovery rates
│   ├── database/
│   │   ├── schema.sql                  # Database table definitions & schema indexes
│   │   └── db.js                       # SQLite database connection, WAL configuration, & promise wrappers
│   ├── simulator/
│   │   └── payment_simulator.js        # Prototype Step 1 & 2: Fake Bank + NPCI payment generator & API mock
│   ├── engine/
│   │   ├── predictor.js                # Prototype Step 4: ML & statistical prediction scoring engine
│   │   ├── active_poller.js            # Prototype Step 3: Active polling background worker
│   │   ├── decision_engine.js          # Prototype Step 5: SLA-aware action layer (Notify/Reverse/Wait)
│   │   └── retry_budget_manager.js     # Prototype Step 6: Smart Retry Budget tracker & scheduler
│   └── server.js                        # Unified Express HTTP API & Server-Sent Events (SSE) server
└── public/                             # Prototype Step 7: Interactive Real-Time Web Dashboard
    ├── index.html                      # Dark-mode dashboard HTML structure & glassmorphic layout
    ├── css/
    │   └── styles.css                  # Custom CSS design system, typography, cards, & animations
    └── js/
        └── app.js                      # Front-end JavaScript connecting REST APIs, SSE, & simulation UI
```

---

## 📄 File-by-File Technical Explanation

### 1. [`package.json`](file:///home/rakshit/projects/limbo/package.json)
- **Role**: Node.js project specification file.
- **Dependencies**:
  - `express`: Lightweight web server framework hosting REST API endpoints and static UI assets.
  - `sqlite3`: Native driver for local SQLite database storage.
  - `cors`: Cross-Origin Resource Sharing middleware.
  - `ws`: Server-Sent Events and WebSocket utilities.

---

### 2. Configuration Layer

#### [`src/config/bank_profiles.json`](file:///home/rakshit/projects/limbo/src/config/bank_profiles.json)
- **Role**: Prototype Step 1 Config — Defines historical settlement profiles and bank behavior rules for major Indian issuing banks: **HDFC Bank**, **State Bank of India (SBI)**, **ICICI Bank**, **Axis Bank**, and **Kotak Mahindra Bank**.
- **Data Structure**:
  - `rails`: Per-rail parameters (`UPI_AUTOPAY`, `NACH`, `CARD`):
    - `expected_window_sec`: Normal confirmation window (e.g. UPI=30s, NACH=2h, Card=15s).
    - `limbo_probability`: Likelihood of transaction entering delayed confirmation state.
    - `delay_mean_sec`: Average time before real status is available at NPCI/Bank.
    - `success_rate`: Percentage of limbo payments that eventually resolve to success (e.g., HDFC UPI=88%).
  - `retry_budget`: `daily_limit_per_merchant` and `hourly_threshold`.
  - `failure_recovery_rates`: Historical recovery rates by failure reason (`INSUFFICIENT_FUNDS`, `BANK_TIMEOUT`, `RISK_DECLINE`, `NETWORK_ERROR`).

---

### 3. Storage Layer

#### [`src/database/schema.sql`](file:///home/rakshit/projects/limbo/src/database/schema.sql)
- **Role**: Prototype Step 2 Database Schema — Defines 4 SQLite database tables:
  1. `transactions`:
     - `id`: Unique transaction identifier (`TXN_...`).
     - `merchant_id`: Merchant code (`MERCHANT_ALPHA`, `MERCHANT_BETA`, etc.).
     - `customer_id`: End-user customer ID.
     - `issuing_bank` & `rail`: Target bank and payment method.
     - `amount`: Monetary value in INR (₹).
     - `visible_status`: Status exposed to gateway/merchant (`pending`, `success`, `failed`, `reversed`).
     - `true_status`: Actual status known to simulator (`success`, `failed`).
     - `failure_reason`: Decline code if failed.
     - `debit_timestamp`, `expected_window_sec`, `sla_deadline`, `true_resolution_time`: Time markers.
     - `is_ambiguous`: Flagged when confirmation window is crossed.
     - `probability_score`: Score calculated by Predictor.
     - `retry_count`, `retry_score`, `action_taken`: Engine state.
  2. `event_logs`: Full audit trail of engine events (`AMBIGUITY_FLAGGED`, `STATUS_POLLED`, `NOTIFICATION_SENT`, `REVERSAL_TRIGGERED`, `RETRY_BLOCKED`, `RETRY_EXECUTED`).
  3. `retry_budgets`: Counters tracking retries used and blocked per merchant per bank.
  4. `engine_metrics`: Periodic aggregated KPI snapshots.

#### [`src/database/db.js`](file:///home/rakshit/projects/limbo/src/database/db.js)
- **Role**: Data Access Layer — Opens SQLite connection, configures Write-Ahead Logging (`PRAGMA journal_mode = WAL;`) for high concurrency, initializes schema from `schema.sql`, and exposes promisified `run()`, `get()`, and `all()` methods.

---

### 4. Engine & Simulation Layer

#### [`src/simulator/payment_simulator.js`](file:///home/rakshit/projects/limbo/src/simulator/payment_simulator.js)
- **Role**: Prototype Step 1 & 2 Ecosystem Simulator — Simulates real-world banking infrastructure locally.
- **Key Functions**:
  - `generateRandomTransaction(customParams)`: Generates fake payments. Randomly assigns:
    - 65% Instant Success
    - 10% Instant Failure
    - 25% Limbo State (`visible_status = 'pending'`, `true_status` hidden until `true_resolution_time`).
  - `queryBankApi(txnId)`: Mock NPCI/Bank status check endpoint. Returns `PENDING_BANK_PROCESSING` if queried before `true_resolution_time`, or true outcome (`SUCCESS`/`FAILED`) after delay expires.
  - `startContinuousSimulation(intervalMs)`: Background loop creating realistic transaction stream.

#### [`src/engine/predictor.js`](file:///home/rakshit/projects/limbo/src/engine/predictor.js)
- **Role**: Prototype Step 4 Machine Learning & Statistical Engine — Calculates probability scores without relying on external cloud ML services.
- **Algorithms**:
  - `predictResolutionProbability(txn)`: Calculates $P(\text{resolve\_successfully})$ for limbo payments:
    $$P = P_{\text{base}} \times e^{-\lambda \times \max(0, \text{age} - \text{window})} \times \text{TOD\_Factor}$$
    Evaluates bank settlement patterns, rail expected window, elapsed age, and hour of day.
  - `scoreRetryWorthiness(txn)`: Calculates $P(\text{retry\_success})$ for failed payments:
    $$P_{\text{retry}} = \text{Recovery}_{\text{reason}} \times 0.65^{\text{retry\_count}} \times \text{SalaryBoost} \times \text{MaintenancePenalty}$$
    Evaluates failure reason, attempt count, salary credit window (1st-5th of month), and bank maintenance hours.

#### [`src/engine/active_poller.js`](file:///home/rakshit/projects/limbo/src/engine/active_poller.js)
- **Role**: Prototype Step 3 Active Polling Layer — Replaces passive waiting with active status verification.
- **Workflow**:
  1. Scans DB for transactions stuck in `pending`.
  2. Flags transactions crossing expected window as `is_ambiguous = 1` (`AMBIGUITY_FLAGGED`).
  3. Invokes `predictor.predictResolutionProbability(txn)` to update $P(\text{success})$.
  4. Queries `paymentSimulator.queryBankApi(txn.id)`.
  5. If status resolved, updates `visible_status` to `success` or `failed` and logs `STATUS_POLLED` event.

#### [`src/engine/decision_engine.js`](file:///home/rakshit/projects/limbo/src/engine/decision_engine.js)
- **Role**: Prototype Step 5 SLA-Aware Action Layer — Automated decision engine applying rule matrices to prediction scores:
  - **High Confidence ($P \ge 0.75$)**: `WAIT_QUIETLY` — Prevents false alarms.
  - **Medium Confidence ($0.35 \le P < 0.75$) & Near SLA**: `NOTIFY_CUSTOMER` — Dispatches proactive SMS/Email to customer: *"Payment debited, being verified with Bank. No action needed."*
  - **Low Confidence ($P < 0.35$) & SLA Breached**: `AUTO_REVERSAL` — Triggers automatic fund reversal to customer account.

#### [`src/engine/retry_budget_manager.js`](file:///home/rakshit/projects/limbo/src/engine/retry_budget_manager.js)
- **Role**: Prototype Step 6 Smart Retry Budget Tracker — Protects merchant approval standing with issuing banks.
- **Workflow**:
  1. Evaluates failed transactions.
  2. Calculates `retryScore` via Predictor.
  3. Checks merchant's rolling 24-hour retry budget counter against bank limit.
  4. If budget exhausted OR `retryScore < 0.45`: Action = `RETRY_BLOCKED`. Preserves merchant standing rating.
  5. If within budget AND `retryScore \ge 0.45`: Action = `RETRY_EXECUTED`. Executes retry and logs recovered revenue if successful.

---

### 5. Web Server & API Layer

#### [`src/server.js`](file:///home/rakshit/projects/limbo/src/server.js)
- **Role**: Express Server & Orchestrator — Boots database, starts background engine loops (`activePoller`, `decisionEngine`, `retryBudgetManager`, `paymentSimulator`), serves public assets, and provides REST API & SSE endpoints:
  - `GET /api/stats`: Dashboard summary stats.
  - `GET /api/transactions`: Transaction list with status/bank filters.
  - `GET /api/events`: Live engine log feed.
  - `GET /api/retry-budgets`: Merchant-bank retry quotas.
  - `POST /api/simulate/trigger`: Manual transaction generator (single, limbo, batch).
  - `POST /api/simulate/toggle`: Pause/resume simulator.
  - `GET /api/stream`: Real-time Server-Sent Events stream.

---

### 6. Interactive Web Dashboard (UI)

#### [`public/index.html`](file:///home/rakshit/projects/limbo/public/index.html)
- **Role**: Prototype Step 7 Dashboard Interface — Dark-mode layout displaying:
  - KPI Header Cards (Limbo Pending, Auto-Resolved, Customer Notifications, Auto-Reversals, Revenue Recovered, Merchant Bank Standing).
  - Simulation Control Panel (Bank & Rail selectors, Inject Normal Txn, Force Limbo, Stress Test Batch).
  - Pillar 1: Limbo Resolution Table with animated probability meters and status badges.
  - Pillar 2: Smart Retry Budget Progress Bars & Real-Time Engine Audit Log Stream.

#### [`public/css/styles.css`](file:///home/rakshit/projects/limbo/public/css/styles.css)
- **Role**: Styling & Aesthetics — Modern glassmorphism CSS system using CSS variables, backdrop blur filters, glowing accents, pulsing indicators, and custom responsive data tables.

#### [`public/js/app.js`](file:///home/rakshit/projects/limbo/public/js/app.js)
- **Role**: Front-End Logic — Fetches initial REST data, manages UI filter pills, handles button clicks, updates table rows and progress meters dynamically, and establishes SSE streaming connection.

---

## 🔄 Lifecycle of a Limbo Payment in Project Limbo

```
[Customer Payment Initiated]
          │
          ▼
 [Debited at Bank Account] ──(Message delayed at NPCI/Bank)──► [Gateway status: "PENDING"]
                                                                      │
                                                                      ▼
                                                          [Active Poller scans DB]
                                                                      │
                                                 ┌────────────────────┴────────────────────┐
                                                 ▼                                         ▼
                                        [Age > Expected Window]                  [Query Bank Status API]
                                                 │                                         │
                                                 ▼                                         ▼
                                     [Flagged: AMBIGUOUS = 1]                   [If settled: Auto-Resolve]
                                                 │
                                                 ▼
                                     [Predictor calculates P]
                                                 │
                        ┌────────────────────────┼────────────────────────┐
                        ▼                        ▼                        ▼
                 (P >= 0.75)             (0.35 <= P < 0.75)            (P < 0.35)
                        │                        │                        │
                        ▼                        ▼                        ▼
                 [Wait Quietly]         [Proactive Customer]      [Auto-Reversal]
                (No false alarm)            (SMS/Email)           (Refund Customer)
```
