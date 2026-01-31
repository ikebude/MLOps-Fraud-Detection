# 🚀 Complete Live Solution - Full Startup Guide

## The Complete Architecture

```
YOUR MACHINE
├─ Producer (Standalone or Docker)
│  ├─ Generates transactions continuously
│  └─ Writes to PostgreSQL
│
└─ Docker Compose Stack (Full)
   ├─ PostgreSQL (transactions_db, mlflow, airflow)
   ├─ MLflow Server (experiment tracking)
   ├─ Airflow (training orchestration)
   ├─ Redis (Celery broker)
   ├─ Inference API (fraud scoring)
   ├─ FraudGuard Dashboard (web UI)
   ├─ MinIO (S3 storage)
   └─ Flower (Celery monitoring)
```

---

## 🎯 Option 1: RECOMMENDED - Standalone Producer + Docker Compose Stack

This is the best option for development and testing. Producer runs independently, everything else in Docker.

### Prerequisites
```bash
# 1. Docker & Docker Compose installed
docker --version       # Docker 20.10+
docker-compose --version  # 1.29+

# 2. Python 3.11+ with virtual environment activated
python --version       # Python 3.11+
source env/bin/activate  # or .\env\Scripts\Activate.ps1 on Windows
```

### Step 1️⃣: Initialize PostgreSQL Database (One Time)

```bash
# Start PostgreSQL in docker-compose first
cd src
docker-compose up -d postgres

# Wait for it to be ready
sleep 10

# Initialize databases and users
psql -h 127.0.0.1 -U postgres -f init-multiple-dbs.sh

# Verify databases were created
psql -h 127.0.0.1 -U postgres -c "\l"
# Should see: transactions_db, mlflow, airflow

# Verify users were created
psql -h 127.0.0.1 -U postgres -c "\du"
# Should see: fraud_producer, fraud_inference, fraud_training, mlflow, airflow
```

### Step 2️⃣: Start the Full Docker Compose Stack

```bash
cd src

# Start all services (in background)
docker-compose up -d

# Wait for services to be healthy
docker-compose ps
# All should show "running"

# Check specific services
docker-compose logs postgres    # Database
docker-compose logs mlflow      # MLflow server
docker-compose logs airflow-scheduler  # Airflow scheduler
```

### Step 3️⃣: Start Producer (Standalone on Host)

**Option A: Using Start Script (PowerShell - Windows)**
```powershell
cd c:\Users\3Consult\Documents\AI Solution Projects\MLOps_Fraud_Detection

# PowerShell
.\scripts\start-producer.ps1

# Expected output:
# Checking Python environment...
# Starting producer with fraud_producer user
# Connecting to 127.0.0.1:5432 transactions_db
# Generating transactions... [TXN_ABC123, TXN_ABC124, ...]
```

**Option B: Using Start Script (Bash - Mac/Linux)**
```bash
cd ~/MLOps_Fraud_Detection

bash scripts/start-producer.sh

# Expected output:
# Starting producer service...
# Connected to database
# Producer ready on port 5000
```

**Option C: Manual Python Execution**
```bash
# From the repo root
cd c:\Users\3Consult\Documents\AI Solution Projects\MLOps_Fraud_Detection

# Create .env file if not exists
cp .env.example .env

# Start producer
python producer/main.py

# Expected output:
# [INFO] DatabaseManager: Initializing with min=2, max=10 connections
# [INFO] Producer: Connecting to transactions_db
# [INFO] Producer: Generating batch of 100 transactions
# [INFO] Stats every 60s: total_txns=500, fraud_rate=8.5%
```

### Step 4️⃣: Access the Services

Once everything is running:

```bash
# 🌐 FraudGuard Dashboard (THE MAIN UI)
open http://localhost:5000
# Shows live fraud detection with real inference results

# 📊 MLflow (Experiment tracking)
open http://localhost:5500
# Track model training runs

# 🔄 Airflow (Training pipeline)
open http://localhost:8080
# Monitor training DAGs
# Default credentials: airflow / airflow

# 🍃 Flower (Celery monitoring)
open http://localhost:5555
# Monitor Celery workers

# 📦 MinIO (Object storage)
open http://localhost:9001
# S3-compatible storage
# Default credentials: minioadmin / minioadmin
```

### Step 5️⃣: Verify Everything is Working

```bash
# Check inference API is scoring transactions
curl http://localhost:8000/inference/stats

# Expected response:
# {
#   "total_records": 5000,
#   "fraud_detections": 425,
#   "fraud_rate": 8.5,
#   "status": "success"
# }

# Check dashboard is reading from inference
curl http://localhost:5000/api/data | head -50

# Check producer is connected
ps aux | grep main.py  # Should see producer process
```

---

## 🎯 Option 2: Everything in Docker (Alternative)

If you want producer inside docker-compose as well:

### Step 1: Create Producer Service in docker-compose.yml

