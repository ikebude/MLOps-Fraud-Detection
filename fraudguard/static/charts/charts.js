function initCharts() {
    const ctx = document.getElementById('mainChart');
    if (!ctx) return;

    // Use enhanced chart if available
    if (typeof initChartsEnhanced === 'function') {
        initChartsEnhanced();
        return;
    }

    const defaultLabels = ['10:00', '10:15', '10:30', '10:45', '11:00', '11:15', '11:30'];
    const defaultValid = [65, 59, 80, 81, 56, 55, 40];
    const defaultFraud = [5, 2, 8, 12, 4, 3, 1];

    window.mainChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: defaultLabels,
            datasets: [{
                label: 'Valid Transactions',
                data: defaultValid,
                borderColor: '#1F2937',
                backgroundColor: 'rgba(31, 41, 55, 0.1)',
                tension: 0.4,
                fill: true,
                pointRadius: 3,
                pointHoverRadius: 5
            },
            {
                label: 'Fraud Attempts',
                data: defaultFraud,
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
                    cornerRadius: 8
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    grid: {
                        color: 'rgba(0, 0, 0, 0.05)'
                    }
                },
                x: {
                    grid: {
                        display: false
                    }
                }
            },
            animation: {
                duration: 750
            }
        }
    });
}

function updateCharts(trends) {
    // Use enhanced chart update if available
    if (typeof updateChartsEnhanced === 'function') {
        updateChartsEnhanced(trends);
        return;
    }
    
    if (!window.mainChart || !trends) {
        console.warn('Chart not initialized or no trends data');
        return;
    }
    if (!Array.isArray(trends.labels) || trends.labels.length === 0) {
        console.warn('No valid labels in trends data');
        return;
    }
    if (!Array.isArray(trends.valid_transactions) || !Array.isArray(trends.fraud_attempts)) {
        console.warn('Invalid trends data structure');
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

window.updateCharts = updateCharts;

function appendChartPoint(label, isFraud, maxPoints = 12) {
    if (!window.mainChart || !label) return;

    const labels = window.mainChart.data.labels || [];
    const validData = window.mainChart.data.datasets[0].data || [];
    const fraudData = window.mainChart.data.datasets[1].data || [];

    if (labels.length > 0 && labels[labels.length - 1] === label) {
        if (isFraud) {
            fraudData[fraudData.length - 1] = (fraudData[fraudData.length - 1] || 0) + 1;
        } else {
            validData[validData.length - 1] = (validData[validData.length - 1] || 0) + 1;
        }
    } else {
        labels.push(label);
        validData.push(isFraud ? 0 : 1);
        fraudData.push(isFraud ? 1 : 0);

        if (labels.length > maxPoints) {
            labels.shift();
            validData.shift();
            fraudData.shift();
        }
    }

    window.mainChart.update();
}

window.appendChartPoint = appendChartPoint;
