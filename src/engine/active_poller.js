const db = require('../database/db');
const paymentSimulator = require('../simulator/payment_simulator');
const predictor = require('./predictor');

class ActivePoller {
  constructor() {
    this.isPolling = false;
    this.pollInterval = null;
  }

  async pollPendingTransactions() {
    try {
      // Fetch all transactions currently stuck in 'pending'
      const pendingTxns = await db.all(
        `SELECT * FROM transactions WHERE visible_status = 'pending'`
      );

      const now = new Date().getTime();

      for (const txn of pendingTxns) {
        const debitTime = new Date(txn.debit_timestamp).getTime();
        const ageSec = (now - debitTime) / 1000;

        // Step 1: Spot ambiguity early
        if (ageSec > txn.expected_window_sec && txn.is_ambiguous === 0) {
          await db.run(
            `UPDATE transactions SET is_ambiguous = 1 WHERE id = ?`,
            [txn.id]
          );

          await db.run(
            `INSERT INTO event_logs (transaction_id, merchant_id, event_type, message)
             VALUES (?, ?, ?, ?)`,
            [
              txn.id,
              txn.merchant_id,
              'AMBIGUITY_FLAGGED',
              `Transaction ${txn.id} crossed normal confirmation window (${txn.expected_window_sec}s). Flagged as AMBIGUOUS.`
            ]
          );
        }

        // Step 2 & 3: Calculate prediction score & actively check status
        const probabilityScore = predictor.predictResolutionProbability(txn);
        
        await db.run(
          `UPDATE transactions SET probability_score = ?, last_polled_at = ? WHERE id = ?`,
          [probabilityScore, new Date().toISOString(), txn.id]
        );

        // Query Bank/NPCI API
        const bankResponse = await paymentSimulator.queryBankApi(txn.id);

        if (bankResponse.status === 'SUCCESS') {
          // Resolved successfully!
          await db.run(
            `UPDATE transactions 
             SET visible_status = 'success', is_ambiguous = 0, action_taken = 'AUTO_RESOLVED_SUCCESS'
             WHERE id = ?`,
            [txn.id]
          );

          await db.run(
            `INSERT INTO event_logs (transaction_id, merchant_id, event_type, message)
             VALUES (?, ?, ?, ?)`,
            [
              txn.id,
              txn.merchant_id,
              'STATUS_POLLED',
              `Active polling confirmed resolution for ${txn.id}: SETTLED (P=${probabilityScore})`
            ]
          );
        } else if (bankResponse.status === 'FAILED') {
          // Resolved to failure
          await db.run(
            `UPDATE transactions 
             SET visible_status = 'failed', is_ambiguous = 0, failure_reason = ?
             WHERE id = ?`,
            [bankResponse.failure_reason || 'BANK_TIMEOUT', txn.id]
          );

          await db.run(
            `INSERT INTO event_logs (transaction_id, merchant_id, event_type, message)
             VALUES (?, ?, ?, ?)`,
            [
              txn.id,
              txn.merchant_id,
              'STATUS_POLLED',
              `Active polling confirmed failure for ${txn.id}: ${bankResponse.failure_reason} (P=${probabilityScore})`
            ]
          );
        }
      }
    } catch (err) {
      console.error('Active Poller execution error:', err.message);
    }
  }

  start(intervalMs = 2000) {
    if (this.isPolling) return;
    this.isPolling = true;
    console.log(`Active Poller started (Interval: ${intervalMs}ms)`);

    this.pollInterval = setInterval(() => {
      this.pollPendingTransactions();
    }, intervalMs);
  }

  stop() {
    if (!this.isPolling) return;
    clearInterval(this.pollInterval);
    this.isPolling = false;
    console.log('Active Poller stopped');
  }
}

module.exports = new ActivePoller();
