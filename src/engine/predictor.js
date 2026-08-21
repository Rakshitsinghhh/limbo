const bankProfiles = require('../config/bank_profiles.json');

class Predictor {
  /**
   * Predicts the probability that a pending/limbo transaction will resolve successfully on its own.
   * Pillar 1 - Step 3 in PDF specification.
   */
  predictResolutionProbability(txn) {
    const bankKey = txn.issuing_bank;
    const rail = txn.rail;
    const profile = bankProfiles[bankKey] || bankProfiles['HDFC'];
    const railConfig = profile.rails[rail] || profile.rails['UPI_AUTOPAY'];

    const baseSuccessRate = railConfig.success_rate;

    const debitTime = new Date(txn.debit_timestamp).getTime();
    const now = new Date().getTime();
    const ageSec = Math.max(0, (now - debitTime) / 1000);
    const expectedWindow = txn.expected_window_sec;

    // Time decay factor: if age exceeds expected window, confidence decays
    let timeFactor = 1.0;
    if (ageSec > expectedWindow) {
      const excessSec = ageSec - expectedWindow;
      // Decay lambda tuned per rail
      const lambda = rail === 'UPI_AUTOPAY' ? 0.005 : rail === 'CARD' ? 0.01 : 0.0001;
      timeFactor = Math.exp(-lambda * excessSec);
    }

    // Time-of-day adjustment (Off-peak bank batch processing 1 AM - 4 AM)
    const hour = new Date(txn.debit_timestamp).getHours();
    let todFactor = 1.0;
    if (hour >= 1 && hour <= 4) {
      todFactor = 0.90;
    }

    // Calculate final probability score
    let score = baseSuccessRate * timeFactor * todFactor;
    score = Math.min(0.99, Math.max(0.05, score));

    return parseFloat(score.toFixed(3));
  }

  /**
   * Scores the likelihood of a failed transaction succeeding if retried right now.
   * Pillar 2 - Step 1 in PDF specification.
   */
  scoreRetryWorthiness(txn) {
    const bankKey = txn.issuing_bank;
    const failureReason = txn.failure_reason || 'BANK_TIMEOUT';
    const retryCount = txn.retry_count || 0;

    const profile = bankProfiles[bankKey] || bankProfiles['HDFC'];
    const recoveryRates = profile.failure_recovery_rates || {};

    const baseRecovery = recoveryRates[failureReason] !== undefined
      ? recoveryRates[failureReason]
      : 0.50;

    // Multi-attempt decay: consecutive retries decrease likelihood of success
    const attemptDecay = Math.pow(0.65, retryCount);

    // Salary credit date boost (1st - 5th of month) for INSUFFICIENT_FUNDS
    const dayOfMonth = new Date().getDate();
    let salaryBoost = 1.0;
    if (failureReason === 'INSUFFICIENT_FUNDS' && (dayOfMonth <= 5 || dayOfMonth >= 28)) {
      salaryBoost = 1.35;
    }

    // Bank maintenance window check (1 AM - 3 AM)
    const currentHour = new Date().getHours();
    let maintenancePenalty = 1.0;
    if (currentHour >= 1 && currentHour <= 3) {
      maintenancePenalty = 0.40;
    }

    let score = baseRecovery * attemptDecay * salaryBoost * maintenancePenalty;
    score = Math.min(0.98, Math.max(0.02, score));

    return parseFloat(score.toFixed(3));
  }
}

module.exports = new Predictor();
