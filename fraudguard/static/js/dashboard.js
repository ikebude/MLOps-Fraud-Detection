document.addEventListener('DOMContentLoaded', () => {
    const basePath = window.FRAUDGUARD_BASE_PATH || '';

    const refreshButton = document.getElementById('refresh-model-btn');
    if (refreshButton) {
        refreshButton.addEventListener('click', async () => {
            try {
                refreshButton.disabled = true;
                refreshButton.classList.add('opacity-60');
                await fetch(`${basePath}/api/inference/run`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ max_records: 1000 })
                });
            } catch (error) {
                console.error('Error triggering inference:', error);
            } finally {
                refreshButton.disabled = false;
                refreshButton.classList.remove('opacity-60');
            }
        });
    }

    // Only run dashboard logic if we are on the dashboard page
    if (!document.getElementById('mainChart')) return;

    // Always start with fetchData immediately
    fetchData();

    // Then try EventSource, but fallback to polling if it fails
    if (window.EventSource) {
        try {
            startStream(basePath);
        } catch (error) {
            console.error('EventSource failed, using polling:', error);
            // Polling handled by dashboard-enhanced.js
            // setInterval(fetchData, 5000);
        }
    } else {
        // Polling handled by dashboard-enhanced.js
        // setInterval(fetchData, 5000);
    }
});

async function fetchData() {
    try {
        const basePath = window.FRAUDGUARD_BASE_PATH || '';
        const apiUrl = `${basePath}/api/data?refresh=1`;
        console.log('Fetching data from:', apiUrl);

        const response = await fetch(apiUrl);

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();
        console.log('Data received:', data);

        // Update Metrics
        if (data.metrics) {
            updateMetric('total-txn', (data.metrics.total_transactions || 0).toLocaleString());
            updateMetric('fraud-rate', (data.metrics.fraud_rate || 0) + '%');
            updateMetric('approval-rate', (data.metrics.approval_rate || 0) + '%');
            updateMetric('active-alerts', data.metrics.active_alerts || 0);
        }

        // Update Model Health
        if (data.model_health) {
            updateMetric('model-name', data.model_health.name || 'Unknown');
            updateMetric('model-version', 'v' + (data.model_health.version || 'N/A'));
            // Show accuracy with more precision (up to 2 decimal places)
            const accuracy = data.model_health.accuracy || 0;
            const accuracyStr = accuracy > 0 ? accuracy.toFixed(2) : '0.00';
            updateMetric('model-accuracy', accuracyStr + '%');
            // Update progress bar
            const progressBar = document.getElementById('accuracy-progress-bar');
            if (progressBar) {
                progressBar.style.width = Math.min(accuracy, 100) + '%';
            }
            updateMetric('drift-status', data.model_health.drift_status || 'Unknown');
        }

        // Update inference stats if available (for presentation)
        if (data.inference_stats) {
            console.log('Inference Stats:', data.inference_stats);
            if (data.inference_stats.avg_fraud_probability !== undefined) {
                updateMetric('avg-fraud-prob', (data.inference_stats.avg_fraud_probability * 100).toFixed(2) + '%');
            }
            if (data.inference_stats.avg_confidence !== undefined) {
                updateMetric('avg-confidence', (data.inference_stats.avg_confidence * 100).toFixed(2) + '%');
            }
            if (data.inference_stats.model_source) {
                updateMetric('model-source', data.inference_stats.model_source);
            }
        }

        // Update Table
        if (data.transactions && Array.isArray(data.transactions)) {
            populateTable(data.transactions);
        }

        // Initialize Charts (only once)
        if (typeof initCharts === 'function' && !window.chartsInitialized) {
            initCharts();
            window.chartsInitialized = true;
        }
        if (typeof updateCharts === 'function' && data.trends) {
            updateCharts(data.trends);
        }

    } catch (error) {
        console.error('Error fetching data:', error);
        console.error('Error details:', error.message, error.stack);
    }
}

