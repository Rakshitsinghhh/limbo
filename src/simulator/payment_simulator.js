const db = require('../database/db');
const bankProfiles = require('../config/bank_profiles.json');

const MERCHANTS = ['MERCHANT_ALPHA', 'MERCHANT_BETA', 'MERCHANT_GAMMA', 'MERCHANT_DELTA'];
const BANKS = ['HDFC', 'SBI', 'ICICI', 'AXIS', 'KOTAK'];
const RAILS = ['UPI_AUTOPAY', 'NACH', 'CARD'];
const FAILURE_REASONS = ['INSUFFICIENT_FUNDS', 'BANK_TIMEOUT', 'RISK_DECLINE', 'NETWORK_ERROR'];

class PaymentSimulator {
  constructor() {
    this.isSimulationRunning = false;
    this.simulationInterval = null;
    this.speedMultiplier = 1; // 1x, 5x, 10x real-time acceleration
  }

  setSpeed(multiplier) {
    this.speedMultiplier = Math.max(1, Math.min(60, multiplier));
  }

  generateRandomTransaction(customParams = {}) {
    const bankKey = customParams.bank || BANKS[Math.floor(Math.random() * BANKS.length)];
    const rail = customParams.rail || RAILS[Math.floor(Math.random() * RAILS.length)];
    const merchantId = customParams.merchantId || MERCHANTS[Math.floor(Math.random() * MERCHANTS.length)];
    const amount = customParams.amount || Math.floor(Math.random() * 4500) + 100;
    const customerId = customParams.customerId || `CUST_${Math.floor(Math.random() * 90000) + 10000}`;

    const profile = bankProfiles[bankKey];
    const railConfig = profile.rails[rail];

    const randomVal = Math.random();
    let visibleStatus = 'pending';
    let trueStatus = 'success';
    let failureReason = 'NONE';
    let delaySec = 0;

    const limboProb = customParams.forceLimbo ? 1.0 : railConfig.limbo_probability;

    if (!customParams.forceLimbo && randomVal < 0.65) {
      // Instant Success
      visibleStatus = 'success';
      trueStatus = 'success';
      delaySec = 0;
    } else if (!customParams.forceLimbo && randomVal < 0.75) {
      // Instant Failure
      visibleStatus = 'failed';
      trueStatus = 'failed';
      failureReason = FAILURE_REASONS[Math.floor(Math.random() * FAILURE_REASONS.length)];
      delaySec = 0;
    } else {
      // Limbo state (Delayed confirmation)
      visibleStatus = 'pending';
      // Probability that limbo resolves to success
      const resolvesToSuccess = Math.random() < railConfig.success_rate;
      trueStatus = resolvesToSuccess ? 'success' : 'failed';
      if (!resolvesToSuccess) {
        failureReason = FAILURE_REASONS[Math.floor(Math.random() * FAILURE_REASONS.length)];
      }

      // Random delay simulated in seconds (scaled for demo)
      // Standard demo scaling: 1 minute real delay -> 15-90 seconds in demo
      const baseDelay = railConfig.delay_mean_sec / 2;
      delaySec = Math.floor(baseDelay * (0.5 + Math.random()));
    }

    const now = new Date();
    const debitTimestamp = now.toISOString();
    const expectedWindowSec = railConfig.expected_window_sec;
    
    // SLA deadline = debit_timestamp + expected_window_sec * 2
    const slaDeadline = new Date(now.getTime() + (expectedWindowSec * 2 * 1000)).toISOString();
    
    // True resolution time = debit_timestamp + delaySec
    const trueResolutionTime = new Date(now.getTime() + (delaySec * 1000)).toISOString();

    const txnId = `TXN_${Date.now()}_${Math.floor(Math.random() * 1000)}`;

    return {
      id: txnId,
      merchant_id: merchantId,
      customer_id: customerId,
      issuing_bank: bankKey,
      rail: rail,
      amount: amount,
      visible_status: visibleStatus,
      true_status: trueStatus,
      failure_reason: failureReason,
      debit_timestamp: debitTimestamp,
      expected_window_sec: expectedWindowSec,
      sla_deadline: slaDeadline,
      true_resolution_time: trueResolutionTime,
      is_ambiguous: 0,
      probability_score: 0.0,
      retry_count: 0,
      action_taken: 'NONE'
    };
  }

  async createTransaction(customParams = {}) {
    const txn = this.generateRandomTransaction(customParams);
    
    await db.run(
      `INSERT INTO transactions (
        id, merchant_id, customer_id, issuing_bank, rail, amount,
        visible_status, true_status, failure_reason, debit_timestamp,
        expected_window_sec, sla_deadline, true_resolution_time, is_ambiguous,
        probability_score, retry_count, action_taken
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      [
        txn.id, txn.merchant_id, txn.customer_id, txn.issuing_bank, txn.rail, txn.amount,
        txn.visible_status, txn.true_status, txn.failure_reason, txn.debit_timestamp,
        txn.expected_window_sec, txn.sla_deadline, txn.true_resolution_time, txn.is_ambiguous,
        txn.probability_score, txn.retry_count, txn.action_taken
      ]
    );

    await db.run(
      `INSERT INTO event_logs (transaction_id, merchant_id, event_type, message)
       VALUES (?, ?, ?, ?)`,
      [
        txn.id,
        txn.merchant_id,
        'TRANSACTION_CREATED',
        `Transaction ${txn.id} created via ${txn.rail} (${txn.issuing_bank}) with visible status: ${txn.visible_status.toUpperCase()}`
      ]
    );

    return txn;
  }

  /**
   * Mock Bank/NPCI Status Query API
   * Represents querying HDFC / SBI / NPCI status endpoints
   */
  async queryBankApi(txnId) {
    const txn = await db.get(`SELECT * FROM transactions WHERE id = ?`, [txnId]);
    if (!txn) {
      return { status: 'NOT_FOUND', detail: 'Transaction ID not registered at Bank gateway' };
    }

    const now = new Date().getTime();
    const resolutionTime = new Date(txn.true_resolution_time).getTime();

    if (now < resolutionTime) {
      return {
        status: 'PENDING_BANK_PROCESSING',
        bank_ref: `NPCI_REF_${txn.id}`,
        message: 'Transaction debited at bank; awaiting final settlement message'
      };
    } else {
      return {
        status: txn.true_status === 'success' ? 'SUCCESS' : 'FAILED',
        bank_ref: `NPCI_SETTLED_${txn.id}`,
        failure_reason: txn.failure_reason,
        message: txn.true_status === 'success'
          ? 'Confirmation received: Payment settled to merchant account'
          : `Decline confirmed: ${txn.failure_reason}`
      };
    }
  }

  startContinuousSimulation(intervalMs = 3000) {
    if (this.isSimulationRunning) return;
    this.isSimulationRunning = true;
    console.log(`Payment Simulator started (Interval: ${intervalMs}ms)`);

    this.simulationInterval = setInterval(async () => {
      try {
        await this.createTransaction();
      } catch (err) {
        console.error('Simulation step error:', err.message);
      }
    }, intervalMs);
  }

  stopContinuousSimulation() {
    if (!this.isSimulationRunning) return;
    clearInterval(this.simulationInterval);
    this.isSimulationRunning = false;
    console.log('Payment Simulator paused');
  }
}

module.exports = new PaymentSimulator();