```yaml
producer:
  build: ./producer
  container_name: fraud-producer
  environment:
    DB_HOST: postgres
    DB_PORT: 5432
    DB_NAME: transactions_db
    DB_USER: fraud_producer
    DB_PASSWORD: producer_password
    PRODUCER_BATCH_SIZE: 100
    PRODUCER_INTERVAL: 60
  depends_on:
    postgres:
      condition: service_healthy
  networks:
    - fraud-detection
```

### Step 2: Build and Start

```bash
cd src

# Build images
docker-compose build

# Start everything
docker-compose up -d

# Check producer logs
docker-compose logs -f producer
```

---

## 📋 Complete Service Startup Sequence (Recommended)

For **Option 1** (Standalone Producer + Docker Stack), here's the complete sequence:

### Terminal 1: Docker Services
```bash
cd src
docker-compose up -d
# Output:
# Creating fraud-detection-postgres ... done
# Creating fraud-detection-redis ... done
# Creating fraud-detection-mlflow ... done
# Creating fraud-detection-airflow-scheduler ... done
# Creating fraud-detection-inference ... done
# Creating fraud-detection-fraudguard ... done
# Creating fraud-detection-airflow-webserver ... done
```

### Terminal 2: Producer (Host)
```bash
cd c:\Users\3Consult\Documents\AI Solution Projects\MLOps_Fraud_Detection
.\scripts\start-producer.ps1

# Or on Mac/Linux:
bash scripts/start-producer.sh

# Output:
# Producer starting...
# Connected to transactions_db
# Generating transactions...
```

### Terminal 3: Monitor (Optional)
```bash
# Watch producer stats
while true; do
  curl -s http://localhost:8000/inference/stats | jq '.fraud_rate'
  sleep 5
done

# Watch inference logs
docker-compose logs -f inference
```

---

## 🔍 Verification Checklist

### ✅ Phase 1: Database Ready
```bash
# Check postgres is running
docker-compose ps postgres
# Status: healthy

# Check databases exist
psql -h 127.0.0.1 -U postgres -c "\l"
# transactions_db, mlflow, airflow should exist

# Check users exist
psql -h 127.0.0.1 -U postgres -c "\du"
# fraud_producer, fraud_inference, fraud_training
```

### ✅ Phase 2: Docker Stack Ready
```bash
# All services running
docker-compose ps

# Check service health
curl http://localhost:8000/health          # Inference API
curl http://localhost:5000/api/health      # Dashboard
curl http://localhost:5500/health          # MLflow
curl http://localhost:8080/health          # Airflow
```

### ✅ Phase 3: Producer Generating Data
```bash
# Check producer is running
ps aux | grep main.py | grep producer

# Check transactions in database
psql -h 127.0.0.1 -U postgres -d transactions_db -c \
  "SELECT count(*) FROM transactions;"
# Should be increasing (e.g., 1000, 2000, 3000...)

# Check fraud stats
curl http://localhost:8000/inference/stats
# Should show: total_records increasing, fraud_rate ~8-10%
```

### ✅ Phase 4: Inference API Scoring
```bash
# Run manual inference
curl -X POST http://localhost:8000/inference/run \
  -H "Content-Type: application/json" \
  -d '{"max_records": 100}'

# Expected response:
# {
#   "status": "success",
#   "total_records": 100,
#   "fraud_detections": 8,
#   "fraud_rate": 8.0
# }

# Check predictions saved
psql -h 127.0.0.1 -U postgres -d transactions_db -c \
  "SELECT count(*) FROM fraud_predictions;"
# Should show predictions
```

### ✅ Phase 5: Dashboard Live
```bash
# Check dashboard getting data
curl http://localhost:5000/api/data | jq '.transactions | length'
# Should show transaction count (e.g., 50, 100, 200)

# Open in browser
open http://localhost:5000

# Should show:
# - Total Transactions (increasing)
# - Fraud Rate (e.g., 8.5%)
# - Latest transaction table
# - Real fraud trend charts
```

---

## 🛑 Stop Everything

### Stop Producer
```bash
# Press Ctrl+C in producer terminal
# Or kill the process:
kill $(ps aux | grep "producer/main.py" | grep -v grep | awk '{print $2}')
```

### Stop Docker Stack
```bash
cd src
docker-compose down

# Remove volumes too (warning: deletes database)
docker-compose down -v
```

---

## 🔄 Restart Everything

```bash
# Stop everything
cd src
docker-compose down
killall python  # Kill producer

# Start fresh
sleep 2
docker-compose up -d
sleep 10
python ../producer/main.py &

# Verify
curl http://localhost:5000
```

---

## 📊 Expected Output Timeline

### T+0s: Services Starting
```
Starting Docker services...
Starting producer...
```

### T+10s: PostgreSQL Ready
```
PostgreSQL listening on :5432
Database schema initialized
User roles created
```

### T+30s: Infrastructure Ready
```
MLflow server running on :5500
Airflow scheduler ready
Inference API ready on :8000
FraudGuard dashboard ready on :5000
```

