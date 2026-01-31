# 🎯 BOSS - Here's How to Run the FULL Live Solution

## The Simple Version (Copy-Paste Ready)

### Terminal 1: Start Database + All Services
```powershell
cd c:\Users\3Consult\Documents\AI Solution Projects\MLOps_Fraud_Detection\src

# One time: Initialize databases
docker-compose up -d postgres
sleep 10
psql -h 127.0.0.1 -U postgres -f init-multiple-dbs.sh

# Then: Start everything
docker-compose up -d

# Check it's running
docker-compose ps
```

### Terminal 2: Start Producer (Generates Data)
```powershell
cd c:\Users\3Consult\Documents\AI Solution Projects\MLOps_Fraud_Detection

# Start producer - generates 100 transactions every 60 seconds
.\scripts\start-producer.ps1

# Or manually:
python producer/main.py

# You'll see:
# [INFO] Producer: Generating batch of 100 transactions
# [INFO] Producer: Inserted 100 transactions in 1.2s
# [INFO] Stats: total=500, fraud_rate=8.5%
```

### Browser: Watch Dashboard
```
Open: http://localhost:5000

You'll see:
✅ Total Transactions (increasing: 100, 200, 300...)
✅ Fraud Rate (shows ~8-10%)
✅ Transactions table (updating every 5 seconds)
✅ Real fraud trend charts
✅ Model health metrics
```

---

## What's Running (The Full Stack)

```
┌─────────────────────────────────────────────────────────────┐
│                    YOUR COMPUTER                             │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  PRODUCER (Host Machine)                                     │
│  ├─ Runs: python producer/main.py                            │
│  ├─ Generates: 100 transactions every 60 seconds             │
│  └─ Writes to: PostgreSQL transactions_db                    │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  DOCKER CONTAINERS (docker-compose up -d)           │   │
│  ├──────────────────────────────────────────────────────┤   │
│  │                                                       │   │
│  │  🗄️ PostgreSQL (Port 5432)                          │   │
│  │  ├─ transactions_db (holds transaction data)         │   │
│  │  ├─ fraud_predictions (holds inference results)      │   │
│  │  ├─ mlflow (experiment tracking database)            │   │
│  │  └─ airflow (training DAGs database)                 │   │
│  │                                                       │   │
│  │  📊 MLflow Server (Port 5500)                       │   │
│  │  └─ Tracks model training experiments               │   │
│  │                                                       │   │
│  │  🔄 Airflow (Port 8080)                             │   │
│  │  ├─ Scheduler: Runs training DAGs                   │   │
│  │  ├─ Webserver: DAG UI                               │   │
│  │  └─ Workers: Execute training jobs                  │   │
│  │                                                       │   │
│  │  💾 Redis (Port 6379)                               │   │
│  │  └─ Celery message broker for workers               │   │
│  │                                                       │   │
│  │  🤖 Inference API (Port 8000)                       │   │
│  │  ├─ Loads fraud detection model                     │   │
│  │  ├─ Scores new transactions                         │   │
│  │  └─ Broadcasts predictions                          │   │
│  │                                                       │   │
│  │  🎨 FraudGuard Dashboard (Port 5000) ⭐ MAIN UI    │   │
│  │  ├─ Shows fraud detection results                   │   │
│  │  ├─ Updates every 5 seconds (polling)               │   │
│  │  ├─ Live updates (SSE streaming)                    │   │
│  │  └─ Real-time fraud trends                          │   │
│  │                                                       │   │
│  │  📦 MinIO (Port 9001)                               │   │
│  │  └─ S3-compatible storage for models                │   │
│  │                                                       │   │
│  │  👀 Flower (Port 5555)                              │   │
│  │  └─ Monitor Celery workers                          │   │
│  │                                                       │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

---

## The Data Flow (What Happens Every Minute)

```
T+0s   Producer generates 100 realistic transactions
       ↓
T+1s   Inserts into PostgreSQL transactions_db
       ↓
T+2s   Inference API detects new unscored transactions
       ↓
T+3s   Loads XGBoost model and scores all 100 txns
       ↓
T+4s   Calculates fraud_probability (0-1) and fraud_prediction (0/1)
       ↓
T+4.5s Saves predictions to fraud_predictions table
       ↓
T+5s   Dashboard polls /api/data endpoint
       ↓
T+5.5s Maps prediction columns to UI format
       ↓
T+6s   Dashboard updates: shows new transactions
       ↓
T+10s  ✅ Full cycle complete
       Then repeat every 60 seconds
```

---

## Command Reference (Copy-Paste)

### 🟢 START Everything

```powershell
# Terminal 1 - Database + Docker Stack
cd src
docker-compose up -d postgres
psql -h 127.0.0.1 -U postgres -f init-multiple-dbs.sh
docker-compose up -d

# Terminal 2 - Producer
cd ..
python producer/main.py

# Browser - Dashboard
http://localhost:5000
```

### 🔴 STOP Everything

```powershell
# Terminal 1
cd src
docker-compose down

# Terminal 2
Ctrl+C  (stop producer)
```

### 🟡 PAUSE (Keep Data)

```powershell
# Terminal 1
cd src
docker-compose stop

# Terminal 2
Ctrl+C

# Resume later:
docker-compose start
# And restart producer
```

### 🔵 MONITOR (Live Stats)

```powershell
# Watch fraud rate updating
curl http://localhost:8000/inference/stats

# Watch dashboard
http://localhost:5000

# Watch producer logs
# (in the terminal where it's running)

