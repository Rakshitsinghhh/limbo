document.addEventListener('DOMContentLoaded', () => {
  // DOM Elements
  const kpiLimboPending = document.getElementById('kpiLimboPending');
  const kpiAutoResolved = document.getElementById('kpiAutoResolved');
  const kpiNotifications = document.getElementById('kpiNotifications');
  const kpiReversals = document.getElementById('kpiReversals');
  const kpiRevenue = document.getElementById('kpiRevenue');
  const kpiStanding = document.getElementById('kpiStanding');
  const kpiBlockedCount = document.getElementById('kpiBlockedCount');

  const bankSelect = document.getElementById('bankSelect');
  const railSelect = document.getElementById('railSelect');

  const triggerSingleBtn = document.getElementById('triggerSingleBtn');
  const triggerLimboBtn = document.getElementById('triggerLimboBtn');
  const triggerBatchBtn = document.getElementById('triggerBatchBtn');
  const toggleSimulatorBtn = document.getElementById('toggleSimulatorBtn');
  const simBtnText = document.getElementById('simBtnText');

  const txnTableBody = document.getElementById('txnTableBody');
  const budgetBarsContainer = document.getElementById('budgetBarsContainer');
  const logContainer = document.getElementById('logContainer');

  let currentStatusFilter = 'all';

  // 1. Fetch & Render Metrics
  async function fetchStats() {
    try {
      const res = await fetch('/api/stats');
      const data = await res.json();

      kpiLimboPending.textContent = data.limboPending;
      kpiAutoResolved.textContent = data.autoResolvedCount;
      kpiNotifications.textContent = data.notificationsSent;
      kpiReversals.textContent = data.reversalsTriggered;
      kpiRevenue.textContent = `₹${data.revenueRecoveredAmount.toLocaleString('en-IN')}`;
      kpiStanding.textContent = `${data.merchantApprovalStanding}%`;
      kpiBlockedCount.textContent = data.retriesBlocked;

      simBtnText.textContent = data.isSimulatorRunning ? 'Pause Simulation' : 'Start Simulation';
    } catch (err) {
      console.error('Failed to fetch stats:', err);
    }
  }

  // 2. Fetch & Render Transaction Table
  async function fetchTransactions() {
    try {
      const res = await fetch(`/api/transactions?status=${currentStatusFilter}&limit=40`);
      const txns = await res.json();

      if (!txns || txns.length === 0) {
        txnTableBody.innerHTML = `<tr><td colspan="6" class="text-center text-dim">No transactions recorded.</td></tr>`;
        return;
      }

      txnTableBody.innerHTML = txns.map(txn => {
        let statusBadge = '';
        if (txn.visible_status === 'pending') {
          statusBadge = `<span class="badge-clean pending">pending</span>`;
        } else if (txn.visible_status === 'success') {
          statusBadge = `<span class="badge-clean success">settled</span>`;
        } else if (txn.visible_status === 'failed') {
          statusBadge = `<span class="badge-clean failed">failed (${txn.failure_reason})</span>`;
        } else if (txn.visible_status === 'reversed') {
          statusBadge = `<span class="badge-clean reversed">reversed</span>`;
        }

        const probPercent = Math.round(txn.probability_score * 100);
        let probFillClass = '';
        if (probPercent < 40) probFillClass = 'low';
        else if (probPercent < 75) probFillClass = 'warn';

        let actionText = txn.action_taken || 'NONE';
        if (actionText === 'NOTIFY_CUSTOMER') {
          actionText = `<span class="badge-clean info">customer alerted</span>`;
        } else if (actionText === 'WAIT_QUIETLY') {
          actionText = `<span class="text-dim">wait quietly</span>`;
        } else if (actionText === 'AUTO_REVERSAL') {
          actionText = `<span class="badge-clean reversed">auto reversed</span>`;
        } else if (actionText === 'RECOVERED_BY_RETRY') {
          actionText = `<span class="badge-clean success">retry success</span>`;
        } else if (actionText === 'RETRY_BLOCKED') {
          actionText = `<span class="badge-clean failed">retry blocked</span>`;
        }

        return `
          <tr>
            <td><strong>${txn.id}</strong></td>
            <td>
              <div>${txn.issuing_bank}</div>
              <div class="text-dim">${txn.rail}</div>
            </td>
            <td><strong>₹${txn.amount.toLocaleString('en-IN')}</strong></td>
            <td>${statusBadge}</td>
            <td>
              <div class="progress-container">
                <div class="progress-track">
                  <div class="progress-fill ${probFillClass}" style="width: ${probPercent}%"></div>
                </div>
                <span>${probPercent}%</span>
              </div>
            </td>
            <td>${actionText}</td>
          </tr>
        `;
      }).join('');
    } catch (err) {
      console.error('Failed to fetch transactions:', err);
    }
  }

  // 3. Fetch & Render Retry Budgets
  async function fetchRetryBudgets() {
    try {
      const res = await fetch('/api/retry-budgets');
      const budgets = await res.json();

      if (!budgets || budgets.length === 0) {
        budgetBarsContainer.innerHTML = `<div class="text-dim">No retry activity.</div>`;
        return;
      }

      budgetBarsContainer.innerHTML = budgets.map(b => {
        const percent = Math.min(100, Math.round((b.retries_used / b.daily_limit) * 100));
        return `
          <div class="budget-row">
            <div class="budget-info">
              <span>${b.merchant_id} &rarr; ${b.issuing_bank}</span>
              <span>${b.retries_used}/${b.daily_limit} (${b.retries_blocked} blocked)</span>
            </div>
            <div class="budget-bar-track">
              <div class="budget-bar-fill" style="width: ${percent}%"></div>
            </div>
          </div>
        `;
      }).join('');
    } catch (err) {
      console.error('Failed to fetch retry budgets:', err);
    }
  }

  // 4. Fetch & Render Engine Logs
  async function fetchLogs() {
    try {
      const res = await fetch('/api/events?limit=30');
      const logs = await res.json();

      logContainer.innerHTML = logs.map(l => {
        const timeStr = new Date(l.created_at).toLocaleTimeString();
        return `
          <div class="log-entry">
            <span class="log-time">[${timeStr}]</span>
            <span class="log-key">${l.event_type}</span>:
            <span>${l.message}</span>
          </div>
        `;
      }).join('');
    } catch (err) {
      console.error('Failed to fetch logs:', err);
    }
  }

  // Event Handlers
  triggerSingleBtn.addEventListener('click', async () => {
    await fetch('/api/simulate/trigger', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ bank: bankSelect.value, rail: railSelect.value, count: 1, forceLimbo: false })
    });
    refreshAll();
  });

  triggerLimboBtn.addEventListener('click', async () => {
    await fetch('/api/simulate/trigger', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ bank: bankSelect.value, rail: railSelect.value, count: 1, forceLimbo: true })
    });
    refreshAll();
  });

  triggerBatchBtn.addEventListener('click', async () => {
    await fetch('/api/simulate/trigger', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ bank: bankSelect.value, rail: railSelect.value, count: 10, forceLimbo: false })
    });
    refreshAll();
  });

  toggleSimulatorBtn.addEventListener('click', async () => {
    const isCurrentlyRunning = simBtnText.textContent.includes('Pause');
    await fetch('/api/simulate/toggle', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: isCurrentlyRunning ? 'stop' : 'start' })
    });
    fetchStats();
  });

  // Filter Pills
  document.getElementById('txnFilterPills').addEventListener('click', (e) => {
    if (e.target.classList.contains('filter-btn')) {
      document.querySelectorAll('.filter-btn').forEach(p => p.classList.remove('active'));
      e.target.classList.add('active');
      currentStatusFilter = e.target.getAttribute('data-filter');
      fetchTransactions();
    }
  });

  // Connect Server-Sent Events (SSE) Stream
  function initSSE() {
    const eventSource = new EventSource('/api/stream');
    eventSource.addEventListener('NEW_TRANSACTION', () => refreshAll());
    eventSource.addEventListener('SIMULATOR_STATUS', () => fetchStats());
    eventSource.onerror = (err) => console.log('SSE stream issue:', err);
  }

  function refreshAll() {
    fetchStats();
    fetchTransactions();
    fetchRetryBudgets();
    fetchLogs();
  }

  // Initial load and fast polling update
  refreshAll();
  setInterval(refreshAll, 2000);
  initSSE();
});