### T+60s: Producer First Batch
```
[Producer] Generated 100 transactions
[Inference] Scored 100 transactions
[Dashboard] Updated with 100 results
```

### T+120s+: Continuous Operation
```
[Producer] Generated 200 total transactions
[Inference] Fraud rate: 8.5%
[Dashboard] Live updates every 5 seconds
[MLflow] Ready for training runs
[Airflow] DAGs ready to execute
```

---

## 💻 Environment Variables Used

### For Producer (Host)
```env
DB_HOST=127.0.0.1
DB_PORT=5432
DB_NAME=transactions_db
DB_USER=fraud_producer
DB_PASSWORD=producer_password
PRODUCER_BATCH_SIZE=100
PRODUCER_INTERVAL=60
```

### For Docker Services
```env
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=airflow
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres123
MLFLOW_TRACKING_URI=http://mlflow-server:5500
INFERENCE_SERVICE_URL=http://inference:8000
```

---

## 🆘 Troubleshooting

### Producer Can't Connect to Database
```bash
# Check PostgreSQL is running
docker-compose ps postgres

# Check database is ready
psql -h 127.0.0.1 -U postgres -d transactions_db -c "SELECT 1;"

# Check .env file has correct credentials
cat .env | grep DB_

# Fix: Restart postgres
docker-compose restart postgres
```

### Dashboard Shows No Data
```bash
# Check inference API is running
curl http://localhost:8000/health

# Check producer is generating data
curl http://localhost:8000/inference/stats

# Check dashboard can reach inference API
curl http://localhost:5000/api/data

# Fix: Restart inference
docker-compose restart inference
docker-compose restart fraudguard
```

### Transactions Not Accumulating
```bash
# Check producer is running
ps aux | grep main.py

# Check transactions in database
psql -h 127.0.0.1 -U postgres -d transactions_db -c \
  "SELECT count(*) FROM transactions;"

# Check producer logs
# Look for errors in terminal where producer is running

# Fix: Restart producer
# Kill and re-run the start script
```

### Inference API Not Scoring
```bash
# Check inference has model
curl http://localhost:8000/health
# Should show: "model_loaded": true

# Check inference has data to score
curl http://localhost:8000/inference/stats

# Check manually run inference
curl -X POST http://localhost:8000/inference/run -d '{}'

# Check inference logs
docker-compose logs inference
```

---

## 📈 Scaling Beyond Development

### For Production, also run:
```bash
# Airflow Workers (parallel training)
docker-compose up -d celery-worker celery-worker2 celery-worker3

# Additional Inference Replicas
docker-compose up -d inference inference2

# Load Balancer (optional)
# nginx reverse proxy in front of inference instances
```

---

## 🎉 Success Indicators

You'll know everything is working when:

✅ **Producer Running**
- Terminal shows "Generating transactions..."
- New transactions appear every 60 seconds

✅ **Dashboard Updating**
- http://localhost:5000 shows transaction count increasing
- Fraud rate displays correctly (~8-10%)
- Transaction table updates every 5 seconds

✅ **Inference Scoring**
- http://localhost:8000/inference/stats shows cumulative predictions
- New predictions appear as producer generates data

✅ **Full Pipeline**
- Producer generates → Database stores → Inference scores → Dashboard displays
- Entire loop completes in <2 seconds

---

## 🔗 Quick Links

| Service | URL | Purpose |
|---------|-----|---------|
| **FraudGuard** | http://localhost:5000 | 🎯 Main fraud detection dashboard |
| **Inference API** | http://localhost:8000 | 🤖 Scoring API |
| **MLflow** | http://localhost:5500 | 📊 Experiment tracking |
| **Airflow** | http://localhost:8080 | 🔄 Training orchestration |
| **Flower** | http://localhost:5555 | 👀 Celery monitoring |
| **MinIO** | http://localhost:9001 | 📦 Object storage |

---

## 📝 One-Command Quick Start

For the impatient (Option 1 - Recommended):

```bash
# Terminal 1: Docker Stack
cd c:\Users\3Consult\Documents\AI Solution Projects\MLOps_Fraud_Detection\src
docker-compose up -d postgres && sleep 5 && psql -h 127.0.0.1 -U postgres -f init-multiple-dbs.sh && docker-compose up -d

# Terminal 2: Producer
cd c:\Users\3Consult\Documents\AI Solution Projects\MLOps_Fraud_Detection
python producer/main.py

# Terminal 3: Access Dashboard
start http://localhost:5000
```

That's it! You now have:
- 🔷 PostgreSQL with isolated databases
- 🤖 Producer generating 100 txns/min
- 🧠 Inference API scoring transactions
- 📊 FraudGuard dashboard showing live results
- 📈 MLflow tracking experiments
- 🔄 Airflow ready for training DAGs

**The complete fraud detection solution running live!** 🎉
