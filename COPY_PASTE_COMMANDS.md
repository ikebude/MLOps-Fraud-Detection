# 📝 Copy-Paste Commands - Full Live Solution

## Prerequisites (Do These Once)

### 1. Check Requirements
```powershell
# Windows - Check Docker
docker --version
# Should show: Docker version 20.10+

docker-compose --version
# Should show: docker-compose version 1.29+

python --version
# Should show: Python 3.11+
```

### 2. Activate Python Environment
```powershell
# Navigate to repo
cd c:\Users\3Consult\Documents\AI Solution Projects\MLOps_Fraud_Detection

# Activate virtual environment
.\env\Scripts\Activate.ps1

# Verify
python --version
pip list | grep psycopg2
```

### 3. Create .env File (If Not Exists)
```powershell
# Copy template
copy .env.example .env

# Verify it has these keys:
type .env | findstr DB_
# Should show DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD
```

---

## 🚀 START THE FULL LIVE SOLUTION

### Step 1️⃣: Terminal 1 - Initialize & Start Docker Stack

```powershell
# Navigate to docker-compose directory
cd c:\Users\3Consult\Documents\AI Solution Projects\MLOps_Fraud_Detection\src

# First time ONLY: Initialize databases
docker-compose up -d postgres
Start-Sleep -Seconds 10
psql -h 127.0.0.1 -U postgres -f init-multiple-dbs.sh

# Verify databases created
psql -h 127.0.0.1 -U postgres -c "\l"
# Should show: transactions_db, mlflow, airflow

# Now start all services
docker-compose up -d

# Wait for services to be healthy (30-45 seconds)
Start-Sleep -Seconds 45
docker-compose ps
# All should show "running"
```

**Expected Output:**
```
Creating postgres ... done
Creating redis ... done
Creating mlflow-server ... done
Creating airflow-scheduler ... done
Creating airflow-worker ... done
Creating inference ... done
Creating fraudguard ... done
Creating minio ... done
Creating flower ... done
```

---

### Step 2️⃣: Terminal 2 - Start Producer

```powershell
# Navigate to repo root
cd c:\Users\3Consult\Documents\AI Solution Projects\MLOps_Fraud_Detection

# Make sure environment is activated
.\env\Scripts\Activate.ps1

# Check producer script exists
Test-Path .\scripts\start-producer.ps1

# Option A: Using the startup script (RECOMMENDED)
.\scripts\start-producer.ps1

# Option B: Or run manually
python producer/main.py
```

**Expected Output:**
```
[INFO] DatabaseManager: Initializing with min=2, max=10 connections
[INFO] Producer: Connecting to 127.0.0.1:5432 transactions_db
[INFO] Producer: Starting transaction generation
[INFO] Batch 1: Inserted 100 transactions in 1.2 seconds
[INFO] Stats [60s]: total=100, fraud_detections=8, fraud_rate=8.0%
[INFO] Batch 2: Inserted 100 transactions in 1.1 seconds
[INFO] Stats [120s]: total=200, fraud_detections=17, fraud_rate=8.5%
```

