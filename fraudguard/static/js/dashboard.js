document.addEventListener('DOMContentLoaded', () => {
    fetchData();
});

async function fetchData() {
    try {
        const response = await fetch('/api/data');
        const data = await response.json();
        
        // Update Metrics
        updateMetric('total-txn', data.metrics.total_transactions.toLocaleString());
        updateMetric('fraud-rate', data.metrics.fraud_rate + '%');
        updateMetric('approval-rate', data.metrics.approval_rate + '%');
        updateMetric('active-alerts', data.metrics.active_alerts);
        
        // Update Model Health
        updateMetric('model-name', data.model_health.name);
        updateMetric('model-version', 'v' + data.model_health.version);
        updateMetric('model-accuracy', data.model_health.accuracy + '%');
        updateMetric('drift-status', data.model_health.drift_status);

        // Update Table
        populateTable(data.transactions);

        // Initialize Charts
        initCharts();

    } catch (error) {
        console.error('Error fetching data:', error);
    }
}

function updateMetric(id, value) {
    const el = document.getElementById(id);
    if (el) el.innerText = value;
}

function populateTable(transactions) {
    const tbody = document.getElementById('txn-table-body');
    if (!tbody) return;

    tbody.innerHTML = '';
    
    // Show only recent 5 for dashboard
    const recentTxns = transactions.slice(0, 5);

    recentTxns.forEach(txn => {
        const row = document.createElement('tr');
        row.className = 'hover:bg-gray-50 cursor-pointer transition-colors';
        
        // Risk Score Color
        let riskColor = 'text-green-600 bg-green-50';
        if (txn.risk_score > 80) riskColor = 'text-red-600 bg-red-50 font-bold';
        else if (txn.risk_score > 50) riskColor = 'text-orange-600 bg-orange-50';

        // Status Color
        let statusColor = 'bg-gray-100 text-gray-800';
        if (txn.status === 'Approved') statusColor = 'bg-green-100 text-green-800';
        if (txn.status === 'Declined') statusColor = 'bg-red-100 text-red-800';
        if (txn.status === 'Flagged') statusColor = 'bg-orange-100 text-orange-800';
        if (txn.status === 'Review') statusColor = 'bg-yellow-100 text-yellow-800';

        row.innerHTML = `
            <td class="px-6 py-4 whitespace-nowrap text-gray-500">${txn.time}</td>
            <td class="px-6 py-4 font-mono text-xs text-gray-600">${txn.id}</td>
            <td class="px-6 py-4 font-medium text-gray-900">${txn.merchant}</td>
            <td class="px-6 py-4 text-gray-900">$${txn.amount.toFixed(2)}</td>
            <td class="px-6 py-4">
                <span class="px-2 py-1 rounded-full text-xs font-medium ${riskColor}" title="Fraud Probability">
                    ${txn.risk_score}/100
                </span>
            </td>
            <td class="px-6 py-4">
                <span class="px-2 py-1 rounded-full text-xs font-medium ${statusColor}">
                    ${txn.status}
                </span>
            </td>
        `;
        row.onclick = () => alert(`Viewing details for transaction ${txn.id}`);
        tbody.appendChild(row);
    });
}
