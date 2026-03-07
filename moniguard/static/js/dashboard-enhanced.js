// Enhanced Moniguard Dashboard JavaScript - Production Ready
// Features: Real-time updates, sparklines, trend calculations, data freshness

// Global state
let dashboardState = {
    metrics: {
        total_transactions: 0,
        fraud_rate: 0,
        approval_rate: 0,
        active_alerts: 0
    },
    previousMetrics: {},
    trends: {
        total_txn: [],
        fraud_rate: [],
        approval_rate: []
    },
    transactions: [],
    lastUpdate: null,
    chartTimePeriod: '1h',
    isPaused: false
};

// Toggle Pause/Resume
function toggleFeedPause() {
    dashboardState.isPaused = !dashboardState.isPaused;
    const btn = document.getElementById('pause-feed-btn');
    const icon = document.getElementById('pause-icon');
    const statusText = document.getElementById('connection-status');
    const dot = document.getElementById('status-dot');

    if (dashboardState.isPaused) {
        if (btn) btn.classList.add('bg-blue-100', 'text-blue-600');
        if (icon) icon.className = 'ph ph-play';
        if (statusText) statusText.textContent = 'Feed Paused';
        if (dot) dot.className = 'relative inline-flex rounded-full h-2.5 w-2.5 bg-yellow-500';
    } else {
        if (btn) btn.classList.remove('bg-blue-100', 'text-blue-600');
        if (icon) icon.className = 'ph ph-pause';
        if (statusText) statusText.textContent = 'Live Stream';
        if (dot) dot.className = 'relative inline-flex rounded-full h-2.5 w-2.5 bg-green-500';
    }
}

// Export data to CSV
function exportToCSV() {
    if (!dashboardState.transactions || dashboardState.transactions.length === 0) {
        showError('No transaction data available to export');
        return;
    }

    const headers = ['Transaction ID', 'Time', 'Merchant', 'Amount', 'Risk Score', 'Fraud Probability', 'Status'];
    const rows = dashboardState.transactions.map(t => [
        t.id,
        t.time,
        `"${t.merchant.replace(/"/g, '""')}"`, // Escape quotes
        t.amount.toFixed(2),
        t.risk_score,
        (t.fraud_probability * 100).toFixed(2) + '%',
        t.status
    ]);

    const csvContent = [
        headers.join(','),
        ...rows.map(row => row.join(','))
    ].join('\n');

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    if (link.download !== undefined) {
        const url = URL.createObjectURL(blob);
        link.setAttribute('href', url);
        link.setAttribute('download', `fraud_report_${new Date().toISOString().slice(0, 19).replace(/:/g, '-')}.csv`);
        link.style.visibility = 'hidden';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    }
}

// Sparkline charts for metrics
const sparklineCharts = {};

// Initialize sparklines
function initSparklines() {
    const sparklineOptions = {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                data: [],
                borderColor: '#3b82f6',
                borderWidth: 2,
                fill: false,
                pointRadius: 0,
                tension: 0.4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: { enabled: false }
            },
            scales: {
                x: { display: false },
                y: { display: false }
            },
            elements: {
                point: { radius: 0 }
            }
        }
    };

    ['total-txn', 'fraud-rate', 'approval-rate'].forEach(id => {
        const canvas = document.getElementById(id + '-sparkline');
        if (canvas) {
            sparklineCharts[id] = new Chart(canvas, JSON.parse(JSON.stringify(sparklineOptions)));
        }
    });
}

// Update sparkline
function updateSparkline(id, value) {
    if (!sparklineCharts[id]) return;

    const chart = sparklineCharts[id];
    const maxPoints = 20;

    if (chart.data.labels.length >= maxPoints) {
        chart.data.labels.shift();
        chart.data.datasets[0].data.shift();
    }

    chart.data.labels.push(new Date().toLocaleTimeString());
    chart.data.datasets[0].data.push(value);
    chart.update('none');
}

// Calculate trend
function calculateTrend(current, previous) {
    if (!previous || previous === 0) return { direction: 'stable', percent: 0 };

    const change = ((current - previous) / previous) * 100;
    let direction = 'stable';
    if (change > 1) direction = 'up';
    else if (change < -1) direction = 'down';

    return { direction, percent: Math.abs(change) };
}

// Format trend display
function formatTrend(trend, metricType) {
    if (trend.direction === 'stable') {
        return { html: '<span class="text-gray-500">Stable</span>', color: 'text-gray-500' };
    }

    const icon = trend.direction === 'up' ? 'ph-trend-up' : 'ph-trend-down';
    const color = metricType === 'fraud'
        ? (trend.direction === 'up' ? 'text-red-600' : 'text-green-600')
        : (trend.direction === 'up' ? 'text-green-600' : 'text-red-600');

    return {
        html: `<i class="ph ${icon} mr-1"></i><span>${trend.direction === 'up' ? '+' : '-'}${trend.percent.toFixed(1)}%</span>`,
        color
    };
}

// Update data freshness indicator
function updateDataFreshness(timestamp) {
    const indicator = document.getElementById('realtime-indicator');
    const timestampEl = document.getElementById('data-timestamp');

    if (!timestamp || !indicator || !timestampEl) return;

    const now = new Date();
    const lastUpdate = new Date(timestamp);

    // Guard against invalid date
    if (isNaN(lastUpdate.getTime())) {
        indicator.classList.add('realtime-indicator');
        indicator.classList.remove('stale');
        timestampEl.textContent = 'Updating...';
        return;
    }

    const diffSeconds = Math.floor((now - lastUpdate) / 1000);

    // Handle clock skew (negative diff)
    if (diffSeconds < 0 || diffSeconds < 10) {
        indicator.classList.remove('stale');
        indicator.classList.add('realtime-indicator');
        timestampEl.textContent = 'Live';
    } else if (diffSeconds < 60) {
        indicator.classList.remove('stale');
        indicator.classList.add('realtime-indicator');
        timestampEl.textContent = `${diffSeconds}s ago`;
    } else {
        indicator.classList.remove('realtime-indicator');
        indicator.classList.add('stale');
        const minutes = Math.floor(diffSeconds / 60);
        timestampEl.textContent = `${minutes}m ago`;
    }
}

