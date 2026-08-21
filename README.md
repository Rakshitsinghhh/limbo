# Project Limbo — The Payment Certainty Engine ⚡

> **The Payment Certainty Engine** — solving the money-in-limbo problem in digital payments (UPI Autopay, NACH Mandates, Credit/Debit Cards).

Project Limbo shifts the paradigm in payment recovery: instead of passively waiting for bank callbacks or blindly retrying failed payments, it **actively polls bank APIs**, **predicts transaction outcomes using statistical ML**, **notifies customers proactively**, **triggers automatic reversals**, and **enforces rolling merchant-bank retry budgets** to protect bank approval standing.

---

## 🚀 Quick Start Guide (Python Stack)

### Prerequisites
- **Python**: 3.10 or higher (100% zero third-party pip dependencies required; runs entirely on Python standard library!)

### Execution Steps

1. **Navigate to project directory**:
   ```bash
   cd /home/rakshit/projects/limbo
   ```

2. **Start Project Limbo**:
   ```bash
   python3 main.py
   ```

3. **Access the Interactive Dashboard**:
   Open your browser and navigate to:
   👉 **`http://localhost:3000`**

4. **Run Verification Test Suite**:
   ```bash
   python3 main.py --test
   ```

---

## 🎯 How to Use & Test the Prototype

Once the server is running and the dashboard is open in your browser:

### 1. Watch Automatic Background Simulation
- The Python simulator automatically generates realistic synthetic payments across **HDFC**, **SBI**, **ICICI**, **Axis**, and **Kotak Bank**.
- You will see transactions move through:
  - **Instant Settlement**: Resolved immediately.
  - **Limbo Pending**: Payments debited from customer accounts but delayed in bank/NPCI transit.
  - **Auto-Resolution**: Active poller querying bank APIs and resolving pending transactions.

### 2. Inject Forced Limbo (Stuck Payment)
- In the **Bank Environment Simulator** section:
  1. Select an issuing bank (e.g. **SBI** or **HDFC**).
  2. Select a payment rail (e.g. **UPI Autopay** or **NACH**).
  3. Click **Force Limbo State**.
- Watch the transaction appear in the **Limbo Resolution Table** with `pending` status.
- Observe how the **Prediction Engine** calculates resolution probability $P(\text{success})$ and the **Decision Engine** executes actions (*Wait Quietly*, *Customer Alerted*, or *Auto Reversed*).

### 3. Test Smart Retry Budgeting (Pillar 2)
- Click **Inject Transaction** or **Batch (10 Txns)**.
- When payments fail due to `INSUFFICIENT_FUNDS` or `BANK_TIMEOUT`, observe the **Merchant-Bank Retry Quota** list.
- Low-scoring retries or merchants nearing bank thresholds are marked as **`retry blocked`**, preserving the merchant's **Bank Approval Standing** rating.

---

## 🏗️ Architecture & Component Overview

Project Limbo implements all **7 prototype steps** outlined in the technical pitch document:

| Step | Component | File Path | Functionality |
| :--- | :--- | :--- | :--- |
| **1** | **Payment Simulator** | [`src_py/simulator.py`](file:///home/rakshit/projects/limbo/src_py/simulator.py) | Generates fake transactions with realistic delays & failure profiles per bank/rail. |
| **2** | **Local Database** | [`src_py/db.py`](file:///home/rakshit/projects/limbo/src_py/db.py) | SQLite storage for transactions, event logs, retry counters, and true vs visible status. |
| **3** | **Active Poller** | [`src_py/active_poller.py`](file:///home/rakshit/projects/limbo/src_py/active_poller.py) | Background thread scanning pending payments and querying simulated bank status APIs. |
| **4** | **Prediction Layer** | [`src_py/predictor.py`](file:///home/rakshit/projects/limbo/src_py/predictor.py) | ML engine predicting resolution probability $P(\text{success})$ and scoring retry worthiness. |
| **5** | **Decision Engine** | [`src_py/decision_engine.py`](file:///home/rakshit/projects/limbo/src_py/decision_engine.py) | SLA-aware action layer triggering quiet wait, customer notification, or auto reversal. |
| **6** | **Retry Budget Tracker** | [`src_py/retry_budget.py`](file:///home/rakshit/projects/limbo/src_py/retry_budget.py) | Enforces merchant-bank rolling retry limits to protect long-term approval standing. |
| **7** | **Web Dashboard** | [`src_py/server.py`](file:///home/rakshit/projects/limbo/src_py/server.py) | Multi-threaded HTTP server hosting REST APIs, SSE event streams, and monochrome UI. |

For a complete module-by-module breakdown of every function and database table, read **[`WHAT_EVERYTHING_DOES.md`](file:///home/rakshit/projects/limbo/WHAT_EVERYTHING_DOES.md)**.

---

## 📡 REST API Reference

The server exposes the following JSON REST endpoints:

- **`GET /api/stats`**: Aggregate KPI summary metrics.
- **`GET /api/transactions?status=pending`**: Query transactions with status or bank filtering.
- **`GET /api/events?limit=30`**: Retrieve live audit log records.
- **`GET /api/retry-budgets`**: Fetch current retry budget utilization per merchant and bank.
- **`POST /api/simulate/trigger`**: Inject custom simulated transactions (`{ bank, rail, count, forceLimbo }`).
- **`POST /api/simulate/toggle`**: Start or pause background simulation (`{ action: 'start' | 'stop' }`).
- **`GET /api/stream`**: Server-Sent Events (SSE) live streaming endpoint.