**Keep this terminal running!** (Don't close it)

---

### Step 3️⃣: Browser - Open Dashboard

```
Open in browser: http://localhost:5000
```

**You Should See:**
```
FraudGuard Dashboard
├─ Total Transactions: 200
├─ Fraud Rate: 8.5%
├─ Approval Rate: 91.5%
├─ Fraud Detections: 17
├─ Transaction Table:
│  ├─ Time: 2026-01-31T15:30:45
│  ├─ ID: TXN_ABC123
│  ├─ User: USER_456
│  ├─ Amount: ₦12,500.00
│  ├─ Risk: 42 (orange badge)
│  └─ Status: Flagged
└─ Charts: Show real fraud trends
```

---

## ✅ Verify Everything is Working

```powershell
# Test 1: Check all Docker services running
docker-compose ps

# Test 2: Check PostgreSQL
psql -h 127.0.0.1 -U postgres -d transactions_db -c "SELECT count(*) FROM transactions;"
# Should show: increasing number (100, 200, 300...)

# Test 3: Check transactions being generated
psql -h 127.0.0.1 -U postgres -d transactions_db -c \
  "SELECT count(*) FROM transactions WHERE timestamp > now() - interval '60 seconds';"
# Should show: ~100 (new transactions in last minute)

# Test 4: Check inference API
curl http://localhost:8000/health
# Should show: {"status": "healthy", "model_loaded": true}

# Test 5: Check predictions
curl http://localhost:8000/inference/stats
# Should show: fraud_rate increasing

# Test 6: Check dashboard
curl http://localhost:5000/api/data | select -ExpandProperty metrics
# Should show: fraud_detections, fraud_rate increasing

# Test 7: Open dashboard
start "http://localhost:5000"
```

---

## 🔍 Monitor the Solution

### Watch Producer Generating Data
```powershell
# In producer terminal, you'll see:
[INFO] Stats [180s]: total=300, fraud_detections=25, fraud_rate=8.3%
[INFO] Stats [240s]: total=400, fraud_detections=34, fraud_rate=8.5%
# Numbers increase every 60 seconds
```

### Watch Inference Scoring
```powershell
# Check inference is scoring
while ($true) {
  $stats = curl -s http://localhost:8000/inference/stats | ConvertFrom-Json
  Write-Host "Fraud Rate: $($stats.fraud_rate)% | Total: $($stats.total_records)"
  Start-Sleep -Seconds 10
}
```

### Watch Dashboard Updating
```powershell
# Check dashboard updates
while ($true) {
  $data = curl -s http://localhost:5000/api/data | ConvertFrom-Json
  Write-Host "Transactions: $($data.metrics.total_transactions) | Fraud Rate: $($data.metrics.fraud_rate)%"
  Start-Sleep -Seconds 5
}
```

### Watch Docker Logs
```powershell
# Inference API logs
docker-compose logs -f inference

# Dashboard logs
docker-compose logs -f fraudguard

# All logs
docker-compose logs -f
```

---

## 🛑 STOP Everything

### Graceful Shutdown
```powershell
# Terminal 2: Stop producer
# Press Ctrl+C in the producer terminal
# You'll see: "Shutting down gracefully..."

# Terminal 1: Stop docker stack
cd c:\Users\3Consult\Documents\AI Solution Projects\MLOps_Fraud_Detection\src
docker-compose down

# Verify stopped
docker-compose ps
# Should show: all containers exited
```

### Cleanup (Warning: Deletes Database)
```powershell
# If you want to remove database and start fresh
cd c:\Users\3Consult\Documents\AI Solution Projects\MLOps_Fraud_Detection\src
docker-compose down -v

# Note: This deletes all transaction and prediction data!
```

---

## ⏸️ PAUSE & RESUME (Keep Data)

### Pause Everything
```powershell
# Terminal 2: Stop producer
# Ctrl+C

# Terminal 1: Stop (don't remove) containers
cd src
docker-compose stop

# Verify paused
docker-compose ps
# Should show: all containers stopped but still exist
```

### Resume Later
```powershell
# Terminal 1: Start containers again
cd src
docker-compose start

# Wait for services
Start-Sleep -Seconds 30

# Terminal 2: Restart producer
python producer/main.py
```

---

## 🔧 Troubleshooting Commands

### Issue: PostgreSQL won't start
```powershell
# Check if port 5432 is in use
netstat -ano | findstr :5432

# If occupied, kill the process
taskkill /PID <pid_from_above> /F

# Then restart
docker-compose restart postgres
```

### Issue: Producer can't connect
```powershell
# Test database connection
psql -h 127.0.0.1 -U postgres -d postgres -c "SELECT 1;"

# If fails, check postgres is running
docker-compose ps postgres

# Check credentials in .env
type .env | findstr DB_

# If needed, recreate databases
psql -h 127.0.0.1 -U postgres -f init-multiple-dbs.sh
```

### Issue: Inference API not scoring
```powershell
# Check inference is running
docker-compose ps inference

# Check model loaded
curl http://localhost:8000/health

# Check logs
docker-compose logs inference | tail -50

# If needed, restart
docker-compose restart inference
```

### Issue: Dashboard shows no data
```powershell
# Check dashboard can reach inference API
curl http://localhost:5000/api/data

# If error, restart both
docker-compose restart inference fraudguard

# Check in browser again
start "http://localhost:5000"
```

### Issue: Port already in use
```powershell
# Find what's using port 5000
netstat -ano | findstr :5000

# Kill it
taskkill /PID <pid> /F

# Or start docker on different port
# Edit docker-compose.yml and change port mapping
```

---

## 📊 Access All Services

### Main Dashboard (What You Need)
```powershell
start "http://localhost:5000"
```

### Other Services (Optional)
```powershell
# Inference API
start "http://localhost:8000/health"

# MLflow (Model experiments)
start "http://localhost:5500"

# Airflow (Training pipeline)
start "http://localhost:8080"
# Login: airflow / airflow

# Flower (Worker monitoring)
start "http://localhost:5555"

# MinIO (S3 storage)
start "http://localhost:9001"
# Login: minioadmin / minioadmin
```

---

## 📈 Check Progress

### Quick Status Check
```powershell
# One-liner to check everything
Write-Host "Docker Services:" ; docker-compose ps ; `
Write-Host "`nProducer Running:" ; ps aux | grep "producer/main.py" | grep -v grep ; `
Write-Host "`nDatabase Size:" ; `
psql -h 127.0.0.1 -U postgres -d transactions_db -c "SELECT count(*) FROM transactions;" ; `
Write-Host "`nFraud Rate:" ; `
curl -s http://localhost:8000/inference/stats | jq '.fraud_rate'
```

### Watch Real-Time Updates
```powershell
# Watch transactions increasing
do {
  $count = psql -h 127.0.0.1 -U postgres -d transactions_db -t -c "SELECT count(*) FROM transactions;"
  $fraud = psql -h 127.0.0.1 -U postgres -d transactions_db -t -c "SELECT count(*) FROM transactions WHERE is_fraud = true;"
  Write-Host "$(Get-Date -Format 'HH:mm:ss') | Total: $count | Fraud: $fraud"
  Start-Sleep -Seconds 10
} while ($true)
```

---

## 🎓 What Each Command Does

| Command | What It Does | Where to Run |
|---------|-------------|-------------|
| `docker-compose up -d postgres` | Start PostgreSQL | Terminal 1, src folder |
| `psql ... -f init-multiple-dbs.sh` | Create databases and users | Terminal 1 (any folder with init script) |
| `docker-compose up -d` | Start all Docker services | Terminal 1, src folder |
| `python producer/main.py` | Generate transaction data | Terminal 2, repo root |
| `curl http://localhost:8000/health` | Check inference API | Any terminal |
| `curl http://localhost:5000/api/data` | Get dashboard data | Any terminal |
| `docker-compose ps` | Check service status | Any terminal, src folder |
| `docker-compose logs -f <service>` | Watch service logs | Any terminal, src folder |

---

## ✨ Expected Behavior

### First 30 Seconds
```
- Docker services starting
- PostgreSQL initializing
- MLflow, Airflow, Inference loading
- FraudGuard starting
```

### After 30-45 Seconds
```
- All services "running" (docker-compose ps)
- Dashboard accessible (http://localhost:5000)
- Inference API healthy (curl localhost:8000/health)
```

### After Producer Starts (T+60s)
```
- 100 transactions generated
- Inference scores them
- Dashboard shows: Total=100, Fraud Rate~8.5%
```

### Continuing (Every 60 Seconds)
```
- Producer generates another 100
- Inference scores them
- Dashboard updates: Total=200, Total=300...
- Charts show real fraud trends
```

---

## 🎯 Success Indicators

```
✅ All 9 docker-compose services running
✅ PostgreSQL has 3 databases (transactions_db, mlflow, airflow)
✅ Producer terminal shows "Stats" every 60 seconds
✅ http://localhost:5000 loads without errors
✅ Dashboard shows increasing transaction count
✅ Fraud Rate displays ~8-10%
✅ Transaction table shows real data
✅ Charts show real trends (not flat lines)
✅ Everything updates live
```

**Once all ✅, you have a fully operational fraud detection system!**

---

## 🚀 That's It!

Copy the commands from **Step 1 and Step 2** above and you'll have the complete live solution running in under 2 minutes.

**Boss, you're ready to go!** 🎉
