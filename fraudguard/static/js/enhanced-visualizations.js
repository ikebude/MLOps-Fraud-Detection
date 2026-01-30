/**
 * Enhanced Visualizations for Fraud Detection Dashboard
 * 
 * Adds:
 * - Financial impact charts
 * - Model performance trends
 * - Feature importance visualization
 * - Advanced transaction analytics
 */

// Financial Impact Chart
function initFinancialImpactChart(data) {
    const ctx = document.getElementById('financial-impact-chart');
    if (!ctx) return;
    
    const businessMetrics = data.enhanced_metrics?.business_metrics || {};
    
    new Chart(ctx, {
        type: 'bar',
        data: {
            labels: ['Fraud Prevented', 'Revenue Preserved', 'Total Volume'],
            datasets: [{
                label: 'USD Value',
                data: [
                    businessMetrics.fraud_prevented_value_usd || 0,
                    businessMetrics.revenue_preserved_usd || 0,
                    businessMetrics.total_volume_usd || 0
                ],
                backgroundColor: [
                    'rgba(239, 68, 68, 0.8)',  // Red for fraud prevented
                    'rgba(34, 197, 94, 0.8)',  // Green for revenue
                    'rgba(59, 130, 246, 0.8)'  // Blue for total
                ],
                borderColor: [
                    'rgb(239, 68, 68)',
                    'rgb(34, 197, 94)',
                    'rgb(59, 130, 246)'
                ],
                borderWidth: 2
            }]
        },
        options: {
            responsive: true,
            plugins: {
                legend: { display: false },
                title: {
                    display: true,
                    text: 'Financial Impact (USD)'
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return '$' + context.parsed.y.toLocaleString('en-US', {
                                minimumFractionDigits: 2,
                                maximumFractionDigits: 2
                            });
                        }
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        callback: function(value) {
                            return '$' + value.toLocaleString();
                        }
                    }
                }
            }
        }
    });
}

// Model Performance Trend Chart
function initModelPerformanceTrend(data) {
    const ctx = document.getElementById('model-performance-trend');
    if (!ctx) return;
    
    // This would use historical metrics from the metrics tracker
    // For now, show current vs baseline
    const modelHealth = data.model_health || {};
    const accuracy = modelHealth.accuracy || 0;
    
    new Chart(ctx, {
        type: 'line',
        data: {
            labels: ['Baseline', 'Current'],
            datasets: [{
                label: 'Model Accuracy (%)',
                data: [85, accuracy], // Baseline vs current
                borderColor: 'rgb(59, 130, 246)',
                backgroundColor: 'rgba(59, 130, 246, 0.1)',
                tension: 0.4,
                fill: true
            }]
        },
        options: {
            responsive: true,
            plugins: {
                title: {
                    display: true,
                    text: 'Model Performance Trend'
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    max: 100,
                    ticks: {
                        callback: function(value) {
                            return value + '%';
                        }
                    }
                }
            }
        }
    });
}

// Feature Importance Visualization
function initFeatureImportanceChart(featureData) {
    const ctx = document.getElementById('feature-importance-chart');
    if (!ctx || !featureData) return;
    
    // Extract top 10 features
    const features = Object.entries(featureData)
        .sort((a, b) => b[1].mean_importance - a[1].mean_importance)
        .slice(0, 10);
    
    new Chart(ctx, {
        type: 'horizontalBar',
        data: {
            labels: features.map(f => f[0]),
            datasets: [{
                label: 'Importance Score',
                data: features.map(f => f[1].mean_importance),
                backgroundColor: 'rgba(239, 68, 68, 0.8)',
                borderColor: 'rgb(239, 68, 68)',
                borderWidth: 1
            }]
        },
        options: {
            indexAxis: 'y',
            responsive: true,
            plugins: {
                title: {
                    display: true,
                    text: 'Top 10 Feature Importance'
                }
            },
            scales: {
                x: {
                    beginAtZero: true
                }
            }
        }
    });
}

