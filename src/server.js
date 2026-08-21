const express = require('express');
const cors = require('cors');
const path = require('path');
const db = require('./database/db');
const paymentSimulator = require('./simulator/payment_simulator');
const activePoller = require('./engine/active_poller');
const decisionEngine = require('./engine/decision_engine');
const retryBudgetManager = require('./engine/retry_budget_manager');

const app = express();
const PORT = process.env.PORT || 3000;

app.use(cors());
app.use(express.json());
app.use(express.static(path.join(__dirname, '../public')));

// Store active SSE clients
let sseClients = [];

function broadcastSSE(eventType, data) {
  sseClients.forEach(client => {
    client.res.write(`event: ${eventType}\ndata: ${JSON.stringify(data)}\n\n`);
  });
}

// REST API Endpoints

// 1. Overall Dashboard Analytics Metrics
app.get('/api/stats', async (req, res) => {
  try {
    const totalTxns = await db.get(`SELECT COUNT(*) as count FROM transactions`);
    const pendingLimbo = await db.get(`SELECT COUNT(*) as count FROM transactions WHERE visible_status = 'pending'`);
    const autoResolved = await db.get(`SELECT COUNT(*) as count FROM transactions WHERE action_taken IN ('AUTO_RESOLVED_SUCCESS', 'WAIT_QUIETLY') OR visible_status = 'success'`);
    const notifications = await db.get(`SELECT COUNT(*) as count FROM event_logs WHERE event_type = 'NOTIFICATION_SENT'`);
    const reversals = await db.get(`SELECT COUNT(*) as count FROM event_logs WHERE event_type = 'REVERSAL_TRIGGERED'`);
    const retriesBlocked = await db.get(`SELECT COUNT(*) as count FROM event_logs WHERE event_type = 'RETRY_BLOCKED'`);
    const revenueRecovered = await db.get(`SELECT SUM(amount) as total FROM transactions WHERE action_taken = 'RECOVERED_BY_RETRY'`);
    
    // Average limbo resolution duration
    const limboTimes = await db.get(`SELECT AVG((JULIANDAY(last_polled_at) - JULIANDAY(debit_timestamp)) * 86400) as avg_sec FROM transactions WHERE visible_status != 'pending' AND last_polled_at IS NOT NULL`);

    // Merchant Approval Rating calculation (protecting standing)
    const totalRetries = await db.get(`SELECT COUNT(*) as count FROM event_logs WHERE event_type IN ('RETRY_EXECUTED', 'RETRY_BLOCKED')`);
    const blockedCount = retriesBlocked.count || 0;
    const approvalStanding = totalRetries.count > 0 
      ? Math.min(99.4, 85 + (blockedCount / totalRetries.count) * 14.4)
      : 98.2;

    res.json({
      totalTransactions: totalTxns.count || 0,
      limboPending: pendingLimbo.count || 0,
      autoResolvedCount: autoResolved.count || 0,
      notificationsSent: notifications.count || 0,
      reversalsTriggered: reversals.count || 0,
      retriesBlocked: blockedCount,
      revenueRecoveredAmount: revenueRecovered.total || 0,
      avgLimboResolutionSec: Math.round(limboTimes.avg_sec || 42),
      merchantApprovalStanding: parseFloat(approvalStanding.toFixed(1)),
      isSimulatorRunning: paymentSimulator.isSimulationRunning
    });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// 2. Transactions Table
app.get('/api/transactions', async (req, res) => {
  try {
    const { status, bank, limit = 50 } = req.query;
    let sql = `SELECT * FROM transactions`;
    let params = [];
    let conditions = [];

    if (status && status !== 'all') {
      conditions.push(`visible_status = ?`);
      params.push(status);
    }
    if (bank && bank !== 'all') {
      conditions.push(`issuing_bank = ?`);
      params.push(bank);
    }

    if (conditions.length > 0) {
      sql += ` WHERE ` + conditions.join(' AND ');
    }

    sql += ` ORDER BY created_at DESC LIMIT ?`;
    params.push(parseInt(limit));

    const transactions = await db.all(sql, params);
    res.json(transactions);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// 3. Engine Event Audit Logs
app.get('/api/events', async (req, res) => {
  try {
    const limit = req.query.limit || 30;
    const events = await db.all(
      `SELECT * FROM event_logs ORDER BY id DESC LIMIT ?`,
      [parseInt(limit)]
    );
    res.json(events);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// 4. Retry Budget Counters
app.get('/api/retry-budgets', async (req, res) => {
  try {
    const budgets = await db.all(`SELECT * FROM retry_budgets ORDER BY merchant_id, issuing_bank`);
    res.json(budgets);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// 5. Trigger Single or Batch Simulated Transaction
app.post('/api/simulate/trigger', async (req, res) => {
  try {
    const { bank, rail, count = 1, forceLimbo = false } = req.body;
    const created = [];
    for (let i = 0; i < count; i++) {
      const txn = await paymentSimulator.createTransaction({ bank, rail, forceLimbo });
      created.push(txn);
    }
    broadcastSSE('NEW_TRANSACTION', { count: created.length });
    res.json({ success: true, count: created.length, transactions: created });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// 6. Toggle Automatic Continuous Simulator
app.post('/api/simulate/toggle', (req, res) => {
  try {
    const { action } = req.body;
    if (action === 'start') {
      paymentSimulator.startContinuousSimulation(2500);
    } else {
      paymentSimulator.stopContinuousSimulation();
    }
    broadcastSSE('SIMULATOR_STATUS', { isRunning: paymentSimulator.isSimulationRunning });
    res.json({ isRunning: paymentSimulator.isSimulationRunning });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// 7. Server-Sent Events (SSE) Stream
app.get('/api/stream', (req, res) => {
  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');

  const clientId = Date.now();
  const newClient = { id: clientId, res };
  sseClients.push(newClient);

  req.on('close', () => {
    sseClients = sseClients.filter(c => c.id !== clientId);
  });
});

// Seed initial demo data & start engine background workers
async function startApp() {
  await db.initDatabase();

  // Seed sample transactions if DB is fresh
  const countRow = await db.get(`SELECT COUNT(*) as count FROM transactions`);
  if (countRow.count === 0) {
    console.log('Seeding initial baseline simulation data...');
    for (let i = 0; i < 15; i++) {
      await paymentSimulator.createTransaction();
    }
    // Force a couple of explicit Limbo & Failed transactions for immediate UI demonstration
    await paymentSimulator.createTransaction({ bank: 'SBI', rail: 'UPI_AUTOPAY', forceLimbo: true });
    await paymentSimulator.createTransaction({ bank: 'HDFC', rail: 'NACH', forceLimbo: true });
  }

  // Start background engine components
  activePoller.start(2000);
  decisionEngine.start(2500);
  retryBudgetManager.start(3000);
  paymentSimulator.startContinuousSimulation(3000);

  app.listen(PORT, () => {
    console.log(`===================================================`);
    console.log(`🚀 Project Limbo — Payment Certainty Engine Live!`);
    console.log(`🌐 Dashboard running at: http://localhost:${PORT}`);
    console.log(`===================================================`);
  });
}

startApp().catch(err => {
  console.error('Fatal initialization error:', err);
});
