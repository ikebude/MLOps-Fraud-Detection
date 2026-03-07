# 🚀 MLOps Fraud Detection - COMPLETE PRE-FLIGHT CHECKLIST & STARTUP GUIDE

## 📋 EXECUTIVE SUMMARY

This is your **END-TO-END MLOps Fraud Detection System** with:
- **Airflow**: Model training orchestration (daily scheduled)
- **MLflow**: Model registry and experiment tracking
- **Inference Service**: Real-time fraud predictions
- **Moniguard Dashboard**: Premium UI for monitoring (UPGRADED ✨)
- **PostgreSQL**: Centralized database (3 databases: airflow, mlflow, transactions_db)
- **MinIO**: S3-compatible storage for MLflow artifacts
- **Producer**: Transaction data generator (OPTIONAL)

---

## 🎯 THE BIG PICTURE - HOW EVERYTHING ALIGNS

```
┌─────────────────────────────────────────────────────────────────────┐
│                         DATA FLOW DIAGRAM                            │
└─────────────────────────────────────────────────────────────────────┘

1. TRAINING PIPELINE (Daily @ 2 AM)
   ┌──────────────┐
   │ Fraud API    │ (External data source)
   └──────┬───────┘
          │ fetch
          ▼
   ┌──────────────┐
   │ Airflow DAG  │ (fraud_detection_training)
   │ - Fetch data │
   │ - Engineer   │
   │ - Train XGB  │
   └──────┬───────┘
          │ log model
          ▼
   ┌──────────────┐
   │ MLflow       │ (Model Registry)
   │ Version: 8   │
   │ Accuracy: 98%│
   └──────┬───────┘
          │ save .pkl
          ▼
   ┌──────────────┐
   │ /app/models/ │ (Shared volume)
   └──────────────┘


2. INFERENCE PIPELINE (Continuous)
   ┌──────────────┐
   │ Transactions │ (Producer writes OR manual insert)
   │ Table        │
   └──────┬───────┘
          │ fetch unprocessed
          ▼
   ┌──────────────┐
   │ Inference    │ (Loads model from MLflow/local)
   │ Service      │
   │ Port: 8000   │
   └──────┬───────┘
          │ save predictions
          ▼
   ┌──────────────┐
   │ Fraud        │ (Predictions table)
   │ Predictions  │
   └──────┬───────┘
          │ JOIN
          ▼
   ┌──────────────┐
   │ Moniguard   │ (Dashboard)
   │ Port: 5000   │
   │ - Live Feed  │
   │ - Metrics    │
   │ - Charts     │
   └──────────────┘


3. DATABASE ARCHITECTURE
   ┌─────────────────────────────────────────┐
   │ PostgreSQL (postgres:5432)              │
   ├─────────────────────────────────────────┤
   │ Database 1: airflow                     │
   │   - User: airflow / airflow             │
   │   - Purpose: Airflow metadata           │
   ├─────────────────────────────────────────┤
   │ Database 2: mlflow                      │
   │   - User: mlflow / mlflow               │
   │   - Purpose: MLflow experiments         │
   ├─────────────────────────────────────────┤
   │ Database 3: transactions_db             │
   │   - Tables:                             │
   │     • transactions (producer writes)    │
   │     • fraud_predictions (inference)     │
   │   - Users:                              │
   │     • fraud_producer (write)            │
   │     • fraud_inference (read + write)    │
   │     • fraud_training (read only)        │
   └─────────────────────────────────────────┘
```

---

## ✅ PRE-FLIGHT CHECKLIST

### 1. **System Requirements**
- [ ] **Docker Desktop** installed and running
  - Windows: Docker Desktop 4.0+
  - Minimum 8GB RAM allocated to Docker
  - 20GB free disk space
- [ ] **PowerShell** (Windows) or **Bash** (Linux/Mac)
- [ ] **Git** installed
- [ ] Ports available: 5000, 5432, 5500, 8000, 8080, 9000, 9001

### 2. **Repository Setup**
- [ ] Clone repository: `git clone <repo>`
- [ ] Navigate to root: `cd MLOps_Fraud_Detection`
- [ ] Verify `.env` file exists in root directory
- [ ] Verify `src/.env` is a symlink or copy of root `.env`

