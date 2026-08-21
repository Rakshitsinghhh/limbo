const db = require('../database/db');

class DecisionEngine {
  constructor() {
    this.isRunning = false;
    this.interval = null;
  }

  async processLimboDecisions() {
    try {
      const ambiguousTxns = await db.all(
        `SELECT * FROM transactions WHERE visible_status = 'pending' AND is_ambiguous = 1`
      );

      const now = new Date().getTime();

      for (const txn of ambiguousTxns) {
        const score = txn.probability_score;
        const slaDeadlineTime = new Date(txn.sla_deadline).getTime();
        const isNearSla = (slaDeadlineTime - now) < (txn.expected_window_sec * 1000);
        const isSlaBreached = now >= slaDeadlineTime;

        if (score >= 0.75) {
          // Action: Wait Quietly
          if (txn.action_taken !== 'WAIT_QUIETLY') {
            await db.run(
              `UPDATE transactions SET action_taken = 'WAIT_QUIETLY' WHERE id = ?`,
              [txn.id]
            );

            await db.run(
              `INSERT INTO event_logs (transaction_id, merchant_id, event_type, message)
               VALUES (?, ?, ?, ?)`,
              [
                txn.id,
                txn.merchant_id,
                'DECISION_WAIT_QUIETLY',
                `High confidence (P=${score}). Engine waiting quietly for bank confirmation on ${txn.id}.`
              ]
            );
          }
        } else if (score >= 0.35 && isNearSla) {
          // Action: Proactive Customer Notification
          if (txn.action_taken !== 'NOTIFY_CUSTOMER') {
            await db.run(
              `UPDATE transactions SET action_taken = 'NOTIFY_CUSTOMER' WHERE id = ?`,
              [txn.id]
            );

            await db.run(
              `INSERT INTO event_logs (transaction_id, merchant_id, event_type, message, metadata)
               VALUES (?, ?, ?, ?, ?)`,
              [
                txn.id,
                txn.merchant_id,
                'NOTIFICATION_SENT',
                `Proactive SMS/Email dispatched to Customer ${txn.customer_id}: Payment of ₹${txn.amount} is debited and being tracked with ${txn.issuing_bank}. No re-payment needed.`,
                JSON.stringify({ probability: score, amount: txn.amount, bank: txn.issuing_bank })
              ]
            );
          }
        } else if (score < 0.35 && isSlaBreached) {
          // Action: Trigger Automatic Reversal
          if (txn.action_taken !== 'AUTO_REVERSAL') {
            await db.run(
              `UPDATE transactions SET visible_status = 'reversed', action_taken = 'AUTO_REVERSAL', is_ambiguous = 0 WHERE id = ?`,
              [txn.id]
            );

            await db.run(
              `INSERT INTO event_logs (transaction_id, merchant_id, event_type, message, metadata)
               VALUES (?, ?, ?, ?, ?)`,
              [
                txn.id,
                txn.merchant_id,
                'REVERSAL_TRIGGERED',
                `Low confidence (P=${score}) & SLA breached. Reversal triggered automatically for ${txn.id} (₹${txn.amount}). Customer refunded.`,
                JSON.stringify({ probability: score, amount: txn.amount, bank: txn.issuing_bank })
              ]
            );
          }
        }
      }
    } catch (err) {
      console.error('Decision Engine processing error:', err.message);
    }
  }

  start(intervalMs = 2500) {
    if (this.isRunning) return;
    this.isRunning = true;
    console.log(`Decision Engine started (Interval: ${intervalMs}ms)`);

    this.interval = setInterval(() => {
      this.processLimboDecisions();
    }, intervalMs);
  }

  stop() {
    if (!this.isRunning) return;
    clearInterval(this.interval);
    this.isRunning = false;
    console.log('Decision Engine stopped');
  }
}

module.exports = new DecisionEngine();