# Watch inference logs
docker-compose logs -f inference

# Watch airflow DAGs
http://localhost:8080
# Login: airflow / airflow
```

---

## Verification (Is It Working?)

### ✅ Check 1: Producer Running
```powershell
ps aux | grep main.py | grep producer
# Should show running process
```

### ✅ Check 2: Databases Ready
```powershell
psql -h 127.0.0.1 -U postgres -c "\l"
# Should show: transactions_db, mlflow, airflow
```

### ✅ Check 3: All Services Healthy
```powershell
cd src
docker-compose ps
# All should show "running"
```

### ✅ Check 4: Transactions Generated
```powershell
psql -h 127.0.0.1 -U postgres -d transactions_db -c \
  "SELECT count(*) FROM transactions;"
# Should show increasing number (1000, 2000, 3000...)
```

### ✅ Check 5: Predictions Scored
```powershell
curl http://localhost:8000/inference/stats
# Should show: "fraud_rate": 8.5 (or similar)
```

### ✅ Check 6: Dashboard Updating
```powershell
http://localhost:5000
# Should show:
# - Total Transactions: Increasing
# - Fraud Rate: ~8-10%
# - Transaction table: Shows latest
# - Charts: Show real trends (not flat)
```

### ✅ Check 7: Live Results
```powershell
curl http://localhost:5000/api/data | grep fraud_rate
# Should show fraud_rate in response
```

---

## Access Everything

| What | Where | What You'll See |
|------|-------|-----------------|
| **Dashboard** ⭐ | http://localhost:5000 | Fraud detection UI, transactions, trends |
| **Inference API** | http://localhost:8000 | JSON predictions |
| **MLflow** | http://localhost:5500 | Model experiment tracking |
| **Airflow DAGs** | http://localhost:8080 | Training pipeline (login: airflow/airflow) |
| **Celery Monitor** | http://localhost:5555 | Worker monitoring |
| **S3 Storage** | http://localhost:9001 | Models & artifacts (login: minioadmin/minioadmin) |

---

## Troubleshooting (Quick Fixes)

| Problem | Fix |
|---------|-----|
| "Connection refused 127.0.0.1:5432" | Wait 30 seconds for postgres to start, then: `psql -h 127.0.0.1 -U postgres -d postgres -c "SELECT 1;"` |
| Producer won't start | Check .env exists: `copy .env.example .env` |
| Dashboard shows "—" | Check inference running: `curl http://localhost:8000/health` |
| No transactions in table | Check producer still running (should see logs) |
| Services not starting | Check ports free: `netstat -an \| findstr :5000` |
| "Port already in use" | Kill the process: `netstat -ano \| findstr :5000`, then `taskkill /PID <pid>` |

---

## Performance Metrics (What to Expect)

| Metric | Target | What You'll See |
|--------|--------|-----------------|
| Transaction Generation | 100 txns/60s | Producer logs show ~100 txns inserted |
| Fraud Detection Rate | 8-10% | Dashboard shows fraud_rate: 8.5 |
| Scoring Latency | <100ms | Inference completes in <1s |
| Dashboard Update | 5s | Page refreshes every 5 seconds |
| SSE Live Update | <100ms | Instant notification when predictions arrive |

---

## One-Line Quick Start (Copy This!)

```powershell
# For maximum laziness, run these 3 commands in parallel:
cd src; docker-compose up -d postgres; sleep 10; psql -h 127.0.0.1 -U postgres -f init-multiple-dbs.sh; docker-compose up -d
# Then:
cd ..; python producer/main.py
# Then open browser:
# http://localhost:5000
```

---

## What Happens When You Open http://localhost:5000

```
BEFORE (Without This Setup):
❌ Dashboard shows "—" (no data)
❌ Charts are empty
❌ No fraud detection results
❌ Stale data

AFTER (With This Setup Running):
✅ Total Transactions: 1,000 (and counting)
✅ Fraud Rate: 8.5%
✅ Approval Rate: 91.5%
✅ Fraud Detections: 85
✅ Latest Transactions Table: Shows real predictions
✅ Charts: Show real fraud trends
✅ Updates: Every 5 seconds + live via SSE
✅ Model Health: Shows metrics from MLflow
```

---

## Architecture Summary (For Your Boss)

We have **3 independent layers** that all work together:

1. **Data Generation** (Producer)
   - Runs on your machine
   - Generates realistic transaction data
   - Writes to PostgreSQL

2. **Fraud Detection** (Inference API + Model)
   - Loads pre-trained XGBoost model
   - Scores transactions in real-time
   - Saves predictions

3. **Visualization** (FraudGuard Dashboard)
   - Displays fraud detection results
   - Shows real-time trends
   - Updates live (SSE + polling)

All connected via **PostgreSQL** for data flow.

---

## That's It! 🎉

You now have:
✅ Producer generating data continuously
✅ Inference API scoring transactions in real-time
✅ FraudGuard dashboard showing live fraud detection
✅ Training pipeline ready (Airflow)
✅ Experiment tracking ready (MLflow)

**A complete, production-grade fraud detection system running live!**

---

## Questions?

- **Producer won't start**: Check `python producer/main.py` manually for errors
- **Dashboard empty**: Check `curl http://localhost:5000/api/data`
- **Model not loaded**: Check `curl http://localhost:8000/health`
- **Database won't connect**: Check `psql -h 127.0.0.1 -U postgres -c "SELECT 1;"`

**Good luck, boss!** 🚀