### 3. **Configuration Files**
- [ ] `.env` - Environment variables (database credentials, URLs)
- [ ] `src/config.yaml` - Model and API configuration
- [ ] `src/init-multiple-dbs.sh` - Database initialization script
- [ ] `src/docker-compose.yml` - Service orchestration

### 4. **Critical Environment Variables** (in `.env`)
```bash
# PostgreSQL
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_TRANSACTIONS_DB=transactions_db
POSTGRES_TRANSACTIONS_USER=fraud_producer
POSTGRES_TRANSACTIONS_PASSWORD=producer_password

# MLflow
MLFLOW_TRACKING_URI=http://mlflow-server:5500
MLFLOW_REGISTERED_MODEL=fraud_detection_model

# Inference
INFERENCE_SERVICE_URL=http://inference:8000
INFERENCE_PORT=8000

# Moniguard
FLASK_PORT=5000
FLASK_DEBUG=False

# MinIO (S3 storage)
MINIO_USERNAME=minioadmin
MINIO_PASSWORD=minioadmin
AWS_ACCESS_KEY_ID=minioadmin
AWS_SECRET_ACCESS_KEY=minioadmin
```

---

## 🚀 STARTUP SEQUENCE (STEP-BY-STEP)

### **PHASE 1: Build Images** (First time only, ~10-15 minutes)

```powershell
# Navigate to src directory
cd src

# Build all Docker images
docker compose build

# Expected output:
# ✓ Building fraud-detection-airflow
# ✓ Building fraud-detection-mlflow
# ✓ Building fraud-detection-inference
# ✓ Building fraud-detection-Moniguard
```

**What happens**:
- Airflow image: Installs Python dependencies, copies DAGs and plugins
- MLflow image: Sets up tracking server
- Inference image: Installs scikit-learn, xgboost, psycopg2
- Moniguard image: Installs Flask, requests, psycopg2

---

### **PHASE 2: Initialize Database** (First time only, ~2 minutes)

```powershell
# Start PostgreSQL and initialize databases
docker compose up -d postgres

# Wait 30 seconds for initialization
Start-Sleep -Seconds 30

# Verify databases were created
docker compose exec postgres psql -U airflow -d airflow -c "\l"

# Expected output:
# airflow          | airflow  | ...
# mlflow           | mlflow   | ...
# transactions_db  | airflow  | ...
```

**What happens** (via `init-multiple-dbs.sh`):
1. Creates 3 databases: `airflow`, `mlflow`, `transactions_db`
2. Creates users: `fraud_producer`, `fraud_inference`, `fraud_training`, `mlflow`
3. Creates tables:
   - `transactions` (33 columns: transaction_id, vendor_id, location, amount, is_fraud, etc.)
   - `fraud_predictions` (12 columns: transaction_id, fraud_probability, fraud_prediction, actual_fraud, etc.)
4. Sets up indexes for performance
5. Grants permissions (producer = write, inference = read+write predictions, training = read-only)

---

### **PHASE 3: Start Core Services** (~3 minutes)

```powershell
# Start MinIO (S3 storage for MLflow)
docker compose up -d minio mc

# Wait for MinIO to create bucket
Start-Sleep -Seconds 20

# Start MLflow
docker compose up -d mlflow-server

# Wait for MLflow to be healthy
Start-Sleep -Seconds 30

# Verify MLflow is running
curl http://localhost:5500/health
```

**What happens**:
- MinIO creates `mlflow` bucket for model artifacts
- MLflow connects to PostgreSQL (`mlflow` database) and MinIO
- MLflow is now ready to track experiments

---

### **PHASE 4: Start Airflow** (~5 minutes)

```powershell
# Initialize Airflow database (first time only)
docker compose up airflow-init

# Start Airflow services
docker compose up -d airflow-webserver airflow-scheduler airflow-worker airflow-triggerer redis

# Wait for Airflow to be ready
Start-Sleep -Seconds 120

# Verify Airflow is running
curl http://localhost:8080/health
```

**What happens**:
- `airflow-init`: Creates admin user (airflow/airflow), migrates database
- `airflow-scheduler`: Loads DAGs from `/opt/airflow/dags`
- `airflow-worker`: Celery worker for task execution
- `airflow-webserver`: Web UI on port 8080
- DAG `fraud_detection_training` is now visible in UI

---

### **PHASE 5: Start Inference Service** (~1 minute)

```powershell
# Start inference service
docker compose up -d inference

# Wait for service to be ready
Start-Sleep -Seconds 30

# Verify inference is running
curl http://localhost:8000/health
```