function startStream(basePath) {
    const streamUrl = `${basePath}/api/stream?interval_ms=2000`;
    console.log('Starting EventSource stream:', streamUrl);
    const stream = new EventSource(streamUrl);

    stream.onopen = () => {
        console.log('EventSource stream opened');
    };

    stream.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            if (data.metrics) {
                // Store previous for trend calculation
                if (!window.previousMetrics) window.previousMetrics = {};

                updateMetric('total-txn', (data.metrics.total_transactions || 0).toLocaleString());
                updateMetric('fraud-rate', (data.metrics.fraud_rate || 0) + '%');
                updateMetric('approval-rate', (data.metrics.approval_rate || 0) + '%');
                updateMetric('active-alerts', data.metrics.active_alerts || 0);

                // Update trends dynamically
                if (typeof calculateTrend === 'function' && typeof updateTrendDisplay === 'function') {
                    const totalTrend = calculateTrend(data.metrics.total_transactions, window.previousMetrics.total_transactions);
                    const fraudTrend = calculateTrend(data.metrics.fraud_rate, window.previousMetrics.fraud_rate);
                    const approvalTrend = calculateTrend(data.metrics.approval_rate, window.previousMetrics.approval_rate);

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

                // Store current as previous for next update
                window.previousMetrics = { ...data.metrics };
            }

            if (data.model_health) {
                updateMetric('model-name', data.model_health.name || 'Unknown');
                updateMetric('model-version', 'v' + (data.model_health.version || 'N/A'));
                // Show accuracy with more precision
                const accuracy = data.model_health.accuracy || 0;
                const accuracyStr = accuracy > 0 ? accuracy.toFixed(2) : '0.00';
                updateMetric('model-accuracy', accuracyStr + '%');
                // Update progress bar
                const progressBar = document.getElementById('accuracy-progress-bar');
                if (progressBar) {
                    progressBar.style.width = Math.min(accuracy, 100) + '%';
                }
                updateMetric('drift-status', data.model_health.drift_status || 'Unknown');
            }

            if (data.transaction) {
                prependTransactionRow(data.transaction);
                if (typeof appendChartPoint === 'function') {
                    const isFraud = data.transaction.status === 'Flagged';
                    appendChartPoint(data.transaction.time, isFraud);
                }
            }

            if (typeof initCharts === 'function' && !window.chartsInitialized) {
                initCharts();
                window.chartsInitialized = true;
            }
        } catch (err) {
            console.error('Stream parse error:', err);
        }
    };

    stream.onerror = (error) => {
        console.error('EventSource error:', error);
        stream.close();
        // Fallback to polling
        console.log('Falling back to polling');
        fetchData();
        if (!window.pollingInterval) {
            window.pollingInterval = setInterval(fetchData, 30000);
        }
    };
}

function updateMetric(id, value) {
    const el = document.getElementById(id);
    if (el) el.innerText = value;
}

function populateTable(transactions) {
    // Use enhanced populate if available
    if (typeof populateTableEnhanced === 'function') {
        populateTableEnhanced(transactions);
        return;
    }

    const tbody = document.getElementById('txn-table-body');
    if (!tbody) return;

    tbody.innerHTML = '';

    // Show only recent 5 for dashboard
    const recentTxns = transactions.slice(0, 5);

    recentTxns.forEach(txn => {
        const fragment = buildTransactionRows(txn);
        tbody.appendChild(fragment);
    });
}

