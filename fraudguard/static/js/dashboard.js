(function () {
    function el(id) { return document.getElementById(id); }
    function updateMetric(id, val) { var e = el(id); if (e) e.textContent = val; }

    function runInference() {
        var btn = el('btn-run-inference');
        if (btn) btn.disabled = true;
        fetch('/api/inference/run', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ max_records: 1000 })
        })
            .then(function () { window.location.reload(); })
            .catch(function () { window.location.reload(); })
            .finally(function () { if (btn) btn.disabled = false; });
    }
    function refresh() { window.location.reload(); }

    var brun = el('btn-run-inference');
    var bref = el('btn-refresh');
    if (brun) brun.addEventListener('click', runInference);
    if (bref) bref.addEventListener('click', refresh);

    function renderTable(rows) {
        var tbody = el('txn-table-body');
        if (!tbody) return;
        tbody.innerHTML = '';
        var slice = (rows || []).slice(0, 10);
        slice.forEach(function (r) {
            var riskCl = 'text-green-600 bg-green-50';
            if (r.risk_score > 80) riskCl = 'text-red-600 bg-red-50 font-bold';
            else if (r.risk_score > 50) riskCl = 'text-orange-600 bg-orange-50';
            var statusCl = 'bg-gray-100 text-gray-800';
            if (r.status === 'Approved') statusCl = 'bg-green-100 text-green-800';
            if (r.status === 'Declined') statusCl = 'bg-red-100 text-red-800';
            if (r.status === 'Flagged') statusCl = 'bg-orange-100 text-orange-800';
            var tr = document.createElement('tr');
            tr.className = 'hover:bg-gray-50';
            // format time if possible
            var t = r.time || '—';
            try { const dd = new Date(r.time); if (!isNaN(dd.getTime())) t = dd.toLocaleString(); } catch (e) { }
            tr.innerHTML = '<td class="px-6 py-4 whitespace-nowrap text-gray-500">' + t + '</td>' +
                '<td class="px-6 py-4 font-mono text-xs text-gray-600">' + r.id + '</td>' +
                '<td class="px-6 py-4 font-medium text-gray-900">' + r.merchant + '</td>' +
                '<td class="px-6 py-4 text-gray-900">' + (r.currency ? (r.currency + ' ') : '') + Number(r.amount).toFixed(2) + '</td>' +
                '<td class="px-6 py-4"><span class="px-2 py-1 rounded-full text-xs font-medium ' + riskCl + '">' + r.risk_score + '</span></td>' +
                '<td class="px-6 py-4"><span class="px-2 py-1 rounded-full text-xs font-medium ' + statusCl + '">' + r.status + '</span></td>';
            tbody.appendChild(tr);
        });
    }

    function initChart(valid, fraud) {
        var ctx = el('mainChart');
        if (!ctx || !window.Chart) return;
        var cfg = {
            type: 'line',
            data: {
                labels: ['1', '2', '3', '4', '5', '6', '7'],
                datasets: [
                    { label: 'Valid', data: valid, borderColor: '#1F2937', tension: 0.4, fill: false },
                    { label: 'Fraud', data: fraud, borderColor: '#F97316', tension: 0.4, fill: false }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { position: 'bottom' } },
                scales: { y: { beginAtZero: true }, x: {} }
            }
        };
        try {
            if (window._mainChart) window._mainChart.destroy();
            window._mainChart = new Chart(ctx, cfg);
        } catch (e) { /* ignore */ }
    }

    function fetchData() {
        if (!el('total-txn')) return;
        fetch('/api/data')
            .then(function (r) { return r.json(); })
            .then(function (d) {
                var m = (d.metrics || {});
                var h = (d.model_health || {});
                updateMetric('total-txn', (m.total_transactions != null) ? m.total_transactions.toLocaleString() : '—');
                updateMetric('fraud-rate', (m.fraud_rate != null) ? m.fraud_rate + '%' : '—');
                updateMetric('approval-rate', (m.approval_rate != null) ? m.approval_rate + '%' : '—');
                updateMetric('active-alerts', (m.active_alerts != null) ? m.active_alerts : '—');
                updateMetric('model-name', h.name || '—');
                updateMetric('model-version', h.version != null ? String(h.version) : '—');
                updateMetric('drift-status', h.drift_status || '—');
                updateMetric('model-precision', h.precision != null ? (typeof h.precision === 'string' ? h.precision : h.precision.toFixed(4)) : '—');
                updateMetric('model-precision-kpi', h.precision != null ? (typeof h.precision === 'string' ? h.precision : (h.precision * 100).toFixed(1) + '%') : '—');
                updateMetric('model-recall', h.recall != null ? (typeof h.recall === 'string' ? h.recall : h.recall.toFixed(4)) : '—');
                updateMetric('model-f1', h.f1 != null ? (typeof h.f1 === 'string' ? h.f1 : h.f1.toFixed(4)) : '—');
                updateMetric('model-auc', h.auc != null ? (typeof h.auc === 'string' ? h.auc : h.auc.toFixed(4)) : '—');
                renderTable(d.transactions || []);

                // Use REAL data: Calculate fraud trend from actual transactions
                var txnList = d.transactions || [];

                // Group transactions by time bucket (e.g., last 7 minutes or 7 distinct time points)
                // Since we get the last 200, we can bucket them by minute
                var buckets = {};
                var timestamps = [];

                txnList.forEach(function (t) {
                    try {
                        var date = new Date(t.time);
                        var key = date.getHours() + ':' + date.getMinutes(); // HH:MM
                        if (!buckets[key]) {
                            buckets[key] = { valid: 0, fraud: 0, time: date.getTime() };
                            timestamps.push(key);
                        }
                        if (t.status === 'Approved') {
                            buckets[key].valid++;
                        } else {
                            buckets[key].fraud++;
                        }
                    } catch (e) { }
                });

                // Sort buckets by time
                timestamps.sort(function (a, b) { return buckets[a].time - buckets[b].time; });

                // Take last 7 buckets or fill if fewer
                var validTrend = [];
                var fraudTrend = [];
                var labels = [];

                var showCount = 7;
                var start = Math.max(0, timestamps.length - showCount);
                for (var i = start; i < timestamps.length; i++) {
                    var k = timestamps[i];
                    labels.push(k);
                    validTrend.push(buckets[k].valid);
                    fraudTrend.push(buckets[k].fraud);
                }

                // If no data, show empty chart (better than fake data)
                if (labels.length === 0) labels = ['No Data'];

                // Update chart
                var ctx = el('mainChart');
                if (ctx && window.Chart) {
                    var cfg = {
                        type: 'line',
                        data: {
                            labels: labels,
                            datasets: [
                                { label: 'Valid', data: validTrend, borderColor: '#1F2937', tension: 0.4, fill: false },
                                { label: 'Fraud', data: fraudTrend, borderColor: '#F97316', tension: 0.4, fill: false }
                            ]
                        },
                        options: {
                            responsive: true,
                            maintainAspectRatio: false,
                            plugins: { legend: { position: 'bottom' } },
                            scales: { y: { beginAtZero: true, ticks: { stepSize: 1 } }, x: {} }
                        }
                    };
                    if (window._mainChart) window._mainChart.destroy();
                    window._mainChart = new Chart(ctx, cfg);
                }
            })
            .catch(function () {
                updateMetric('total-txn', '—');
                updateMetric('fraud-rate', '—');
                updateMetric('approval-rate', '—');
                updateMetric('active-alerts', '—');
            });
    }

    if (el('total-txn')) {
        fetchData();
        setInterval(fetchData, 5000);

        // Listen for live inference results via SSE
        if (typeof (EventSource) !== 'undefined') {
            try {
                var es = new EventSource('/stream/transactions');
                es.addEventListener('transactions', function (ev) {
                    try {
                        var payload = JSON.parse(ev.data || '{}');
                        if (payload.results && payload.results.length > 0) {
                            // Got new inference results, refresh metrics
                            fetchData();
                        }
                    } catch (e) { /* ignore parse errors */ }
                });
                es.onerror = function () { /* connection closed, will retry */ };
            } catch (e) { /* SSE not supported, polling is sufficient */ }
        }
    }
})();
