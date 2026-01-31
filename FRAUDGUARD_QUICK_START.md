# FraudGuard Web - Quick Start 🚀

## What's Fixed

✅ **Inference API** now has `run_inference()` method  
✅ **Dashboard** reads correct columns from inference  
✅ **Charts** show real fraud trends (not fake data)  
✅ **Live Updates** via Server-Sent Events (SSE)  

---

## 5-Minute Setup

### 1. **Start PostgreSQL** (if not running)
```bash
# Docker
docker run -d --name fraud-postgres -p 5432:5432 postgres:13

# Or local PostgreSQL
psql -U postgres
```

### 2. **Initialize Database** (one time)
```bash
psql -U postgres -f src/init-multiple-dbs.sh
```

### 3. **Start Producer** (generates transactions)
```bash
# PowerShell
.\scripts\start-producer.ps1

# Or Bash
bash scripts/start-producer.sh

# Or manually
python3 producer/main.py
```

### 4. **Start Inference API**
```bash
cd src/inference
python3 api_server.py
# Listens on http://localhost:8000
```

### 5. **Start FraudGuard Dashboard**
```bash
cd fraudguard
python3 app.py
# Open http://localhost:5000
```

---

## Verify It's Working

### Check Inference API
```bash
curl http://localhost:8000/health
# Should return: {"status": "healthy", "model_loaded": true}

curl -X POST http://localhost:8000/inference/run \
  -H "Content-Type: application/json" \
  -d '{"max_records": 100}'
# Should return: {status: success, results: [...]}
```

### Check Dashboard
```bash
curl http://localhost:5000/api/data
# Should return transactions with real fraud predictions
```

### Watch Live Updates
```bash
# In browser console:
const es = new EventSource('http://localhost:5000/stream/transactions');
es.addEventListener('transactions', (ev) => {
  console.log('New predictions:', JSON.parse(ev.data));
});
```

---

## What You'll See

### Dashboard Metrics (Real)
- **Total Transactions**: Actual count from all predictions
- **Fraud Rate**: Real percentage (not made up)
- **Transactions Table**: Actual recent predictions

### Charts (Real Data)
- **Valid Line**: Based on approved transaction count
- **Fraud Line**: Based on fraud detections
- **Trend**: Realistic variation, not synthetic

### Live Updates
- Dashboard refreshes every 5 seconds (polling)
- **Plus** instant updates when new predictions arrive (SSE)
- No stale data

---

## Data Flow

```
Producer                 Inference API            Dashboard
   │                          │                       │
   ├─ Generate Txns ─────────>│                       │
   │                          │ Run Inference         │
   │                          ├─ Make Predictions    │
   │                          ├─ Save to DB          │
   │                          │                       │
   │                          ├─ Broadcast SSE ─────>│ Updates
   │                          │                       │
   │                          │<─ /api/data ────────<│ Poll
   │                          │                       │
   └───── Keep generating ────>─ /stream/transactions>─ Live
```

---

## Columns in Dashboard

| Column | Source | Maps From |
|--------|--------|-----------|
| **Time** | transaction timestamp | `timestamp` field |
| **ID** | transaction_id | `transaction_id` |
| **User** | user_id | `user_id` or `full_name` |
| **Amount** | transaction amount | `amount` field |
| **Risk** | fraud probability | `fraud_probability * 100` |
| **Status** | prediction result | `fraud_label` ('FRAUD'/'LEGITIMATE') |

---

## Status Colors

| Status | Meaning | Color |
|--------|---------|-------|
| **Approved** | Legitimate (fraud_prediction=0) | 🟢 Green |
| **Flagged** | Likely fraud but not certain (0.5-0.8 probability) | 🟠 Orange |
| **Declined** | Likely fraud with high confidence (≥0.8 probability) | 🔴 Red |

---

## Test with Real Data

### Option 1: Wait for Producer
Producer generates transactions continuously. Inference API will find them and score them. Dashboard will show results.

### Option 2: Trigger Manually
```bash
# Run single inference batch
curl -X POST http://localhost:8000/inference/run \
  -H "Content-Type: application/json" \
  -d '{"max_records": 1000}'
```

### Option 3: Check Cumulative Stats
```bash
curl http://localhost:8000/inference/stats
# Shows: {total_records: 50000, fraud_detections: 5000, fraud_rate: 10.0}
```

---

## Troubleshooting

### Dashboard shows "—" (dashes)
- **Cause**: Inference API unreachable or no data
- **Fix**: 
  1. Check inference API is running: `curl http://localhost:8000/health`
  2. Run inference: `curl -X POST http://localhost:8000/inference/run -d '{}'`
  3. Refresh dashboard

### Charts show no data
- **Cause**: No transactions in `/api/data` response
- **Fix**: 
  1. Check producer is running
  2. Check database has transactions: `psql -c "SELECT count(*) FROM transactions"`
  3. Run inference to score them

### Live updates not working
- **Cause**: SSE not supported or connection closed
- **Fix**: 
  1. Check browser console for errors
  2. Polling will work as fallback (5 seconds)
  3. Restart dashboard app

---

## Environment Variables

### For Inference API
```bash
DB_HOST=127.0.0.1
DB_PORT=5432
DB_NAME=transactions_db
DB_USER=fraud_inference
DB_PASSWORD=inference_password
INFERENCE_PORT=8000
FLASK_DEBUG=false
```

### For Dashboard
```bash
INFERENCE_SERVICE_URL=http://localhost:8000
MLFLOW_TRACKING_URI=http://localhost:5500
FLASK_PORT=5000
FLASK_DEBUG=false
```

### For Producer
```bash
DB_HOST=127.0.0.1
DB_PORT=5432
DB_NAME=transactions_db
DB_USER=fraud_producer
DB_PASSWORD=producer_password
PRODUCER_BATCH_SIZE=100
PRODUCER_INTERVAL=10
```

---

## Next Steps

1. ✅ Start producer (generates data)
2. ✅ Start inference API (scores data)
3. ✅ Start dashboard (displays results)
4. 🔄 Watch dashboard update with real fraud predictions
5. 📊 Train new models with accumulated data
6. 🚀 Deploy to production

---

## Files Changed

```
✅ src/inference/inference.py
   - Added run_inference() method

✅ fraudguard/app.py
   - Fixed _map_result_to_txn() column mapping

✅ fraudguard/static/js/dashboard.js
   - Real fraud trend charts
   - Live SSE updates
```

**Full details**: See [FRAUDGUARD_WEB_INTEGRATION_FIXED.md](FRAUDGUARD_WEB_INTEGRATION_FIXED.md)

---

## That's it! 🎉

Dashboard now reads real fraud predictions from inference API and shows them live. All columns correct, all charts real, all updates live.

**Boss, it's ready to go!** 🚀