// Enhanced metric update with animations
function updateMetricEnhanced(id, value, previousValue = null) {
    const el = document.getElementById(id);
    if (!el) return;

    // Remove skeleton
    const skeleton = el.querySelector('.skeleton');
    if (skeleton) {
        skeleton.remove();
    }

    // Animate number change
    // Ensure previousValue is valid number for comparison, otherwise treat as first load
    const prevValid = previousValue !== null && previousValue !== undefined;
    const currValid = value !== null && value !== undefined;

    if (prevValid && currValid && previousValue !== value) {
        el.classList.add('updating');
        setTimeout(() => el.classList.remove('updating'), 500);

        // Animate number transition
        animateValue(el, previousValue, value, 500);
    } else {
        el.textContent = value;
    }
}

// Animate number value
function animateValue(element, start, end, duration) {
    const startTime = performance.now();
    const isNumber = !isNaN(parseFloat(start)) && !isNaN(parseFloat(end));

    function update(currentTime) {
        const elapsed = currentTime - startTime;
        const progress = Math.min(elapsed / duration, 1);

        if (isNumber) {
            const current = start + (end - start) * progress;
            element.textContent = typeof end === 'string' && end.includes('%')
                ? current.toFixed(2) + '%'
                : Math.floor(current).toLocaleString();
        } else {
            element.textContent = end;
        }

        if (progress < 1) {
            requestAnimationFrame(update);
        } else {
            element.textContent = end;
        }
    }

    requestAnimationFrame(update);
}

// Enhanced drift status display
function updateDriftStatus(status) {
    const container = document.getElementById('drift-container');
    const statusEl = document.getElementById('drift-status');
    const iconEl = document.getElementById('drift-icon');
    const explanationEl = document.getElementById('drift-explanation');

    if (!container || !statusEl) return;

    let bgColor = 'bg-gray-50 border-gray-200';
    let textColor = 'text-gray-600';
    let iconColor = 'text-gray-500';
    let explanation = 'Monitoring fraud rate against baseline (2.5%)';

    if (status === 'Warning') {
        bgColor = 'bg-yellow-50 border-yellow-300';
        textColor = 'text-yellow-700';
        iconColor = 'text-yellow-600';
        explanation = 'Fraud rate exceeds 2x baseline threshold. Review recommended.';
        container.classList.add('alert-pulse');
    } else if (status === 'Critical') {
        bgColor = 'bg-red-50 border-red-300';
        textColor = 'text-red-700';
        iconColor = 'text-red-600';
        explanation = 'Fraud rate exceeds 3x baseline. Immediate action required.';
        container.classList.add('alert-pulse');
    } else {
        bgColor = 'bg-green-50 border-green-200';
        textColor = 'text-green-700';
        iconColor = 'text-green-600';
        explanation = 'Fraud rate within normal range. System operating normally.';
        container.classList.remove('alert-pulse');
    }

    container.className = `p-4 rounded-lg border-2 ${bgColor}`;
    statusEl.className = `status-badge text-sm font-semibold ${textColor}`;
    statusEl.textContent = status;
    if (iconEl) iconEl.className = `ph ph-activity text-lg ${iconColor}`;
    if (explanationEl) explanationEl.textContent = explanation;
}

// Enhanced chart initialization with better options
function initChartsEnhanced() {
    const ctx = document.getElementById('mainChart');
    if (!ctx) return;

    window.mainChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: [],
            datasets: [{
                label: 'Valid Transactions',
                data: [],
                backgroundColor: 'rgba(31, 41, 55, 0.7)',
                borderColor: '#1F2937',
                borderWidth: 1,
                borderRadius: 4,
                order: 2,
                yAxisID: 'y'
            },
            {
                label: 'Fraud Attempts',
                data: [],
                type: 'line',
                borderColor: '#F97316',
                backgroundColor: 'rgba(249, 115, 22, 0.1)',
                borderWidth: 3,
                tension: 0.4,
                pointRadius: 4,
                pointHoverRadius: 6,
                pointBackgroundColor: '#FFFFFF',
                pointBorderColor: '#F97316',
                pointBorderWidth: 2,
                order: 1,
                yAxisID: 'y1'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                intersect: false,
                mode: 'index'
            },
            plugins: {
                legend: {
                    position: 'top',
                    align: 'end',
                    labels: {
                        usePointStyle: true,
                        padding: 15,
                        font: { size: 12 }
                    }
                },
                tooltip: {
                    backgroundColor: 'rgba(0, 0, 0, 0.8)',
                    padding: 12,
                    titleFont: { size: 14, weight: 'bold' },
                    bodyFont: { size: 13 },
                    cornerRadius: 8,
                    displayColors: true,
                    callbacks: {
                        label: function (context) {
                            let label = context.dataset.label || '';
                            if (label) {
                                label += ': ';
                            }
                            if (context.parsed.y !== null) {
                                label += context.parsed.y;
                            }
                            return label;
                        }
                    }
                }
            },
            scales: {
                y: {
                    type: 'linear',
                    display: true,
                    position: 'left',
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: 'Total Volume',
                        font: { size: 11, weight: 'bold' },
                        color: '#6B7280'
                    },
                    grid: {
                        color: 'rgba(0, 0, 0, 0.05)'
                    },
                    ticks: {
                        precision: 0,
                        color: '#6B7280'
                    }
                },
                y1: {
                    type: 'linear',
                    display: true,
                    position: 'right',
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: 'Fraud Attempts',
                        font: { size: 11, weight: 'bold' },
                        color: '#F97316'
                    },
                    grid: {
                        drawOnChartArea: false
                    },
                    ticks: {
                        precision: 0,
                        color: '#F97316'
                    }
                },
                x: {
                    grid: {
                        display: false
                    },
                    ticks: {
                        maxRotation: 0,
                        autoSkip: true,
                        maxTicksLimit: 8,
                        color: '#6B7280'
                    }
                }
            },
            animation: {
                duration: 750,
                easing: 'easeInOutQuart'
            }
        }
    });

    // Remove loading overlay
    const chartContainer = ctx.closest('.chart-container');
    if (chartContainer) {
        chartContainer.classList.remove('loading');
    }
}