**What happens**:
- Inference service starts
- Attempts to load model from MLflow (`models:/fraud_detection_model/latest`)
- If no model in MLflow, looks for `/app/models/fraud_detection_model.pkl`
- Connects to `transactions_db` database
- Ready to process transactions

---

### **PHASE 6: Start Moniguard Dashboard** (~30 seconds)

```powershell
# Start Moniguard
docker compose up -d Moniguard

# Wait for service to be ready
Start-Sleep -Seconds 20

# Verify Moniguard is running
curl http://localhost:5000/api/health
```

**What happens**:
- Moniguard Flask app starts
- Connects to:
  - PostgreSQL (`transactions_db`) for direct queries
  - Inference Service (http://inference:8000) for API calls
  - MLflow (http://mlflow-server:5500) for model health
- Dashboard is now accessible at http://localhost:5000

---

### **PHASE 7: (OPTIONAL) Start Producer** 

```powershell
# Start transaction producer
docker compose --profile producer up -d producer

# Verify producer is running
docker compose logs -f producer
```

**What happens**:
- Producer generates synthetic transactions
- Writes to `transactions` table every 0.6 seconds (configurable)
- Inference service picks up new transactions automatically

**NOTE**: Producer is OPTIONAL. You can manually insert transactions or use existing data.

---

## 🎯 VERIFICATION & TESTING

### **1. Check All Services**

```powershell
# View running containers
docker compose ps

# Expected output (all "healthy" or "running"):
# postgres              running (healthy)
# redis                 running (healthy)
# minio                 running (healthy)
# mlflow-server         running (healthy)
# airflow-webserver     running (healthy)
# airflow-scheduler     running (healthy)
# airflow-worker        running (healthy)
# inference-service     running (healthy)
# Moniguard-web        running (healthy)
```

### **2. Access Web Interfaces**

| Service | URL | Credentials | Purpose |
|---------|-----|-------------|---------|
| **Moniguard** | http://localhost:5000 | None | Main dashboard |
| **Airflow** | http://localhost:8080 | airflow / airflow | DAG management |
| **MLflow** | http://localhost:5500 | None | Model registry |
| **MinIO Console** | http://localhost:9001 | minioadmin / minioadmin | S3 storage |
| **Inference API** | http://localhost:8000/docs | None | API docs (FastAPI) |

### **3. Run First Training**

```powershell
# Option 1: Via Airflow UI
# 1. Go to http://localhost:8080
# 2. Login: airflow / airflow
# 3. Find DAG: fraud_detection_training
# 4. Toggle ON (unpause)
# 5. Click "Trigger DAG" (play button)

# Option 2: Via CLI
docker compose exec airflow-webserver airflow dags trigger fraud_detection_training

# Monitor progress
docker compose logs -f airflow-worker
```

**Expected Duration**: 10-30 minutes (depending on data size)

**What happens**:
1. Fetches data from Fraud API (or local source)
2. Feature engineering (33 features)
3. Trains XGBoost model with SMOTE
4. Logs to MLflow:
   - Metrics: precision, recall, f1, roc_auc
   - Parameters: max_depth, learning_rate, etc.
   - Model: `fraud_detection_model`
5. Saves model to `/app/models/fraud_detection_model.pkl`
6. Registers model in MLflow registry

### **4. Verify Model in MLflow**

```powershell
# Open MLflow UI
Start-Process http://localhost:5500

# Navigate to:
# - "Experiments" → "fraud_detection"
# - Click latest run
# - Verify metrics (precision, recall, f1)
# - Check "Artifacts" → model files

# Or via API
curl http://localhost:5500/api/2.0/mlflow/registered-models/get?name=fraud_detection_model
```

### **5. Run Inference**

```powershell
# Option 1: Via Moniguard UI
# 1. Go to http://localhost:5000
# 2. Click "Run Inference" button
# 3. Wait for completion

# Option 2: Via API
curl -X POST http://localhost:8000/inference/run `
  -H "Content-Type: application/json" `
  -d '{"max_records": 1000}'

# Check results
curl http://localhost:8000/inference/results | ConvertFrom-Json | ConvertTo-Json -Depth 10
```

**What happens**:
1. Inference service fetches unprocessed transactions from `transactions` table
2. Applies same feature engineering as training
3. Loads model from MLflow (or local cache)
4. Generates predictions
5. Saves to `fraud_predictions` table:
   - `fraud_probability` (0.0 - 1.0)
   - `fraud_prediction` (0 or 1)
   - `fraud_label` ("Legitimate" or "Fraud")
   - `risk_level` ("Low", "Medium", "High")
   - `actual_fraud` (from `transactions.is_fraud`)

### **6. Verify Moniguard Dashboard**

```powershell
# Open Moniguard
Start-Process http://localhost:5000
```

**Check these elements**:

1. **KPI Metrics** (Top 4 cards):
   - Total Transactions (should update in real-time)
   - Fraud Rate (percentage)
   - Approval Rate (100% - fraud rate)
   - Active Alerts (fraud count)
   - ✅ All should show LIVE data (updates every 500ms)

2. **Transaction Volume & Fraud Trends** (Chart):
   - Dual y-axis chart
   - Bars: Total transaction volume (left axis)
   - Line: Fraud attempts (right axis, orange)
   - X-axis: Time buckets (15-minute intervals)
   - ✅ Should show real data from last 6 hours

3. **Live Fraud Transaction Feed** (Table):
   - Shows ONLY transactions where `fraud_prediction = 1` OR `actual_fraud = 1`
   - Columns: Time, Transaction ID, Merchant, Location, Amount, Risk Score, Status, Details
   - ✅ Merchant names should be REAL (e.g., "Amazon", "Walmart", not "Transaction")
   - ✅ Locations should be REAL (e.g., "New York, US", not "Unknown")
   - ✅ Pulsing red "LIVE" indicator

4. **Model Health** (Bottom left):
   - Model name (e.g., "Fraud Detection Model")
   - Version (e.g., "8" or "latest")
   - Accuracy (e.g., "98.45%")
   - ✅ Should match MLflow data

5. **System Health** (Navigate to `/system-health`):
   - Component status cards:
     - Inference API (green = healthy)
     - PostgreSQL (green = connected)
     - MLflow Registry (green = active)
     - Airflow Pipeline (green = scheduled)
   - Performance gauge (circular chart)
   - Environment info panel

---

## 🔧 TROUBLESHOOTING GUIDE

### **Issue 1: Services Not Starting**

```powershell
# Check container status
docker compose ps

# View logs for specific service
docker compose logs -f <service_name>
# Examples:
docker compose logs -f postgres
docker compose logs -f mlflow-server
docker compose logs -f inference
docker compose logs -f Moniguard

# Common fixes:
# 1. Restart service
docker compose restart <service_name>

# 2. Rebuild image
docker compose build --no-cache <service_name>
docker compose up -d <service_name>

# 3. Check port conflicts
netstat -ano | findstr :<port>
# If port is in use, change in docker-compose.yml
```

### **Issue 2: Database Connection Errors**

```powershell
# Verify PostgreSQL is running
docker compose exec postgres pg_isready -U airflow

# Check database exists
docker compose exec postgres psql -U airflow -c "\l"

# Verify tables exist
docker compose exec postgres psql -U airflow -d transactions_db -c "\dt"

# Expected tables:
# - transactions
# - fraud_predictions

# Check user permissions
docker compose exec postgres psql -U airflow -d transactions_db -c "\du"

# If tables missing, re-run init script
docker compose down -v
docker compose up -d postgres
# Wait 30 seconds for init-multiple-dbs.sh to run
```

### **Issue 3: Moniguard Shows "No Data"**

**Diagnosis**:
```powershell
# 1. Check if inference service is running
curl http://localhost:8000/health

# 2. Check if there are predictions in database
docker compose exec postgres psql -U airflow -d transactions_db -c "SELECT COUNT(*) FROM fraud_predictions;"

# 3. Check if there are transactions
docker compose exec postgres psql -U airflow -d transactions_db -c "SELECT COUNT(*) FROM transactions;"

# 4. Check Moniguard logs
docker compose logs -f Moniguard
```

**Solutions**:
```powershell
# Solution A: No transactions exist
# Start producer to generate data
docker compose --profile producer up -d producer

# OR manually insert test transaction
docker compose exec postgres psql -U fraud_producer -d transactions_db -c "
INSERT INTO transactions (transaction_id, order_id, user_id, amount, vendor_id, location, country, is_fraud, timestamp)
VALUES ('TEST001', 'ORD001', 'USER001', 150.00, 'Amazon', 'New York, US', 'USA', 1, NOW());
"

# Solution B: No predictions exist
# Run inference manually
curl -X POST http://localhost:8000/inference/run -H "Content-Type: application/json" -d '{"max_records": 100}'

# Solution C: Database connection issue
# Check Moniguard environment variables
docker compose exec Moniguard env | grep DB_
# Should show:
# DB_HOST=postgres
# DB_NAME=transactions_db
# DB_USER=fraud_training
# DB_PASSWORD=training_password
```

### **Issue 4: MLflow Not Showing Model**

```powershell
# Check MLflow is running
curl http://localhost:5500/health

# Check if model was registered
curl http://localhost:5500/api/2.0/mlflow/registered-models/list

# If no model, trigger training
docker compose exec airflow-webserver airflow dags trigger fraud_detection_training

# Monitor training logs
docker compose logs -f airflow-worker

# Check if model file exists
docker compose exec airflow-worker ls -lh /app/models/
# Should show: fraud_detection_model.pkl
```

### **Issue 5: Inference Service Can't Load Model**

```powershell
# Check inference logs
docker compose logs -f inference

# Common errors and fixes:

# Error: "Model not found in MLflow"
# Fix: Check MLflow connection
docker compose exec inference curl http://mlflow-server:5500/health

# Error: "Local model file not found"
# Fix: Verify model file exists
docker compose exec inference ls -lh /app/models/

# Error: "Database connection failed"
# Fix: Verify database credentials
docker compose exec inference env | grep DB_

# Restart inference after fixes
docker compose restart inference
```

### **Issue 6: Chart Not Updating**

```powershell
# Open browser console (F12)
# Check for JavaScript errors

# Common issues:
# 1. Server-Sent Events (SSE) connection failed
#    - Check Moniguard logs: docker compose logs -f Moniguard
#    - Verify /api/stream endpoint: curl http://localhost:5000/api/stream

# 2. No trend data
#    - Check if predictions exist in last 6 hours
docker compose exec postgres psql -U airflow -d transactions_db -c "
SELECT COUNT(*) FROM fraud_predictions 
WHERE prediction_timestamp >= NOW() - INTERVAL '6 hours';
"

# 3. Browser cache issue
#    - Hard refresh: Ctrl + Shift + R
#    - Clear browser cache
```

---

## 📊 DATA FLOW VERIFICATION

### **End-to-End Test**

```powershell
# 1. Insert test transaction
docker compose exec postgres psql -U fraud_producer -d transactions_db -c "
INSERT INTO transactions (
    transaction_id, order_id, user_id, full_name, email, amount, 
    vendor_id, location, country, payment_method, is_fraud, timestamp
) VALUES (
    'E2E_TEST_001', 'ORD_E2E_001', 'USER_E2E', 'Test User', 'test@example.com', 250.00,
    'TestVendor', 'Los Angeles, US', 'USA', 'Credit Card', 1, NOW()
);
"

# 2. Run inference
curl -X POST http://localhost:8000/inference/run -H "Content-Type: application/json" -d '{"max_records": 10}'

# 3. Verify prediction was created
docker compose exec postgres psql -U airflow -d transactions_db -c "
SELECT 
    fp.transaction_id, 
    fp.fraud_prediction, 
    fp.fraud_probability, 
    fp.actual_fraud,
    t.vendor_id as merchant,
    t.location
FROM fraud_predictions fp
LEFT JOIN transactions t ON fp.transaction_id = t.transaction_id
WHERE fp.transaction_id = 'E2E_TEST_001';
"

# Expected output:
# transaction_id | fraud_prediction | fraud_probability | actual_fraud | merchant    | location
# E2E_TEST_001   | 1                | 0.8500            | 1            | TestVendor  | Los Angeles, US

# 4. Check Moniguard dashboard
# - Open http://localhost:5000
# - Look for E2E_TEST_001 in "Live Fraud Transaction Feed"
# - Verify merchant shows "TestVendor"
# - Verify location shows "Los Angeles, US"
# - Verify risk score shows ~85%
```

---

## 🎯 OPTIMIZATION TIPS

### **Performance Tuning**

1. **Database Connection Pooling** (Already configured in `app.py`):
   - Min connections: 2
   - Max connections: 10
   - Connection timeout: 30s

2. **Inference Batch Size**:
   - Default: 1000 records per run
   - Adjust in API call: `{"max_records": 500}`

3. **Moniguard Update Interval**:
   - Default: 500ms (real-time)
   - To reduce load, edit `dashboard-enhanced.js`:
     ```javascript
     const eventSource = new EventSource('/api/stream?interval_ms=2000'); // 2 seconds
     ```

4. **Chart Data Window**:
   - Default: Last 6 hours
   - To change, edit `app.py` line 292:
     ```python
     def get_trend_data(hours: int = 12):  # 12 hours instead of 6
     ```

### **Resource Allocation**

```yaml
# Add to docker-compose.yml for resource limits:
services:
  inference:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
        reservations:
          cpus: '1'
          memory: 1G
```

---

## 🔐 SECURITY NOTES

### **Production Considerations** (NOT for local dev):

1. **Change Default Passwords**:
   - Airflow: `_AIRFLOW_WWW_USER_PASSWORD`
   - PostgreSQL: `POSTGRES_PASSWORD`
   - MinIO: `MINIO_PASSWORD`

2. **Enable SSL/TLS**:
   - PostgreSQL: Set `DB_SSLMODE=require`
   - MLflow: Use HTTPS reverse proxy

3. **Network Isolation**:
   - Use Docker networks
   - Don't expose all ports to host

4. **Secrets Management**:
   - Use Docker secrets or external vault
   - Don't commit `.env` to Git

---

## 📝 MAINTENANCE

### **Daily Tasks**
- [ ] Check Airflow DAG runs (should run daily at 2 AM)
- [ ] Monitor Moniguard metrics
- [ ] Review fraud alerts

### **Weekly Tasks**
- [ ] Check disk space: `docker system df`
- [ ] Review MLflow experiments
- [ ] Backup PostgreSQL: `docker compose exec postgres pg_dump -U airflow transactions_db > backup.sql`

### **Monthly Tasks**
- [ ] Clean old Docker images: `docker system prune -a`
- [ ] Review model performance metrics
- [ ] Update dependencies

---

## 🚀 QUICK START COMMANDS (Copy-Paste Ready)

### **First Time Setup**:
```powershell
cd C:\Users\me\Projects\MLOps_Fraud_Detection\src
docker compose build
docker compose up -d postgres
Start-Sleep -Seconds 30
docker compose up -d minio mc mlflow-server
Start-Sleep -Seconds 30
docker compose up airflow-init
docker compose up -d airflow-webserver airflow-scheduler airflow-worker airflow-triggerer redis
Start-Sleep -Seconds 120
docker compose up -d inference Moniguard
Start-Sleep -Seconds 30
```

### **Subsequent Starts**:
```powershell
cd C:\Users\me\Projects\MLOps_Fraud_Detection\src
docker compose up -d
```

### **Stop Everything**:
```powershell
cd C:\Users\me\Projects\MLOps_Fraud_Detection\src
docker compose down
```

### **Complete Reset** (⚠️ DELETES ALL DATA):
```powershell
cd C:\Users\me\Projects\MLOps_Fraud_Detection\src
docker compose down -v
docker system prune -a -f
# Then run "First Time Setup" again
```

---

## ✅ FINAL CHECKLIST

Before considering the system "ready":

- [ ] All services show "healthy" in `docker compose ps`
- [ ] Airflow UI accessible at http://localhost:8080
- [ ] MLflow UI accessible at http://localhost:5500
- [ ] Moniguard UI accessible at http://localhost:5000
- [ ] At least one training run completed successfully
- [ ] Model visible in MLflow registry
- [ ] Inference service can load model
- [ ] Moniguard shows live metrics (not zeros)
- [ ] Live Fraud Transaction Feed shows real merchant names
- [ ] Chart displays dual y-axis with real data
- [ ] System Health page shows all components green

---

**STATUS**: Your system is now a **PRODUCTION-GRADE MLOps FRAUD DETECTION PLATFORM** 🎉

**Next Steps**:
1. Run first training: `docker compose exec airflow-webserver airflow dags trigger fraud_detection_training`
2. Wait 10-30 minutes for training to complete
3. Run inference: `curl -X POST http://localhost:8000/inference/run -H "Content-Type: application/json" -d '{"max_records": 1000}'`
4. Open Moniguard: http://localhost:5000
5. Watch the magic happen! ✨





