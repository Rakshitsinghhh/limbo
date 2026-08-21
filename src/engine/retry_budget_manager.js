const db = require('../database/db');
const predictor = require('./predictor');
const bankProfiles = require('../config/bank_profiles.json');

class RetryBudgetManager {
  constructor() {
    this.isRunning = false;
    this.interval = null;
  }

  async getOrCreateBudget(merchantId, issuingBank) {
    let budget = await db.get(
      `SELECT * FROM retry_budgets WHERE merchant_id = ? AND issuing_bank = ?`,
      [merchantId, issuingBank]
    );

    if (!budget) {
      const profile = bankProfiles[issuingBank] || bankProfiles['HDFC'];
      const dailyLimit = profile.retry_budget.daily_limit_per_merchant;

      await db.run(
        `INSERT INTO retry_budgets (merchant_id, issuing_bank, retries_used, retries_blocked, daily_limit)
         VALUES (?, ?, 0, 0, ?)`,
        [merchantId, issuingBank, dailyLimit]
      );

      budget = await db.get(
        `SELECT * FROM retry_budgets WHERE merchant_id = ? AND issuing_bank = ?`,
        [merchantId, issuingBank]
      );
    }

    return budget;
  }

  async processFailedTransactionRetries() {
    try {
      // Find failed transactions that haven't had retry action evaluated yet
      const failedTxns = await db.all(
        `SELECT * FROM transactions 
         WHERE visible_status = 'failed' 
           AND retry_count < 3 
           AND action_taken NOT IN ('RETRY_BLOCKED', 'RECOVERED_BY_RETRY', 'MAX_RETRIES_EXCEEDED')`
      );

      for (const txn of failedTxns) {
        const retryScore = predictor.scoreRetryWorthiness(txn);
        const budget = await this.getOrCreateBudget(txn.merchant_id, txn.issuing_bank);

        await db.run(
          `UPDATE transactions SET retry_score = ? WHERE id = ?`,
          [retryScore, txn.id]
        );

        const isBudgetExhausted = budget.retries_used >= budget.daily_limit;
        const isLowWorthiness = retryScore < 0.45;

        if (isBudgetExhausted || isLowWorthiness) {
          // Block retry to protect merchant approval standing with bank
          await db.run(
            `UPDATE transactions SET action_taken = 'RETRY_BLOCKED' WHERE id = ?`,
            [txn.id]
          );

          await db.run(
            `UPDATE retry_budgets 
             SET retries_blocked = retries_blocked + 1 
             WHERE merchant_id = ? AND issuing_bank = ?`,
            [txn.merchant_id, txn.issuing_bank]
          );

          const reason = isBudgetExhausted ? 'Merchant-Bank budget exhausted' : `Low retry score (P=${retryScore})`;

          await db.run(
            `INSERT INTO event_logs (transaction_id, merchant_id, event_type, message, metadata)
             VALUES (?, ?, ?, ?, ?)`,
            [
              txn.id,
              txn.merchant_id,
              'RETRY_BLOCKED',
              `Smart Retry Budgeting blocked retry for ${txn.id} on ${txn.issuing_bank}: ${reason}. Merchant approval rating preserved.`,
              JSON.stringify({ retryScore, failureReason: txn.failure_reason, budgetUsed: budget.retries_used, limit: budget.daily_limit })
            ]
          );
        } else {
          // Allow smart retry
          const nextRetryCount = txn.retry_count + 1;

          await db.run(
            `UPDATE retry_budgets 
             SET retries_used = retries_used + 1 
             WHERE merchant_id = ? AND issuing_bank = ?`,
            [txn.merchant_id, txn.issuing_bank]
          );

          // Retry outcome simulation based on retryScore probability
          const retrySuccessful = Math.random() < retryScore;

          if (retrySuccessful) {
            await db.run(
              `UPDATE transactions 
               SET visible_status = 'success', retry_count = ?, action_taken = 'RECOVERED_BY_RETRY' 
               WHERE id = ?`,
              [nextRetryCount, txn.id]
            );

            await db.run(
              `INSERT INTO event_logs (transaction_id, merchant_id, event_type, message, metadata)
               VALUES (?, ?, ?, ?, ?)`,
              [
                txn.id,
                txn.merchant_id,
                'RETRY_EXECUTED',
                `Smart Retry SUCCESS! Recovered ₹${txn.amount} on attempt #${nextRetryCount} (Score: ${retryScore}).`,
                JSON.stringify({ attempt: nextRetryCount, retryScore, recoveredAmount: txn.amount })
              ]
            );
          } else {
            await db.run(
              `UPDATE transactions 
               SET retry_count = ?, action_taken = ? 
               WHERE id = ?`,
              [nextRetryCount, nextRetryCount >= 3 ? 'MAX_RETRIES_EXCEEDED' : 'RETRY_FAILED', txn.id]
            );

            await db.run(
              `INSERT INTO event_logs (transaction_id, merchant_id, event_type, message)
               VALUES (?, ?, ?, ?)`,
              [
                txn.id,
                txn.merchant_id,
                'RETRY_EXECUTED',
                `Smart Retry Attempt #${nextRetryCount} failed for ${txn.id} (${txn.issuing_bank}).`
              ]
            );
          }
        }
      }
    } catch (err) {
      console.error('Retry Budget Manager error:', err.message);
    }
  }

  start(intervalMs = 3000) {
    if (this.isRunning) return;
    this.isRunning = true;
    console.log(`Retry Budget Manager started (Interval: ${intervalMs}ms)`);

    this.interval = setInterval(() => {
      this.processFailedTransactionRetries();
    }, intervalMs);
  }

  stop() {
    if (!this.isRunning) return;
    clearInterval(this.interval);
    this.isRunning = false;
    console.log('Retry Budget Manager stopped');
  }
}

module.exports = new RetryBudgetManager();