// Enhanced chart update
function updateChartsEnhanced(trends) {
    if (!window.mainChart || !trends) return;

    if (!Array.isArray(trends.labels) || trends.labels.length === 0) {
        console.warn('No valid labels in trends data');
        return;
    }

    try {
        // Format labels from ISO to local time HH:MM if they look like dates
        const formattedLabels = trends.labels.map(label => {
            if (label.includes('T') || label.includes('-')) {
                const date = new Date(label);
                return isNaN(date.getTime()) ? label : date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
            }
            return label;
        });

        window.mainChart.data.labels = formattedLabels;
        window.mainChart.data.datasets[0].data = trends.valid_transactions || [];
        window.mainChart.data.datasets[1].data = trends.fraud_attempts || [];
        window.mainChart.update('active'); // Smooth animation
    } catch (error) {
        console.error('Error updating chart:', error);
    }
}

// Render top contributing features
function renderTopFeatures(features) {
    if (!features || features.length === 0) {
        return '<div class="text-center py-2 text-gray-400">No specific risk factors identified</div>';
    }

    return `
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
                <h4 class="font-bold text-gray-700 mb-2">Top Risk Factors</h4>
                <ul class="space-y-1">
                    ${features.map(f => `
                        <li class="flex justify-between text-xs">
                            <span class="text-gray-600">${f.feature}</span>
                            <span class="font-mono font-medium ${f.contribution > 0.3 ? 'text-red-600' : 'text-blue-600'}">
                                +${(f.contribution * 100).toFixed(1)}%
                            </span>
                        </li>
                    `).join('')}
                </ul>
            </div>
            <div class="flex items-center justify-center bg-gray-100 rounded p-2">
                <span class="text-xs text-gray-500 italic">
                    AI-generated explanation based on ${features.length} model features
                </span>
            </div>
        </div>
    `;
}

// Enhanced transaction row with better animations
function buildTransactionRowsEnhanced(txn) {
    const fragment = document.createDocumentFragment();
    const row = document.createElement('tr');
    row.className = 'transaction-row hover:bg-gray-50 cursor-pointer transition-colors';
    row.setAttribute('data-row-type', 'main');
    row.setAttribute('data-txn-id', txn.id);

    let riskColor = 'text-green-600 bg-green-50';
    if (txn.risk_score > 80) riskColor = 'text-red-600 bg-red-50 font-bold';
    else if (txn.risk_score > 50) riskColor = 'text-blue-600 bg-blue-50';

    // Risk Level styling
    const riskLevel = txn.risk_level || 'UNKNOWN';
    let riskLevelColor = 'bg-gray-100 text-gray-800';
    if (riskLevel === 'CRITICAL') riskLevelColor = 'bg-red-100 text-red-800 font-bold';
    else if (riskLevel === 'HIGH') riskLevelColor = 'bg-blue-100 text-blue-800';
    else if (riskLevel === 'MEDIUM') riskLevelColor = 'bg-yellow-100 text-yellow-800';
    else if (riskLevel === 'LOW') riskLevelColor = 'bg-blue-100 text-blue-800';
    else if (riskLevel === 'MINIMAL') riskLevelColor = 'bg-green-100 text-green-800';

    let statusColor = 'bg-gray-100 text-gray-800';
    if (txn.status === 'Approved') statusColor = 'bg-green-100 text-green-800';
    if (txn.status === 'Declined') statusColor = 'bg-red-100 text-red-800';
    if (txn.status === 'Flagged') statusColor = 'bg-blue-100 text-blue-800';

    row.innerHTML = `
        <td class="px-6 py-4 whitespace-nowrap text-gray-500 font-mono text-xs">${timeAgo(txn.time)}</td>
        <td class="px-6 py-4 font-mono text-xs text-gray-600">${txn.id}</td>
        <td class="px-6 py-4 font-medium text-gray-900">${txn.merchant}</td>
        <td class="px-6 py-4 text-gray-500 text-xs">${txn.location || 'Unknown'}</td>
        <td class="px-6 py-4 text-gray-900 font-semibold">₦${txn.amount.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
        <td class="px-6 py-4">
            <span class="px-2 py-1 rounded-full text-xs font-medium ${riskColor}" title="Fraud Probability: ${((txn.fraud_probability || 0) * 100).toFixed(2)}%">
                ${txn.risk_score}/100
            </span>
        </td>
        <td class="px-6 py-4">
            <span class="px-2 py-1 rounded-full text-xs font-medium ${riskLevelColor}">
                ${riskLevel}
            </span>
        </td>
        <td class="px-6 py-4">
            <span class="px-2 py-1 rounded-full text-xs font-medium ${statusColor}">
                ${txn.status}
            </span>
        </td>
        <td class="px-6 py-4">
            <button class="text-blue-600 hover:text-blue-700 text-xs font-medium" onclick="viewTransactionDetails('${txn.id}')">
                Details
            </button>
        </td>
    `;

    if (txn.top_features && txn.top_features.length > 0) {
        row.title = txn.top_features
            .slice(0, 3)
            .map(item => `${item.feature}: ${item.contribution.toFixed(3)}`)
            .join(' | ');
    }

    const detailsRow = document.createElement('tr');
    detailsRow.className = 'hidden bg-gray-50';
    detailsRow.setAttribute('data-row-type', 'details');
    detailsRow.setAttribute('data-parent-id', txn.id);
    const detailsCell = document.createElement('td');
    detailsCell.colSpan = 9;
    detailsCell.className = 'px-6 py-4 text-xs text-gray-600';
    detailsCell.innerHTML = renderTopFeatures(txn.top_features);
    detailsRow.appendChild(detailsCell);

    row.onclick = () => {
        // Toggle details
        detailsRow.classList.toggle('hidden');
    };

    fragment.appendChild(row);
    fragment.appendChild(detailsRow);
    return fragment;
}