// Enhanced Transaction Analytics
function analyzeTransactions(transactions) {
    if (!transactions || transactions.length === 0) {
        return {};
    }
    
    const analysis = {
        total_count: transactions.length,
        flagged_count: transactions.filter(t => t.status === 'Flagged').length,
        total_amount: transactions.reduce((sum, t) => sum + (t.amount || 0), 0),
        flagged_amount: transactions
            .filter(t => t.status === 'Flagged')
            .reduce((sum, t) => sum + (t.amount || 0), 0),
        avg_risk_score: transactions.reduce((sum, t) => sum + (t.risk_score || 0), 0) / transactions.length,
        high_risk_count: transactions.filter(t => (t.risk_score || 0) > 80).length,
        medium_risk_count: transactions.filter(t => (t.risk_score || 0) > 50 && (t.risk_score || 0) <= 80).length,
        low_risk_count: transactions.filter(t => (t.risk_score || 0) <= 50).length
    };
    
    analysis.fraud_rate = (analysis.flagged_count / analysis.total_count) * 100;
    analysis.avg_transaction_value = analysis.total_amount / analysis.total_count;
    analysis.avg_flagged_transaction_value = analysis.flagged_amount / (analysis.flagged_count || 1);
    
    return analysis;
}

// Update dashboard with enhanced analytics
function updateEnhancedDashboard(data) {
    // Update financial metrics if available
    const businessMetrics = data.enhanced_metrics?.business_metrics;
    if (businessMetrics) {
        updateMetric('fraud-prevented-value', 
            '$' + (businessMetrics.fraud_prevented_value_usd || 0).toLocaleString('en-US', {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2
            }));
        updateMetric('revenue-preserved', 
            '$' + (businessMetrics.revenue_preserved_usd || 0).toLocaleString('en-US', {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2
            }));
        updateMetric('estimated-roi', 
            (businessMetrics.estimated_roi_percent || 0).toFixed(2) + '%');
    }
    
    // Update operational metrics if available
    const operationalMetrics = data.enhanced_metrics?.operational_metrics;
    if (operationalMetrics) {
        updateMetric('avg-latency', 
            (operationalMetrics.avg_latency_ms || 0).toFixed(2) + 'ms');
        updateMetric('throughput', 
            (operationalMetrics.throughput_tps || 0).toFixed(2) + ' tps');
    }
    
    // Initialize charts if data available
    if (data.enhanced_metrics) {
        initFinancialImpactChart(data);
        initModelPerformanceTrend(data);
    }
    
    // Feature drift analysis
    const featureDrift = data.feature_drift || {};
    if (Object.keys(featureDrift).length > 0) {
        initFeatureImportanceChart(featureDrift);
    }
}

// Enhanced transaction table with sorting
function initTransactionTableSorting() {
    const headers = document.querySelectorAll('#txn-table-body').parentElement?.querySelectorAll('th');
    if (!headers) return;
    
    headers.forEach((header, index) => {
        header.style.cursor = 'pointer';
        header.addEventListener('click', () => {
            const currentSort = header.getAttribute('data-sort') || 'none';
            const newSort = currentSort === 'asc' ? 'desc' : 'asc';
            
            // Reset all headers
            headers.forEach(h => h.setAttribute('data-sort', 'none'));
            header.setAttribute('data-sort', newSort);
            
            // Get sort field name
            const sortField = header.getAttribute('data-sort-field') || 'timestamp';
            
            // Reload data with new sort
            const basePath = window.FRAUDGUARD_BASE_PATH || '';
            fetch(`${basePath}/api/data?sort_by=${sortField}&sort_order=${newSort}`)
                .then(response => response.json())
                .then(data => {
                    if (data.transactions) {
                        populateTable(data.transactions);
                    }
                });
        });
    });
}

// Export functions for use in main dashboard
if (typeof window !== 'undefined') {
    window.enhancedVisualizations = {
        initFinancialImpactChart,
        initModelPerformanceTrend,
        initFeatureImportanceChart,
        analyzeTransactions,
        updateEnhancedDashboard,
        initTransactionTableSorting
    };
}
