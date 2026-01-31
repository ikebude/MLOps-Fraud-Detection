/**
 * FraudGuard Live Dashboard - Real-time Metrics, Alerts, and Transactions
 * ADVANCED: WebSocket-ready, Live Metrics Gauges, Alert Notifications, Performance Tracking
 */

(function () {
  'use strict';

  // ============================================================================
  // CONFIGURATION
  // ============================================================================
  const CONFIG = {
    API_ENDPOINT: '/api',
    STREAM_ENDPOINT: '/stream/transactions',
    REFRESH_INTERVAL: 2000,      // Poll every 2 seconds
    ALERT_TIMEOUT: 5000,          // Alert display duration
    METRIC_UPDATE_ANIMATION: 300, // Smooth metric transitions
    HIGH_RISK_THRESHOLD: 70,      // Risk score >= 70 = alert
  };

  // ============================================================================
  // STATE MANAGEMENT
  // ============================================================================
  const State = {
    metrics: {
      total_transactions: 0,
      fraud_detections: 0,
      fraud_rate: 0,
      approval_rate: 100,
      avg_risk_score: 0,
      predictions_per_minute: 0,
      avg_latency_ms: 0,
    },
    transactions: [],
    alerts: [],
    lastUpdate: null,
    isStreamConnected: false,
  };

  // ============================================================================
  // UTILITY FUNCTIONS
  // ============================================================================

  function el(id) {
    return document.getElementById(id);
  }

  function updateMetric(id, val, animate = true) {
    const elem = el(id);
    if (!elem) return;
    if (animate) {
      elem.style.opacity = '0.5';
      setTimeout(() => {
        elem.textContent = val;
        elem.style.opacity = '1';
        elem.style.transition = 'opacity 0.3s ease-in-out';
      }, 50);
    } else {
      elem.textContent = val;
    }
  }

  function formatTime(isoString) {
    if (!isoString) return '—';
    try {
      const d = new Date(isoString);
      if (isNaN(d.getTime())) return isoString;
      return d.toLocaleString('en-US', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: true,
      });
    } catch (e) {
      return isoString;
    }
  }

  function formatCurrency(amount, currency = 'NGN') {
    try {
      return `${currency} ${parseFloat(amount).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    } catch (e) {
      return `${currency} ${amount}`;
    }
  }

  function getRiskColor(score) {
    if (score >= 80) return { bg: 'bg-red-50', text: 'text-red-600', class: 'danger' };
    if (score >= 50) return { bg: 'bg-orange-50', text: 'text-orange-600', class: 'warning' };
    return { bg: 'bg-green-50', text: 'text-green-600', class: 'safe' };
  }

  function getStatusColor(status) {
    const colors = {
      'Approved': { bg: 'bg-green-100', text: 'text-green-800' },
      'Flagged': { bg: 'bg-orange-100', text: 'text-orange-800' },
      'Declined': { bg: 'bg-red-100', text: 'text-red-800' },
    };
    return colors[status] || { bg: 'bg-gray-100', text: 'text-gray-800' };
  }

  // ============================================================================
  // ALERTS SYSTEM
  // ============================================================================

  const AlertSystem = {
    queue: [],

    add(type, title, message, data = {}) {
      const alert = {
        id: Date.now(),
        type, // 'fraud', 'warning', 'info', 'success'
        title,
        message,
        data,
        timestamp: new Date(),
      };
      this.queue.unshift(alert);
      if (this.queue.length > 20) this.queue.pop(); // Keep last 20 alerts
      this.render();
      if (type !== 'info') {
        this.showNotification(alert);
      }
      return alert.id;
    },

    showNotification(alert) {
      const notifContainer = el('live-alerts-container');
      if (!notifContainer) return;

      const div = document.createElement('div');
      div.className = `p-4 rounded-lg shadow-lg mb-3 animate-slide-in ${
        alert.type === 'fraud' ? 'bg-red-600' :
        alert.type === 'warning' ? 'bg-orange-500' :
        alert.type === 'success' ? 'bg-green-500' : 'bg-blue-500'
      } text-white text-sm`;
      div.innerHTML = `<strong>${alert.title}:</strong> ${alert.message}`;
      notifContainer.appendChild(div);

      setTimeout(() => {
        div.style.animation = 'slide-out 0.3s ease-out forwards';
        setTimeout(() => div.remove(), 300);
      }, CONFIG.ALERT_TIMEOUT);
    },

    render() {
      const container = el('alerts-list');
      if (!container) return;
      container.innerHTML = '';
      this.queue.slice(0, 10).forEach(alert => {
        const div = document.createElement('div');
        const typeClass = {
          'fraud': 'border-l-4 border-red-500 bg-red-50',
          'warning': 'border-l-4 border-orange-500 bg-orange-50',
          'success': 'border-l-4 border-green-500 bg-green-50',
          'info': 'border-l-4 border-blue-500 bg-blue-50',
        }[alert.type] || 'border-l-4 border-gray-500 bg-gray-50';

        div.className = `p-4 mb-2 ${typeClass} rounded`;
        div.innerHTML = `
          <p class="font-semibold text-sm">${alert.title}</p>
          <p class="text-xs text-gray-600 mt-1">${alert.message}</p>
          <p class="text-xs text-gray-500 mt-1">${alert.timestamp.toLocaleTimeString()}</p>
        `;
        container.appendChild(div);
      });
    },
  };

  // ============================================================================
  // METRICS DASHBOARD
  // ============================================================================

  const MetricsDashboard = {
    async refresh() {
      try {
        const resp = await fetch(`${CONFIG.API_ENDPOINT}/inference/details`);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();

        const stats = data.stats || {};
        const results = data.results || {};

        // Update state
        State.metrics = {
          total_transactions: stats.total_records || 0,
          fraud_detections: stats.fraud_detections || 0,
          fraud_rate: (stats.fraud_rate || 0).toFixed(1),
          approval_rate: (100 - (stats.fraud_rate || 0)).toFixed(1),
          avg_risk_score: (stats.avg_fraud_probability || 0 * 100).toFixed(1),
          predictions_per_minute: stats.predictions_per_minute || 0,
          avg_latency_ms: stats.avg_latency_ms || 0,
        };

        State.lastUpdate = new Date();

        // Update DOM with animation
        updateMetric('metric-total-txns', State.metrics.total_transactions);
        updateMetric('metric-fraud-count', State.metrics.fraud_detections);
        updateMetric('metric-fraud-rate', State.metrics.fraud_rate + '%');
        updateMetric('metric-approval-rate', State.metrics.approval_rate + '%');
        updateMetric('metric-avg-risk', State.metrics.avg_risk_score.toFixed(0));
        updateMetric('metric-ppm', State.metrics.predictions_per_minute.toFixed(1));
        updateMetric('metric-latency', State.metrics.avg_latency_ms.toFixed(0) + 'ms');

        // Update gauges
        this.updateGauges();

        // Check for high-risk transactions and create alerts
        this.checkForAlerts(results);

      } catch (e) {
        console.error('Metrics refresh failed:', e);
        AlertSystem.add('warning', 'Metrics Update Failed', 'Could not fetch latest metrics');
      }
    },

    updateGauges() {
      // Fraud Rate Gauge (circular)
      const fraudGauge = el('gauge-fraud-rate');
      if (fraudGauge) {
        const rate = parseFloat(State.metrics.fraud_rate) || 0;
        fraudGauge.style.conic-gradient = `conic-gradient(rgb(239, 68, 68) 0deg ${rate * 3.6}deg, rgb(229, 231, 235) ${rate * 3.6}deg)`;
      }

      // Approval Rate Gauge
      const approvalGauge = el('gauge-approval-rate');
      if (approvalGauge) {
        const rate = parseFloat(State.metrics.approval_rate) || 100;
        approvalGauge.style.conic-gradient = `conic-gradient(rgb(34, 197, 94) 0deg ${rate * 3.6}deg, rgb(229, 231, 235) ${rate * 3.6}deg)`;
      }
    },

    checkForAlerts(results) {
      if (!results || !Array.isArray(results.transactions)) return;

      results.transactions.slice(0, 5).forEach(txn => {
        const risk = txn.risk_score || 0;
        if (risk >= CONFIG.HIGH_RISK_THRESHOLD) {
          const merchant = txn.merchant || txn.user_id || 'Unknown';
          const amount = formatCurrency(txn.amount, txn.currency);
          AlertSystem.add('fraud', '🚨 HIGH RISK TRANSACTION', 
            `${merchant} - ${amount} (Risk: ${risk}/100)`);
        }
      });
    },
  };

  // ============================================================================
  // TRANSACTIONS TABLE
  // ============================================================================

  const TransactionsTable = {
    renderTable(rows) {
      const tbody = el('txn-table-body');
      if (!tbody) return;

      tbody.innerHTML = '';
      const slice = (rows || []).slice(0, 15); // Show more rows

      slice.forEach(r => {
        const riskColor = getRiskColor(r.risk_score);
        const statusColor = getStatusColor(r.status);

        const tr = document.createElement('tr');
        tr.className = 'hover:bg-gray-50 transition-colors';
        tr.innerHTML = `
          <td class="px-6 py-4 whitespace-nowrap text-xs text-gray-500">${formatTime(r.time)}</td>
          <td class="px-6 py-4 font-mono text-xs text-gray-600">${r.id}</td>
          <td class="px-6 py-4 font-medium text-gray-900 text-sm">${r.merchant}</td>
          <td class="px-6 py-4 text-gray-900 text-sm font-semibold">${formatCurrency(r.amount, r.currency)}</td>
          <td class="px-6 py-4">
            <span class="inline-flex items-center px-3 py-1 rounded-full text-xs font-bold ${riskColor.bg} ${riskColor.text}">
              ${r.risk_score}
            </span>
          </td>
          <td class="px-6 py-4">
            <span class="inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold ${statusColor.bg} ${statusColor.text}">
              ${r.status}
            </span>
          </td>
        `;
        tbody.appendChild(tr);
      });
    },
  };

  // ============================================================================
  // CHARTS INTEGRATION (Chart.js)
  // ============================================================================

  const Charts = {
    fraudTrendChart: null,
    fraudCategoryChart: null,

    initialize() {
      this.initFraudTrendChart();
      this.initFraudCategoryChart();
    },

    initFraudTrendChart() {
      const ctx = el('chart-fraud-trend');
      if (!ctx) return;

      this.fraudTrendChart = new Chart(ctx, {
        type: 'line',
        data: {
          labels: [],
          datasets: [{
            label: 'Fraud Rate (%)',
            data: [],
            borderColor: 'rgb(239, 68, 68)',
            backgroundColor: 'rgba(239, 68, 68, 0.1)',
            tension: 0.3,
            fill: true,
            pointRadius: 3,
            pointBackgroundColor: 'rgb(239, 68, 68)',
          }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: true,
          plugins: {
            legend: { display: true, position: 'top' },
            title: { display: true, text: 'Fraud Rate Over Time' },
          },
          scales: {
            y: { beginAtZero: true, max: 100 },
          },
        },
      });
    },

    initFraudCategoryChart() {
      const ctx = el('chart-fraud-category');
      if (!ctx) return;

      this.fraudCategoryChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
          labels: ['Approved', 'Flagged', 'Declined'],
          datasets: [{
            data: [0, 0, 0],
            backgroundColor: [
              'rgba(34, 197, 94, 0.8)',
              'rgba(251, 146, 60, 0.8)',
              'rgba(239, 68, 68, 0.8)',
            ],
          }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: true,
          plugins: {
            legend: { display: true, position: 'right' },
            title: { display: true, text: 'Transaction Status Distribution' },
          },
        },
      });
    },

    updateCharts() {
      // Trend chart: Add latest fraud rate
      if (this.fraudTrendChart) {
        const now = new Date().toLocaleTimeString();
        this.fraudTrendChart.data.labels.push(now);
        const fraudRate = parseFloat(State.metrics.fraud_rate) || 0;
        this.fraudTrendChart.data.datasets[0].data.push(fraudRate);

        // Keep only last 30 data points
        if (this.fraudTrendChart.data.labels.length > 30) {
          this.fraudTrendChart.data.labels.shift();
          this.fraudTrendChart.data.datasets[0].data.shift();
        }
        this.fraudTrendChart.update('none');
      }

      // Category chart: Update status counts
      if (this.fraudCategoryChart && State.transactions.length > 0) {
        const counts = { Approved: 0, Flagged: 0, Declined: 0 };
        State.transactions.forEach(t => {
          counts[t.status] = (counts[t.status] || 0) + 1;
        });
        this.fraudCategoryChart.data.datasets[0].data = [
          counts.Approved,
          counts.Flagged,
          counts.Declined,
        ];
        this.fraudCategoryChart.update('none');
      }
    },
  };

  // ============================================================================
  // LIVE STREAM (SSE)
  // ============================================================================

  const LiveStream = {
    eventSource: null,

    connect() {
      if (this.eventSource) return; // Already connected

      try {
        this.eventSource = new EventSource(CONFIG.STREAM_ENDPOINT);

        this.eventSource.addEventListener('transactions', e => {
          try {
            const payload = JSON.parse(e.data);
            const results = payload.results || [];
            
            if (results.length > 0) {
              State.transactions = results.map(r => {
                const obj = {
                  id: r.transaction_id || r.id || '—',
                  time: r.prediction_timestamp || r.timestamp || '—',
                  merchant: r.user_id || r.full_name || '—',
                  amount: r.amount || 0,
                  currency: r.currency || 'NGN',
                  risk_score: Math.min(100, Math.round((r.fraud_probability || 0) * 100)),
                  status: (r.fraud_prediction === 1 || r.fraud_label === 'FRAUD') ? 
                    ((r.fraud_probability || 0) >= 0.8 ? 'Declined' : 'Flagged') : 'Approved',
                };
                return obj;
              });

              TransactionsTable.renderTable(State.transactions);
              Charts.updateCharts();
            }
          } catch (e) {
            console.error('SSE parse error:', e);
          }
        });

        this.eventSource.onerror = () => {
          console.warn('SSE connection error, will reconnect');
          State.isStreamConnected = false;
          this.disconnect();
          setTimeout(() => this.connect(), 5000);
        };

        State.isStreamConnected = true;
        AlertSystem.add('success', 'Live Stream Connected', 'Real-time updates enabled');
      } catch (e) {
        console.error('SSE connection failed:', e);
        State.isStreamConnected = false;
      }
    },

    disconnect() {
      if (this.eventSource) {
        this.eventSource.close();
        this.eventSource = null;
        State.isStreamConnected = false;
      }
    },
  };

  // ============================================================================
  // INITIALIZATION & POLLING
  // ============================================================================

  function initialize() {
    console.log('🚀 FraudGuard Live Dashboard Initializing...');

    // Initialize charts
    Charts.initialize();

    // Connect to live stream
    LiveStream.connect();

    // Initial metrics load
    MetricsDashboard.refresh();

    // Set up polling (fallback + additional refresh)
    setInterval(() => {
      MetricsDashboard.refresh();
      Charts.updateCharts();
    }, CONFIG.REFRESH_INTERVAL);

    // Update last refresh time
    setInterval(() => {
      const elem = el('last-update-time');
      if (elem && State.lastUpdate) {
        elem.textContent = State.lastUpdate.toLocaleTimeString();
      }
    }, 1000);

    // Button handlers
    const btnRefresh = el('btn-refresh');
    if (btnRefresh) {
      btnRefresh.addEventListener('click', () => {
        MetricsDashboard.refresh();
        AlertSystem.add('info', 'Refreshed', 'Metrics updated manually');
      });
    }

    AlertSystem.add('success', '✨ Dashboard Ready', 'Real-time monitoring active');
  }

  // Auto-initialize when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initialize);
  } else {
    initialize();
  }

  // Expose for testing
  window.FraudGuardLive = { State, MetricsDashboard, AlertSystem, TransactionsTable, Charts, LiveStream };
})();
