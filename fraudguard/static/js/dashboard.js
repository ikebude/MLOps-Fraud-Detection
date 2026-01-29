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
                try { const dd = new Date(r.time); if (!isNaN(dd.getTime())) t = dd.toLocaleString(); } catch (e) {}
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
                updateMetric('model-precision', h.precision != null ? String(h.precision) : '—');
                updateMetric('model-recall', h.recall != null ? String(h.recall) : '—');
                updateMetric('model-f1', h.f1 != null ? String(h.f1) : '—');
                updateMetric('model-auc', h.auc != null ? String(h.auc) : '—');
                renderTable(d.transactions || []);
                var total = m.total_transactions || 0;
                var fraud = m.fraud_detections || 0;
                var v = Math.max(0, total - fraud);
                initChart(
                    [v * 0.7, v * 0.75, v * 0.8, v * 0.78, v * 0.85, v * 0.82, v * 0.9],
                    [fraud * 0.5, fraud * 0.6, fraud * 0.4, fraud * 0.7, fraud * 0.5, fraud * 0.6, fraud * 0.55]
                );
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
    }
})();
