// Enhanced FraudGuard Dashboard JavaScript - Production Ready
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
    lastUpdate: null,
    chartTimePeriod: '1h'
};

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
    const diffSeconds = Math.floor((now - lastUpdate) / 1000);
    
    if (diffSeconds < 10) {
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
    if (previousValue !== null && previousValue !== value) {
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
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'Valid Transactions',
                data: [],
                borderColor: '#1F2937',
                backgroundColor: 'rgba(31, 41, 55, 0.1)',
                tension: 0.4,
                fill: true,
                pointRadius: 3,
                pointHoverRadius: 5
            },
            {
                label: 'Fraud Attempts',
                data: [],
                borderColor: '#F97316',
                backgroundColor: 'rgba(249, 115, 22, 0.1)',
                tension: 0.4,
                fill: true,
                pointRadius: 3,
                pointHoverRadius: 5
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
                    position: 'bottom',
                    labels: {
                        usePointStyle: true,
                        padding: 15
                    }
                },
                tooltip: {
                    backgroundColor: 'rgba(0, 0, 0, 0.8)',
                    padding: 12,
                    titleFont: { size: 14, weight: 'bold' },
                    bodyFont: { size: 13 },
                    cornerRadius: 8,
                    displayColors: true
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    grid: {
                        color: 'rgba(0, 0, 0, 0.05)'
                    },
                    ticks: {
                        precision: 0
                    }
                },
                x: {
                    grid: {
                        display: false
                    },
                    ticks: {
                        maxRotation: 45,
                        minRotation: 0
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
        window.mainChart.data.labels = trends.labels;
        window.mainChart.data.datasets[0].data = trends.valid_transactions || [];
        window.mainChart.data.datasets[1].data = trends.fraud_attempts || [];
        window.mainChart.update('active'); // Smooth animation
    } catch (error) {
        console.error('Error updating chart:', error);
    }
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
    else if (txn.risk_score > 50) riskColor = 'text-orange-600 bg-orange-50';

    let statusColor = 'bg-gray-100 text-gray-800';
    if (txn.status === 'Approved') statusColor = 'bg-green-100 text-green-800';
    if (txn.status === 'Declined') statusColor = 'bg-red-100 text-red-800';
    if (txn.status === 'Flagged') statusColor = 'bg-orange-100 text-orange-800';

    row.innerHTML = `
        <td class="px-6 py-4 whitespace-nowrap text-gray-500 font-mono text-xs">${txn.time}</td>
        <td class="px-6 py-4 font-mono text-xs text-gray-600">${txn.id}</td>
        <td class="px-6 py-4 font-medium text-gray-900">${txn.merchant}</td>
        <td class="px-6 py-4 text-gray-900 font-semibold">$${txn.amount.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}</td>
        <td class="px-6 py-4">
            <span class="px-2 py-1 rounded-full text-xs font-medium ${riskColor}">
                ${txn.risk_score}/100
            </span>
        </td>
        <td class="px-6 py-4">
            <span class="px-2 py-1 rounded-full text-xs font-medium ${statusColor}">
                ${txn.status}
            </span>
        </td>
        <td class="px-6 py-4">
            <button class="text-orange-600 hover:text-orange-700 text-xs font-medium" onclick="viewTransactionDetails('${txn.id}')">
                View
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
    detailsCell.colSpan = 7;
    detailsCell.className = 'px-6 py-4 text-xs text-gray-600';
    detailsCell.innerHTML = renderTopFeatures(txn.top_features);
    detailsRow.appendChild(detailsCell);

    row.onclick = () => {
        if (!txn.top_features || txn.top_features.length === 0) return;
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
        const basePath = window.FRAUDGUARD_BASE_PATH || '';
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
        
        // Update data freshness
        if (data.inference_stats && data.inference_stats.timestamp) {
            updateDataFreshness(data.inference_stats.timestamp);
        }
        
        // Store previous metrics for trend calculation
        dashboardState.previousMetrics = { ...dashboardState.metrics };
        
        // Update metrics with animations
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
            
            // Update trends - calculate from REAL previous values
            const totalTrend = calculateTrend(metrics.total_transactions, dashboardState.previousMetrics.total_transactions);
            const fraudTrend = calculateTrend(metrics.fraud_rate, dashboardState.previousMetrics.fraud_rate);
            const approvalTrend = calculateTrend(metrics.approval_rate, dashboardState.previousMetrics.approval_rate);
            
            updateTrendDisplay('total-txn-trend', totalTrend, 'transaction');
            updateTrendDisplay('fraud-rate-trend', fraudTrend, 'fraud');
            updateTrendDisplay('approval-rate-trend', approvalTrend, 'approval');
            
            // Update alerts status dynamically
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
                    alertsEl.className = 'flex items-center text-sm text-orange-600 font-medium';
                    alertsEl.innerHTML = '<span>Requires attention</span>';
                }
            }
            
            // Store current metrics
            dashboardState.metrics = { ...metrics };
        }
        
        // Update model health
        if (data.model_health) {
            updateModelHealthEnhanced(data.model_health);
        }
        
        // Update inference stats
        if (data.inference_stats) {
            updateInferenceStats(data.inference_stats);
        }
        
        // Update table
        if (data.transactions && Array.isArray(data.transactions)) {
            populateTableEnhanced(data.transactions);
        }
        
        // Update charts
        if (typeof initChartsEnhanced === 'function' && !window.chartsInitialized) {
            initChartsEnhanced();
            window.chartsInitialized = true;
        }
        if (typeof updateChartsEnhanced === 'function' && data.trends) {
            updateChartsEnhanced(data.trends);
        }
        
        dashboardState.lastUpdate = new Date();
        
    } catch (error) {
        console.error('Error fetching data:', error);
        showError('Failed to load dashboard data. Please refresh the page.');
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
    const accuracy = health.accuracy || 0;
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
        updateMetricEnhanced('avg-fraud-prob', (stats.avg_fraud_probability * 100).toFixed(2) + '%');
    }
    if (stats.avg_confidence !== undefined) {
        updateMetricEnhanced('avg-confidence', (stats.avg_confidence * 100).toFixed(2) + '%');
    }
    if (stats.total_records !== undefined) {
        updateMetricEnhanced('inference-total', (stats.total_records || 0).toLocaleString());
    }
    if (stats.fraud_detections !== undefined) {
        updateMetricEnhanced('inference-fraud', (stats.fraud_detections || 0).toLocaleString());
    }
}

function populateTableEnhanced(transactions) {
    const tbody = document.getElementById('txn-table-body');
    if (!tbody) return;

    tbody.innerHTML = '';
    
    if (!transactions || transactions.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="7" class="px-6 py-8 text-center text-gray-400">
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
    const errorMsg = document.createElement('div');
    errorMsg.className = 'fixed top-4 right-4 bg-red-500 text-white p-4 rounded-lg shadow-lg z-50 max-w-md';
    errorMsg.innerHTML = `
        <div class="flex items-center gap-2">
            <i class="ph ph-warning-circle text-xl"></i>
            <span>${message}</span>
        </div>
    `;
    document.body.appendChild(errorMsg);
    setTimeout(() => errorMsg.remove(), 5000);
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    // Initialize sparklines
    initSparklines();
    
    // Initial data fetch
    fetchDataEnhanced();
    
    // Set up polling as fallback (faster for real-time)
    setInterval(fetchDataEnhanced, 2000); // Every 2 seconds for TRUE real-time updates
    
    // Set up EventSource for real-time updates
    if (window.EventSource) {
        const basePath = window.FRAUDGUARD_BASE_PATH || '';
        const streamUrl = `${basePath}/api/stream?interval_ms=2000`;
        const stream = new EventSource(streamUrl);
        
        stream.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                // Update metrics in real-time
                if (data.metrics) {
                    dashboardState.previousMetrics = { ...dashboardState.metrics };
                    dashboardState.metrics = data.metrics;
                    
                    updateMetricEnhanced('total-txn', (data.metrics.total_transactions || 0).toLocaleString());
                    updateMetricEnhanced('fraud-rate', (data.metrics.fraud_rate || 0).toFixed(2) + '%');
                    updateMetricEnhanced('approval-rate', (data.metrics.approval_rate || 0).toFixed(2) + '%');
                    updateMetricEnhanced('active-alerts', data.metrics.active_alerts || 0);
                }
                
                if (data.transaction) {
                    // ALWAYS prepend new transaction to ensure live feed updates
                    prependTransactionRowEnhanced(data.transaction);
                }
                
                // Also update trends from stream data
                if (data.metrics && typeof calculateTrend === 'function') {
                    const totalTrend = calculateTrend(data.metrics.total_transactions, dashboardState.previousMetrics.total_transactions);
                    const fraudTrend = calculateTrend(data.metrics.fraud_rate, dashboardState.previousMetrics.fraud_rate);
                    const approvalTrend = calculateTrend(data.metrics.approval_rate, dashboardState.previousMetrics.approval_rate);
                    
                    if (typeof updateTrendDisplay === 'function') {
                        updateTrendDisplay('total-txn-trend', totalTrend, 'transaction');
                        updateTrendDisplay('fraud-rate-trend', fraudTrend, 'fraud');
                        updateTrendDisplay('approval-rate-trend', approvalTrend, 'approval');
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
                            alertsEl.className = 'flex items-center text-sm text-orange-600 font-medium';
                            alertsEl.innerHTML = '<span>Requires attention</span>';
                        }
                    }
                    
                    // Store as previous for next comparison
                    dashboardState.previousMetrics = { ...data.metrics };
                }
            } catch (err) {
                console.error('Stream parse error:', err);
            }
        };
        
        stream.onerror = () => {
            console.log('EventSource error, using polling fallback');
            stream.close();
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