function buildTransactionRows(txn) {
    const fragment = document.createDocumentFragment();
    const row = document.createElement('tr');
    row.className = 'hover:bg-gray-50 cursor-pointer transition-colors';
    row.setAttribute('data-row-type', 'main');

    // DEBUG: Log to verify data
    console.log('Dashboard Transaction:', txn.id, 'fraud_probability:', txn.fraud_probability, 'risk_score:', txn.risk_score, 'risk_level:', txn.risk_level);

    let riskColor = 'text-green-600 bg-green-50';
    if (txn.risk_score > 80) riskColor = 'text-red-600 bg-red-50 font-bold';
    else if (txn.risk_score > 50) riskColor = 'text-orange-600 bg-orange-50';

    // Risk Level styling
    const riskLevel = txn.risk_level || 'UNKNOWN';
    let riskLevelColor = 'bg-gray-100 text-gray-800';
    if (riskLevel === 'CRITICAL') riskLevelColor = 'bg-red-100 text-red-800 font-bold';
    else if (riskLevel === 'HIGH') riskLevelColor = 'bg-orange-100 text-orange-800';
    else if (riskLevel === 'MEDIUM') riskLevelColor = 'bg-yellow-100 text-yellow-800';
    else if (riskLevel === 'LOW') riskLevelColor = 'bg-blue-100 text-blue-800';
    else if (riskLevel === 'MINIMAL') riskLevelColor = 'bg-green-100 text-green-800';

    let statusColor = 'bg-gray-100 text-gray-800';
    if (txn.status === 'Approved') statusColor = 'bg-green-100 text-green-800';
    if (txn.status === 'Declined') statusColor = 'bg-red-100 text-red-800';
    if (txn.status === 'Flagged') statusColor = 'bg-orange-100 text-orange-800';
    if (txn.status === 'Review') statusColor = 'bg-yellow-100 text-yellow-800';

    row.innerHTML = `
        <td class="px-6 py-4 whitespace-nowrap text-gray-500">${txn.time}</td>
        <td class="px-6 py-4 font-mono text-xs text-gray-600">${txn.id}</td>
        <td class="px-6 py-4 font-medium text-gray-900">${txn.merchant}</td>
        <td class="px-6 py-4 text-gray-600 text-xs">${txn.location || 'N/A'}</td>
        <td class="px-6 py-4 text-gray-900">$${txn.amount.toFixed(2)}</td>
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
            <button class="text-blue-600 hover:text-blue-800 text-xs font-medium">View</button>
        </td>
    `;
    if (txn.top_features && txn.top_features.length > 0) {
        row.title = txn.top_features
            .map(item => `${item.feature}: ${item.contribution.toFixed(3)}`)
            .join(' | ');
    }

    const detailsRow = document.createElement('tr');
    detailsRow.className = 'hidden bg-gray-50';
    detailsRow.setAttribute('data-row-type', 'details');
    const detailsCell = document.createElement('td');
    detailsCell.colSpan = 9;
    detailsCell.className = 'px-6 py-3 text-xs text-gray-600';
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

function prependTransactionRow(txn) {
    // Use enhanced prepend if available
    if (typeof prependTransactionRowEnhanced === 'function') {
        prependTransactionRowEnhanced(txn);
        return;
    }

    const tbody = document.getElementById('txn-table-body');
    if (!tbody) return;
    const fragment = buildTransactionRows(txn);
    tbody.prepend(fragment);

    const mainRows = Array.from(tbody.querySelectorAll('tr[data-row-type="main"]'));
    if (mainRows.length > 5) {
        const lastMain = mainRows[mainRows.length - 1];
        const lastDetails = lastMain.nextElementSibling;
        if (lastDetails && lastDetails.getAttribute('data-row-type') === 'details') {
            lastDetails.remove();
        }
        lastMain.remove();
    }
}

function renderTopFeatures(topFeatures) {
    if (!Array.isArray(topFeatures) || topFeatures.length === 0) {
        return '<span class="text-gray-400">No explanation available</span>';
    }
    const items = topFeatures.map(item => {
        const val = item.value === null || item.value === undefined ? 'n/a' : item.value;
        return `<span class="inline-flex items-center px-2 py-1 mr-2 mb-2 bg-white border border-gray-200 rounded">
            <strong class="mr-1">${item.feature}</strong>
            <span class="text-gray-500">(${item.contribution.toFixed(3)})</span>
            <span class="ml-2 text-gray-400">val: ${val}</span>
        </span>`;
    });
    return `<div class="flex flex-wrap">${items.join('')}</div>`;
}
