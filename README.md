# Project Limbo — The Payment Certainty Engine ⚡

> **The Payment Certainty Engine** — solving the money-in-limbo problem in digital payments (UPI Autopay, NACH Mandates, Credit/Debit Cards).

Project Limbo shifts the paradigm in payment recovery: instead of passively waiting for bank callbacks or blindly retrying failed payments, it **actively polls bank APIs**, **predicts transaction outcomes using statistical ML**, **notifies customers proactively**, **triggers automatic reversals**, and **enforces rolling merchant-bank retry budgets** to protect bank approval standing.

---

## 🚀 Quick Start Guide

### Prerequisites
- **Node.js**: v18.0.0 or higher
- **npm**: v8.0.0 or higher

### Installation & Execution

1. **Clone or navigate to project directory**:
   ```bash
   cd /home/rakshit/projects/limbo
   ```

2. **Install Node.js dependencies**:
   ```bash
   npm install
   ```

3. **Start the Project Limbo Server**:
   ```bash
   npm start
   ```
   *(Or run directly with: `node src/server.js`)*

4. **Access the Interactive Dashboard**:
   Open your browser and navigate to:
   👉 **`http://localhost:3000`**

---

## 🎯 How to Use & Test the Prototype

Once the server is running and the dashboard is open in your browser, you can interact with all 7 prototype components in real time:

### 1. Watch Automatic Background Simulation
- Upon launch, the simulator automatically generates realistic synthetic payments across **HDFC**, **SBI**, **ICICI**, **Axis**, and **Kotak Bank**.
- You will see transactions move through:
  - **Instant Settlement**: Resolved immediately.
  - **Limbo Pending**: Payments debited from customer accounts but delayed in bank/NPCI transit.
  - **Auto-Resolution**: Active poller querying bank APIs and resolving pending transactions.

### 2. Inject Forced Limbo (Stuck Payment)
- In the **Live Simulation Controller** section:
  1. Select an issuing bank (e.g. **SBI** or **HDFC**).
  2. Select a payment rail (e.g. **UPI Autopay** or **NACH**).
  3. Click **Force Limbo (Stuck Payment)**.
- Watch the transaction appear in the **Limbo Resolution Feed** with `Pending Limbo` status.
- Observe how the **Prediction Engine** calculates resolution probability $P(\text{success})$ and the **Decision Engine** executes actions (`Wait Quietly`, `Customer Notified`, or `Auto Reversal`).

### 3. Test Smart Retry Budgeting (Pillar 2)
- Click **Inject Normal Txn** or **Stress Test (Batch 10)**.
- When payments fail due to `INSUFFICIENT_FUNDS` or `BANK_TIMEOUT`, observe the **Merchant-Bank Rolling Retry Counters** widget.
- Notice how low-scoring retries or merchants nearing bank thresholds are marked as **`RETRY_BLOCKED`**, preserving the merchant's **Bank Approval Standing** rating.

### 4. Pause / Resume Simulation
- Click the **Pause Simulator / Start Simulator** toggle button in the top header to control transaction generation during demos.

---

## 🏗️ Architecture & Component Overview

Project Limbo implements all **7 prototype steps** outlined in the technical pitch document:

| Step | Component | File Path | Functionality |
| :--- | :--- | :--- | :--- |
| **1** | **Payment Simulator** | [`src/simulator/payment_simulator.js`](file:///home/rakshit/projects/limbo/src/simulator/payment_simulator.js) | Generates fake transactions with realistic delays & failure profiles per bank/rail. |
| **2** | **Local Database** | [`src/database/schema.sql`](file:///home/rakshit/projects/limbo/src/database/schema.sql) | SQLite storage for transactions, event logs, retry counters, and true vs visible status. |
| **3** | **Active Poller** | [`src/engine/active_poller.js`](file:///home/rakshit/projects/limbo/src/engine/active_poller.js) | Background job scanning pending payments and querying simulated bank status APIs. |
| **4** | **Prediction Layer** | [`src/engine/predictor.js`](file:///home/rakshit/projects/limbo/src/engine/predictor.js) | ML engine predicting resolution probability $P(\text{success})$ and scoring retry worthiness. |
| **5** | **Decision Engine** | [`src/engine/decision_engine.js`](file:///home/rakshit/projects/limbo/src/engine/decision_engine.js) | SLA-aware action layer triggering quiet wait, customer notification, or auto reversal. |
| **6** | **Retry Budget Tracker** | [`src/engine/retry_budget_manager.js`](file:///home/rakshit/projects/limbo/src/engine/retry_budget_manager.js) | Enforces merchant-bank rolling retry limits to protect long-term approval standing. |
| **7** | **Web Dashboard** | [`public/index.html`](file:///home/rakshit/projects/limbo/public/index.html) | Interactive real-time dashboard displaying metrics, transaction streams, & audit logs. |

For a complete module-by-module breakdown of every function and database table, read **[`WHAT_EVERYTHING_DOES.md`](file:///home/rakshit/projects/limbo/WHAT_EVERYTHING_DOES.md)**.

---

## 📡 REST API Reference

The server exposes the following JSON REST endpoints:

- **`GET /api/stats`**: Aggregate KPI summary metrics (Limbo pending, auto-resolved, notifications, reversals, revenue recovered, bank standing).
- **`GET /api/transactions?status=pending`**: Query transactions with optional status or bank filtering.
- **`GET /api/events?limit=30`**: Retrieve live audit log records.
- **`GET /api/retry-budgets`**: Fetch current retry budget utilization per merchant and bank.
- **`POST /api/simulate/trigger`**: Inject custom simulated transactions (`{ bank, rail, count, forceLimbo }`).
- **`POST /api/simulate/toggle`**: Start or pause background simulation (`{ action: 'start' | 'stop' }`).
- **`GET /api/stream`**: Server-Sent Events (SSE) live streaming endpoint.

---

## 📊 Key Success Metrics Tracked

1. **Average Limbo Resolution Time**: Measures how fast stuck payments are resolved.
2. **Customer Notifications Sent**: Measures proactive updates preventing support tickets.
3. **Auto-Reversals Executed**: Measures automated customer refunds when SLA expires.
4. **Revenue Recovered**: Measures recovered revenue from high-scoring retries.
5. **Merchant Bank Standing Rating**: Tracks merchant approval standing protected by blocking low-probability retries.