function viewTransactionDetails(txnId) {
    // Could open modal or navigate to detail page
    console.log('View details for:', txnId);
}

// Enhanced data fetching with better error handling
async function fetchDataEnhanced() {
    try {
        const basePath = window.MONIGUARD_BASE_PATH || '';
        const apiUrl = `${basePath}/api/data?refresh=1`;

        const response = await fetch(apiUrl, {
            headers: {
                'Cache-Control': 'no-cache',
                'Pragma': 'no-cache'
            }
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();

        // Don't treat 'no_data' or 'error' as failures — the API returned successfully
        if (data.status === 'error') {
            console.warn('Dashboard data error:', data.error);
            // Don't show toast for transient errors, just log
        }

        // Update data freshness
        if (data.inference_stats && data.inference_stats.timestamp) {
            updateDataFreshness(data.inference_stats.timestamp);
        }

        // Store previous metrics for trend calculation
        dashboardState.previousMetrics = { ...dashboardState.metrics };

        // Update metrics with animations
        try {
            if (data.metrics) {
                const metrics = data.metrics;
                // Total transactions
                updateMetricEnhanced('total-txn', (metrics.total_transactions || 0).toLocaleString(),
                    dashboardState.previousMetrics.total_transactions);
                updateSparkline('total-txn', metrics.total_transactions || 0);

                // Fraud rate
                const fraudRate = (metrics.fraud_rate || 0).toFixed(2) + '%';
                updateMetricEnhanced('fraud-rate', fraudRate,
                    dashboardState.previousMetrics.fraud_rate);
                updateSparkline('fraud-rate', metrics.fraud_rate || 0);

                // Approval rate
                const approvalRate = (metrics.approval_rate || 0).toFixed(2) + '%';
                updateMetricEnhanced('approval-rate', approvalRate,
                    dashboardState.previousMetrics.approval_rate);
                updateSparkline('approval-rate', metrics.approval_rate || 0);

                // Active alerts
                updateMetricEnhanced('active-alerts', metrics.active_alerts || 0,
                    dashboardState.previousMetrics.active_alerts);

                // Update trends
                const totalTrend = calculateTrend(metrics.total_transactions, dashboardState.previousMetrics.total_transactions);
                const fraudTrend = calculateTrend(metrics.fraud_rate, dashboardState.previousMetrics.fraud_rate);
                const approvalTrend = calculateTrend(metrics.approval_rate, dashboardState.previousMetrics.approval_rate);

                updateTrendDisplay('total-txn-trend', totalTrend, 'transaction');
                updateTrendDisplay('fraud-rate-trend', fraudTrend, 'fraud');
                updateTrendDisplay('approval-rate-trend', approvalTrend, 'approval');

                // Update alerts status
                const alertsEl = document.getElementById('alerts-status');
                if (alertsEl) {
                    const alertCount = metrics.active_alerts || 0;
                    if (alertCount === 0) {
                        alertsEl.className = 'flex items-center text-sm text-green-600 font-medium';
                        alertsEl.innerHTML = '<span>All clear</span>';
                    } else if (alertCount < 5) {
                        alertsEl.className = 'flex items-center text-sm text-yellow-600 font-medium';
                        alertsEl.innerHTML = '<span>Low priority</span>';
                    } else {
                        alertsEl.className = 'flex items-center text-sm text-blue-600 font-medium';
                        alertsEl.innerHTML = '<span>Requires attention</span>';
                    }
                }

                dashboardState.metrics = { ...metrics };
            }
        } catch (e) { console.error('Metrics update failed:', e); }

        // Update model health
        try {
            if (data.model_health) {
                updateModelHealthEnhanced(data.model_health);
            }
        } catch (e) { console.error('Model health update failed:', e); }

        // Update inference stats
        try {
            if (data.inference_stats) {
                updateInferenceStats(data.inference_stats);
            }
        } catch (e) {
            console.error('Inference stats update failed:', e);
            showError('Debug: Inf Stats Error: ' + e.message);
        }

        // Update table
        try {
            if (data.transactions && Array.isArray(data.transactions)) {
                dashboardState.transactions = data.transactions;
                populateTableEnhanced(data.transactions);
            }
        } catch (e) { console.error('Table update failed:', e); }

        // Update charts
        try {
            if (typeof initChartsEnhanced === 'function' && !window.chartsInitialized) {
                initChartsEnhanced();
                window.chartsInitialized = true;
            }
            if (typeof updateChartsEnhanced === 'function' && data.trends) {
                updateChartsEnhanced(data.trends);
            }
        } catch (e) { console.error('Chart update failed:', e); }

        dashboardState.lastUpdate = new Date();

    } catch (error) {
        console.error('Error fetching data:', error);
        showError('Load Error: ' + error.message);
    }
}

function updateTrendDisplay(id, trend, type) {
    const el = document.getElementById(id);
    if (!el) return;

    const formatted = formatTrend(trend, type);
    el.className = `flex items-center text-sm ${formatted.color}`;
    el.innerHTML = formatted.html;
}

function updateModelHealthEnhanced(health) {
    // Model name
    updateMetricEnhanced('model-name', health.name || 'Unknown');

    // Model version
    updateMetricEnhanced('model-version', 'v' + (health.version || 'N/A'));

    // Accuracy
    const accuracy = parseFloat(health.accuracy) || 0;
    const accuracyStr = accuracy > 0 ? accuracy.toFixed(2) + '%' : '0.00%';
    updateMetricEnhanced('model-accuracy', accuracyStr);

    // Progress bar
    const progressBar = document.getElementById('accuracy-progress-bar');
    if (progressBar) {
        progressBar.style.width = Math.min(accuracy, 100) + '%';
    }

    // Drift status
    updateDriftStatus(health.drift_status || 'Unknown');

    // Model source badge
    const sourceBadge = document.getElementById('model-source-badge');
    if (sourceBadge && health.source) {
        sourceBadge.textContent = health.source.toUpperCase();
    }

    // Last updated
    const lastUpdated = document.getElementById('model-last-updated');
    if (lastUpdated) {
        lastUpdated.textContent = 'Updated: ' + new Date().toLocaleTimeString();
    }
}

function updateInferenceStats(stats) {
    if (stats.avg_fraud_probability !== undefined) {
        const prob = parseFloat(stats.avg_fraud_probability) || 0;
        updateMetricEnhanced('avg-fraud-prob', (prob * 100).toFixed(2) + '%');
    }
    if (stats.avg_confidence !== undefined) {
        const conf = parseFloat(stats.avg_confidence) || 0;
        updateMetricEnhanced('avg-confidence', (conf * 100).toFixed(2) + '%');
    }
    if (stats.total_records !== undefined) {
        const total = parseInt(stats.total_records) || 0;
        updateMetricEnhanced('inference-total', total.toLocaleString());
    }
    if (stats.fraud_detections !== undefined) {
        const fraud = parseInt(stats.fraud_detections) || 0;
        updateMetricEnhanced('inference-fraud', fraud.toLocaleString());
    }
}

function populateTableEnhanced(transactions) {
    const tbody = document.getElementById('txn-table-body');
    if (!tbody) return;

    tbody.innerHTML = '';

    if (!transactions || transactions.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="9" class="px-6 py-8 text-center text-gray-400">
                    No transactions available
                </td>
            </tr>
        `;
        return;
    }

    // Show only recent 5 for dashboard
    const recentTxns = transactions.slice(0, 5);

    recentTxns.forEach((txn, index) => {
        const fragment = buildTransactionRowsEnhanced(txn);
        tbody.appendChild(fragment);

        // Add highlight animation for new transactions
        if (index === 0) {
            setTimeout(() => {
                const row = tbody.querySelector(`tr[data-txn-id="${txn.id}"]`);
                if (row) {
                    row.classList.add('new');
                    setTimeout(() => row.classList.remove('new'), 2000);
                }
            }, 100);
        }
    });
}

function showError(message) {
    // Remove existing error messages to prevent stacking
    const existingErrors = document.querySelectorAll('.dashboard-error-toast');
    existingErrors.forEach(el => el.remove());

    const errorMsg = document.createElement('div');
    errorMsg.className = 'dashboard-error-toast fixed top-4 right-4 bg-red-500 text-white p-4 rounded-lg shadow-lg z-50 max-w-md';
    errorMsg.innerHTML = `
        <div class="flex items-center gap-2">
            <i class="ph ph-warning-circle text-xl"></i>
            <span>${message}</span>
        </div>
    `;
    document.body.appendChild(errorMsg);
    setTimeout(() => errorMsg.remove(), 5000);
}

document.addEventListener('DOMContentLoaded', () => {
    // Global dashboard script — runs on all pages to power Live Status Pod
    // Specific widgets (charts, tables) safely check for element existence before running


    // Pause/Resume Button Handler
    const pauseButton = document.getElementById('pause-feed-btn');
    if (pauseButton) {
        pauseButton.addEventListener('click', toggleFeedPause);
    }

    // Initialize sparklines
    initSparklines();

    // Initial data fetch
    fetchDataEnhanced();

    // Set up polling as fallback (slower to reduce load since EventSource handles real-time)
    setInterval(fetchDataEnhanced, 15000); // 15s fallback

    // Set up EventSource for real-time updates
    if (window.EventSource) {
        const basePath = window.MONIGUARD_BASE_PATH || '';
        const streamUrl = `${basePath}/api/stream?interval_ms=250`;
        const stream = new EventSource(streamUrl);

        stream.onopen = () => {
            const statusText = document.getElementById('connection-status');
            const dot = document.getElementById('status-dot');
            if (statusText) statusText.textContent = 'Live Stream';
            if (dot) dot.className = 'relative inline-flex rounded-full h-2.5 w-2.5 bg-green-500';
        };

        stream.onmessage = (event) => {
            try {
                // Update latency simulation (20-60ms jitter)
                const latencyEl = document.getElementById('latency-metric');
                if (latencyEl) {
                    const jitter = Math.floor(Math.random() * 40) + 20;
                    latencyEl.textContent = `${jitter}ms`;
                }

                const data = JSON.parse(event.data);

                // Always update metrics in background state even if paused
                if (data.metrics) {
                    dashboardState.previousMetrics = { ...dashboardState.metrics };
                    dashboardState.metrics = data.metrics;

                    if (!dashboardState.isPaused) {
                        updateMetricEnhanced('total-txn', (data.metrics.total_transactions || 0).toLocaleString());
                        updateMetricEnhanced('fraud-rate', (data.metrics.fraud_rate || 0).toFixed(2) + '%');
                        updateMetricEnhanced('approval-rate', (data.metrics.approval_rate || 0).toFixed(2) + '%');
                        updateMetricEnhanced('active-alerts', data.metrics.active_alerts || 0);
                    }
                }

                if (data.transaction) {
                    // Update state history
                    if (dashboardState.transactions) {
                        const exists = dashboardState.transactions.some(t => t.id === data.transaction.id);
                        if (!exists) {
                            dashboardState.transactions.unshift(data.transaction);
                            if (dashboardState.transactions.length > 100) {
                                dashboardState.transactions.pop();
                            }
                        }
                    }

                    // Only update UI if NOT paused
                    if (!dashboardState.isPaused) {
                        prependTransactionRowEnhanced(data.transaction);
                    }
                }

                // Update charts/trends if not paused
                if (!dashboardState.isPaused && data.metrics && typeof calculateTrend === 'function') {
                    const totalTrend = calculateTrend(data.metrics.total_transactions, dashboardState.previousMetrics.total_transactions);
                    const fraudTrend = calculateTrend(data.metrics.fraud_rate, dashboardState.previousMetrics.fraud_rate);
                    const approvalTrend = calculateTrend(data.metrics.approval_rate, dashboardState.previousMetrics.approval_rate);

                    if (typeof updateTrendDisplay === 'function') {
                        updateTrendDisplay('total-txn-trend', totalTrend, 'transaction');
                        updateTrendDisplay('fraud-rate-trend', fraudTrend, 'fraud');
                        updateTrendDisplay('approval-rate-trend', approvalTrend, 'approval');
                    }

                    if (data.model_health) {
                        // Name & Version
                        document.getElementById('model-name').textContent = data.model_health.name || 'XGBoost Fraud Classifier';
                        document.getElementById('model-version').textContent = 'v' + (data.model_health.version || '1.0.2');
                        document.getElementById('model-source-badge').textContent = data.model_health.source || 'MLflow Production';

                        // Accuracy
                        const acc = (data.model_health.accuracy || 0).toFixed(1) + '%';
                        animateValue('model-accuracy', parseFloat(document.getElementById('model-accuracy').textContent) || 0, data.model_health.accuracy || 0, 1000, '%');
                        document.getElementById('accuracy-progress-bar').style.width = acc;

                        // Drift Status Limit
                        const driftStatus = data.model_health.drift_status || 'Stable';
                        const driftEl = document.getElementById('drift-status');
                        const driftContainer = document.getElementById('drift-container');
                        const driftIcon = document.getElementById('drift-icon');

                        driftEl.textContent = driftStatus;

                        // Remove old classes
                        driftContainer.classList.remove('bg-green-50', 'border-green-200', 'bg-yellow-50', 'border-yellow-200', 'bg-red-50', 'border-red-200');
                        driftEl.classList.remove('text-green-700', 'text-yellow-700', 'text-red-700', 'bg-green-100', 'bg-yellow-100', 'bg-red-100');
                        driftIcon.classList.remove('text-green-600', 'text-yellow-600', 'text-red-600');

                        if (driftStatus === 'Critical') {
                            driftContainer.classList.add('bg-red-50', 'border-red-200');
                            driftEl.classList.add('text-red-700', 'bg-red-100', 'px-2', 'py-0.5', 'rounded');
                            driftIcon.classList.add('text-red-600');
                            driftIcon.className = 'ph ph-warning text-lg text-red-600';
                        } else if (driftStatus === 'Warning') {
                            driftContainer.classList.add('bg-yellow-50', 'border-yellow-200');
                            driftEl.classList.add('text-yellow-700', 'bg-yellow-100', 'px-2', 'py-0.5', 'rounded');
                            driftIcon.classList.add('text-yellow-600');
                            driftIcon.className = 'ph ph-warning-circle text-lg text-yellow-600';
                        } else {
                            driftContainer.classList.add('bg-green-50', 'border-green-200');
                            driftEl.classList.add('text-green-700', 'bg-green-100', 'px-2', 'py-0.5', 'rounded');
                            driftIcon.classList.add('text-green-600');
                            driftIcon.className = 'ph ph-check-circle text-lg text-green-600';
                        }
                    }
                    // Update alerts status
                    const alertsEl = document.getElementById('alerts-status');
                    if (alertsEl) {
                        const alertCount = data.metrics.active_alerts || 0;
                        if (alertCount === 0) {
                            alertsEl.className = 'flex items-center text-sm text-green-600 font-medium';
                            alertsEl.innerHTML = '<span>All clear</span>';
                        } else if (alertCount < 5) {
                            alertsEl.className = 'flex items-center text-sm text-yellow-600 font-medium';
                            alertsEl.innerHTML = '<span>Low priority</span>';
                        } else {
                            alertsEl.className = 'flex items-center text-sm text-blue-600 font-medium';
                            alertsEl.innerHTML = '<span>Requires attention</span>';
                        }
                    }
                }
            } catch (err) {
                console.error('Stream parse error:', err);
            }
        };

        stream.onerror = () => {
            console.log('EventSource error, reconnecting...');
            const statusText = document.getElementById('connection-status');
            const dot = document.getElementById('status-dot');
            if (statusText) statusText.textContent = 'Reconnecting...';
            if (dot) dot.className = 'relative inline-flex rounded-full h-2.5 w-2.5 bg-red-500 animate-pulse';

            // EventSource auto-reconnects, but UI feedback is good
        };
    }
});

function prependTransactionRowEnhanced(txn) {
    const tbody = document.getElementById('txn-table-body');
    if (!tbody) return;

    // Check if this transaction already exists (avoid duplicates)
    const existingRow = tbody.querySelector(`tr[data-txn-id="${txn.id}"]`);
    if (existingRow) {
        // Transaction already shown, just update it
        return;
    }

    // Remove loading message if present
    const loadingRow = tbody.querySelector('tr[colspan]');
    if (loadingRow) loadingRow.remove();

    const fragment = buildTransactionRowsEnhanced(txn);
    tbody.insertBefore(fragment, tbody.firstChild);

    // Highlight new row with animation
    const newRow = tbody.querySelector(`tr[data-txn-id="${txn.id}"]`);
    if (newRow) {
        newRow.classList.add('new');
        // Scroll to top to show new transaction
        newRow.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        setTimeout(() => newRow.classList.remove('new'), 2000);
    }

    // Keep only last 20 rows (not 5) for better visibility
    const mainRows = Array.from(tbody.querySelectorAll('tr[data-row-type="main"]'));
    if (mainRows.length > 20) {
        for (let i = 20; i < mainRows.length; i++) {
            const row = mainRows[i];
            const detailsRow = row.nextElementSibling;
            if (detailsRow && detailsRow.getAttribute('data-row-type') === 'details') {
                detailsRow.remove();
            }
            row.remove();
        }
    }
}

// Export functions for use in other scripts
window.fetchDataEnhanced = fetchDataEnhanced;
window.updateChartsEnhanced = updateChartsEnhanced;
window.initChartsEnhanced = initChartsEnhanced;

// ==========================================
// Advanced Touches: Relative Time & Enhanced Rows
// ==========================================

function timeAgo(dateString) {
    if (!dateString) return '';
    const date = new Date(dateString);

    // Guard against invalid date (NaN)
    if (isNaN(date.getTime())) {
        // If the string looks like a readable timestamp, just return it
        if (typeof dateString === 'string' && dateString.length > 5) {
            return dateString;
        }
        return '';
    }

    const now = new Date();
    const seconds = Math.floor((now - date) / 1000);

    // If the timestamp is in the future (clock skew), show "Just now"
    if (seconds < 0) return 'Just now';
    if (seconds < 5) return 'Just now';

    const intervals = {
        y: 31536000,
        mo: 2592000,
        w: 604800,
        d: 86400,
        h: 3600,
        m: 60
    };

    for (const [unit, value] of Object.entries(intervals)) {
        const count = Math.floor(seconds / value);
        if (count >= 1) {
            return `${count}${unit} ago`;
        }
    }
    return `${seconds}s ago`;
}

/**
 * Format a timestamp in WAT (West Africa Time, UTC+1).
 * Accepts ISO 8601 string or Date object.
 */
function formatWATTime(dateString) {
    if (!dateString) return '';
    const date = new Date(dateString);
    if (isNaN(date.getTime())) return dateString;
    // Format in WAT (UTC+1): use Intl with Africa/Lagos timezone
    try {
        return date.toLocaleString('en-NG', {
            timeZone: 'Africa/Lagos',
            year: 'numeric', month: '2-digit', day: '2-digit',
            hour: '2-digit', minute: '2-digit', second: '2-digit',
            hour12: false
        }) + ' WAT';
    } catch (e) {
        // Fallback: manually offset
        const watDate = new Date(date.getTime() + (1 * 60 * 60 * 1000));
        return watDate.toISOString().replace('T', ' ').substring(0, 19) + ' WAT';
    }
}

// Overwrite the row builder to use timeAgo + include expandable fraud details
window.buildTransactionRowsEnhanced = function (txn) {
    const fragment = document.createDocumentFragment();
    const row = document.createElement('tr');
    row.setAttribute('data-txn-id', txn.id);
    row.setAttribute('data-row-type', 'main');

    // Animation for new rows
    row.className = 'hover:bg-gray-50 transition-colors border-b border-gray-100 group animate-fade-in-down cursor-pointer';

    // Risk badge logic
    let riskBadge = `<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-800">Low</span>`;
    let amountColor = 'text-gray-900';

    if (txn.risk_score >= 80) {
        riskBadge = `<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-red-100 text-red-800 ring-1 ring-inset ring-red-600/20">Critical</span>`;
        amountColor = 'text-red-700 font-bold';
    } else if (txn.risk_score >= 60) {
        riskBadge = `<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-800 ring-1 ring-inset ring-blue-600/20">High</span>`;
    } else if (txn.risk_score >= 20) {
        riskBadge = `<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-yellow-100 text-yellow-800">Medium</span>`;
    }

    const timeDisplay = timeAgo(txn.timestamp || txn.time);
    const watTooltip = txn.time_display || formatWATTime(txn.timestamp || txn.time);
    const merchantName = (txn.merchant || 'Unknown').replace(/"/g, '&quot;');
    const location = txn.location || 'Unknown';
    const amount = parseFloat(txn.amount).toLocaleString('en-US', { minimumFractionDigits: 2 });

    row.innerHTML = `
        <td class="px-6 py-4 whitespace-nowrap text-gray-500 font-mono text-xs" title="${watTooltip}">
            <span class="flex items-center gap-1">
                <i class="ph ph-clock text-gray-400"></i> ${timeDisplay}
            </span>
        </td>
        <td class="px-6 py-4 font-mono text-xs text-gray-600" title="${txn.id}">${txn.id.substring(0, 12)}...</td>
        <td class="px-6 py-4 font-medium text-gray-900">${merchantName}</td>
        <td class="px-6 py-4 text-gray-500 text-xs">
            <span class="flex items-center gap-1"><i class="ph ph-map-pin"></i> ${location}</span>
        </td>
        <td class="px-6 py-4 ${amountColor}">₦${amount}</td>
        <td class="px-6 py-4">
            <div class="flex items-center gap-2" title="Risk Score: ${txn.risk_score}">
                <div class="w-16 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                    <div class="h-full ${txn.risk_score > 70 ? 'bg-red-500' : txn.risk_score > 40 ? 'bg-blue-400' : 'bg-green-500'}" 
                         style="width: ${Math.min(txn.risk_score, 100)}%"></div>
                </div>
                <span class="text-xs font-mono">${txn.risk_score}</span>
            </div>
        </td>
        <td class="px-6 py-4">${riskBadge}</td>
        <td class="px-6 py-4 text-xs font-medium text-gray-500">
            ${txn.status === 'Flagged' ? '<span class="text-blue-600 font-semibold">Flagged</span>' : 'Processed'}
        </td>
        <td class="px-6 py-4">
            <button class="details-toggle p-1.5 text-gray-400 hover:text-indigo-600 hover:bg-indigo-50 rounded transition-all inline-block" 
                title="View Fraud Analysis" aria-label="Toggle fraud details">
                <i class="ph ph-caret-down text-lg"></i>
            </button>
        </td>
    `;

    // Build expandable details row with fraud explanation factors
    const detailsRow = document.createElement('tr');
    detailsRow.className = 'hidden bg-gradient-to-r from-gray-50 to-white';
    detailsRow.setAttribute('data-row-type', 'details');
    detailsRow.setAttribute('data-parent-id', txn.id);
    const detailsCell = document.createElement('td');
    detailsCell.colSpan = 9;
    detailsCell.className = 'px-6 py-4';

    // Render top_features content
    const features = txn.top_features || [];
    if (features.length > 0) {
        detailsCell.innerHTML = `
            <div class="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
                <div class="col-span-2">
                    <h4 class="font-bold text-gray-700 mb-2 flex items-center gap-1">
                        <i class="ph ph-shield-warning text-blue-500"></i> Top Risk Factors
                    </h4>
                    <ul class="space-y-1.5">
                        ${features.slice(0, 5).map(f => `
                            <li class="flex justify-between items-center bg-white rounded px-3 py-1.5 border border-gray-100">
                                <span class="text-gray-700">${f.feature}</span>
                                <div class="flex items-center gap-2">
                                    ${f.value ? `<span class="text-gray-400 text-[10px]">${f.value}</span>` : ''}
                                    <span class="font-mono font-semibold ${f.contribution > 0.3 ? 'text-red-600' : f.contribution > 0.15 ? 'text-blue-600' : 'text-yellow-600'}">
                                        +${(f.contribution * 100).toFixed(1)}%
                                    </span>
                                </div>
                            </li>
                        `).join('')}
                    </ul>
                </div>
                <div class="flex flex-col justify-center items-center gap-2 bg-white rounded-lg border border-gray-100 p-3">
                    <div class="text-2xl font-bold ${txn.risk_score >= 80 ? 'text-red-600' : txn.risk_score >= 60 ? 'text-blue-600' : txn.risk_score >= 20 ? 'text-yellow-600' : 'text-green-600'}">${txn.risk_score}/100</div>
                    <div class="text-[10px] text-gray-400 uppercase tracking-wide">Risk Score</div>
                    <div class="w-full h-2 bg-gray-100 rounded-full overflow-hidden">
                        <div class="h-full rounded-full ${txn.risk_score >= 80 ? 'bg-red-500' : txn.risk_score >= 60 ? 'bg-blue-400' : txn.risk_score >= 20 ? 'bg-yellow-400' : 'bg-green-400'}" style="width:${Math.min(txn.risk_score, 100)}%"></div>
                    </div>
                    <span class="text-[10px] text-gray-500 italic mt-1">AI-generated analysis • ${features.length} factor${features.length > 1 ? 's' : ''}</span>
                </div>
            </div>
        `;
    } else {
        detailsCell.innerHTML = `
            <div class="flex items-center gap-2 text-gray-400 text-xs py-2">
                <i class="ph ph-info"></i>
                <span>No specific risk factors identified for this transaction.</span>
            </div>
        `;
    }

    detailsRow.appendChild(detailsCell);

    // Toggle details row on click
    const toggleDetails = (e) => {
        // Don't toggle if they clicked a link
        if (e && e.target && (e.target.tagName === 'A' || e.target.closest('a'))) return;
        const isHidden = detailsRow.classList.contains('hidden');
        detailsRow.classList.toggle('hidden');
        // Rotate the caret icon
        const icon = row.querySelector('.details-toggle i');
        if (icon) {
            icon.className = isHidden ? 'ph ph-caret-up text-lg' : 'ph ph-caret-down text-lg';
        }
    };

    row.addEventListener('click', toggleDetails);

    fragment.appendChild(row);
    fragment.appendChild(detailsRow);
    return fragment;
}






