# 🗄️ Database Architecture: Isolated Producer Database

## Overview

Your system now has a **proper database separation**:

```
┌──────────────────────────────────────────────────────────────┐
│                    PostgreSQL Server                         │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────────┐        ┌──────────────────┐           │
│  │ transactions_db  │        │    mlflow        │           │
│  ├──────────────────┤        ├──────────────────┤           │
│  │ transactions     │        │ experiments      │           │
│  │ (38 columns)     │        │ metrics          │           │
│  │ (7 indexes)      │        │ artifacts        │           │
│  └──────────────────┘        └──────────────────┘           │
│   ▲      ▲      ▲                   ▲                        │
│   │      │      │                   │                        │
└───┼──────┼──────┼───────────────────┼────────────────────────┘
    │      │      │                   │
    │      │      │             ┌─────┘
    │      │      │             │
    │      │      │       ┌─────────────┐
    │      │      │       │   MLflow    │
    │      │      │       │  (Docker)   │
    │      │      │       └─────────────┘
    │      │      │
┌───┴──┐ ┌─┴──┐ ┌─┴──────────────┐
│Prod  │ │Inf │ │ Training DAG   │
│      │ │    │ │ (Airflow/Docker)
│      │ │    │ │
└──────┘ └────┘ └────────────────┘
```

---

## 🎯 Database Isolation

### **transactions_db** (Producer's Database)
Owner: `fraud_producer` (writes)

| User | Role | Access | Purpose |
|------|------|--------|---------|
| `fraud_producer` | Writer | Full R/W | Produces transaction data |
| `fraud_inference` | Reader | SELECT only | Inference script reads predictions |
| `fraud_training` | Reader | SELECT only | Training reads raw data for features |

**Table**: `transactions` (38 columns)
- Stores raw e-commerce transaction data
- No feature engineering (raw data)
- Fraud labels included for training

**Indexes** (7 total):
```sql
idx_user_timestamp        -- For user activity analysis
idx_device_timestamp      -- For device fingerprinting
idx_ip_timestamp          -- For IP geolocation analysis
idx_timestamp             -- For time-series features
idx_is_fraud              -- For fraud filtering
idx_payment_status        -- For payment analysis
idx_action                -- For behavioral analysis
```

---

### **mlflow** (MLflow Experiments)
Owner: `mlflow`

Used by:
- MLflow server (experiment tracking)
- Airflow (if configured)
- Not accessed by producer/inference directly

---

### **airflow** (Airflow Metadata)
Owner: `airflow` (from docker-compose)

Used by:
- Airflow webserver (DAGs, tasks, logs)
- Airflow scheduler
- Airflow workers
- Not accessed by producer

---

## 👥 User Permissions

### 1. `fraud_producer` (Producer User)
```sql
PRIVILEGES: All privileges on transactions_db
PURPOSE: Creates tables, inserts transactions, updates records
USED BY: Producer script (main.py)
```

### 2. `fraud_inference` (Inference User)
```sql
PRIVILEGES: SELECT on all tables in transactions_db
PURPOSE: Read-only access to transactions for prediction
USED BY: Inference script (inference.py)
```

### 3. `fraud_training` (Training User)
```sql
PRIVILEGES: SELECT on all tables in transactions_db
PURPOSE: Read raw transactions for feature engineering
USED BY: Training DAG (fraud_detection_training.py)
```

### 4. `mlflow` (MLflow User)
```sql
PRIVILEGES: All privileges on mlflow database
PURPOSE: Track experiments, log metrics, store artifacts
USED BY: MLflow server
```

### 5. `airflow` (Airflow User)
```sql
PRIVILEGES: All privileges on airflow database
PURPOSE: Store DAG definitions, task states, logs
USED BY: Airflow webserver, scheduler, workers
```

---

## 🔄 Data Flow

### **Writing (Producer)**
```
Producer Script
  └─→ fraud_producer user (127.0.0.1:5432)
       └─→ transactions_db
            └─→ transactions table
                 └─→ INSERT 100-1000 records/batch
```

### **Reading (Inference)**
```
Inference Script
  └─→ fraud_inference user (127.0.0.1:5432)
       └─→ transactions_db
            └─→ transactions table (read-only)
                 └─→ SELECT latest records
                      └─→ Engineer features
                           └─→ Make predictions
```

### **Reading (Training)**
```
Training DAG
  └─→ fraud_training user (127.0.0.1:5432)
       └─→ transactions_db
            └─→ transactions table (read-only)
                 └─→ SELECT all records
                      └─→ Engineer features
                           └─→ Train XGBoost model
```

---

## ⚙️ Configuration

### **.env File**

```env
# ========== PRODUCER ==========
DB_HOST=127.0.0.1
DB_PORT=5432
DB_NAME=transactions_db
DB_USER=fraud_producer
DB_PASSWORD=producer_password

# ========== INFERENCE ==========
INFERENCE_DB_HOST=127.0.0.1
INFERENCE_DB_USER=fraud_inference
INFERENCE_DB_PASSWORD=inference_password

# ========== TRAINING ==========
TRAINING_DB_HOST=127.0.0.1
TRAINING_DB_USER=fraud_training
TRAINING_DB_PASSWORD=training_password
```

---

## 🚀 Operational Scenarios

### Scenario 1: Producer Before Docker
```powershell
# 1. Start PostgreSQL (Docker)
docker run -d -p 5432:5432 postgres:13

# 2. Initialize databases (manual or via docker exec)
psql -U postgres -f src/init-multiple-dbs.sh

# 3. Start producer (standalone)
.\scripts\start-producer.ps1
# Producer runs, stacks transactions in transactions_db

# 4. Later: Start full stack
cd src
docker-compose up -d
# Inference & Training can immediately read producer's data
```

### Scenario 2: Producer with Docker
```powershell
# 1. Start docker-compose (includes PostgreSQL)
cd src
docker-compose up -d

# 2. PostgreSQL initializes automatically with init-multiple-dbs.sh
# 3. Wait for postgres service to be healthy

# 4. Start producer (connects to same PostgreSQL)
.\scripts\start-producer.ps1
# Producer writes, Airflow/Inference/Training all read

# 5. All services use same transaction data
```

### Scenario 3: Producer Only (No Docker)
```powershell
# 1. Ensure PostgreSQL is running locally
psql -U postgres -c "SELECT 1"

# 2. Initialize databases
psql -U postgres -f src/init-multiple-dbs.sh

# 3. Start producer
.\scripts\start-producer.ps1

# 4. Data accumulates in transactions_db
# 5. Later: Add docker-compose for inference/training
```

---

## 🔒 Security Benefits

✅ **Producer can't read** (no accidental reads)
✅ **Inference can't write** (no data contamination)
✅ **Training can't modify** (data integrity)
✅ **Each service has credentials** (audit trail)
✅ **Separate database for MLflow** (experiment isolation)
✅ **Separate database for Airflow** (DAG isolation)

---

## 📊 Monitoring & Maintenance

### Check Producer Data
```bash
# As fraud_producer
psql -h 127.0.0.1 -U fraud_producer -d transactions_db
SELECT COUNT(*), COUNT(CASE WHEN is_fraud=1 THEN 1 END) FROM transactions;
```

### Check Inference Permissions
```bash
# As fraud_inference (should work - read-only)
psql -h 127.0.0.1 -U fraud_inference -d transactions_db
SELECT COUNT(*) FROM transactions;  # ✅ Works

# This should fail - fraud_inference can't write
INSERT INTO transactions VALUES (...);  # ❌ Permission denied
```

### Check Training Permissions
```bash
# As fraud_training (should work - read-only)
psql -h 127.0.0.1 -U fraud_training -d transactions_db
SELECT COUNT(*) FROM transactions;  # ✅ Works

# This should fail - fraud_training can't write
DELETE FROM transactions;  # ❌ Permission denied
```

---

## 🔄 Connection Pooling

Each service maintains its own connection pool:

| Service | Pool Size | Purpose |
|---------|-----------|---------|
| Producer | 2-10 | Write transactions in batches |
| Inference | 1-5 | Read for predictions |
| Training | 1-2 | Read for feature engineering |
| Airflow | 20+ | Multiple task parallelism |

---

## 📈 Scaling Considerations

### Producer Scaling
```env
# For higher throughput
PRODUCER_INTERVAL=0.1          # 100ms between batches
PRODUCER_BATCH_SIZE=100        # 100 txn per batch
# Results in: ~1000 txn/second
```

### Inference Scaling
```env
# For higher prediction volume
INFERENCE_DB_USER=fraud_inference
# Add more inference server instances (same user)
```

### Training Scaling
```env
# For parallel feature engineering
TRAINING_DB_USER=fraud_training
# Add more training workers (same user)
```

---

## 🐛 Troubleshooting

### "Permission denied" Error
```
ERROR: permission denied for schema public
```
**Solution**: Check user permissions:
```bash
psql -U postgres -d transactions_db -c "GRANT USAGE ON SCHEMA public TO fraud_inference;"
```

### Can't Connect to Database
```
ERROR: could not translate host name "postgres" to address
```
**Solution**: For standalone producer, use `127.0.0.1` not `postgres`

### Producer Writes Slow
```
Insert rate: 10 txn/sec (expected: 1000+)
```
**Solution**: Increase batch size:
```env
PRODUCER_BATCH_SIZE=100
PRODUCER_INTERVAL=0.1
```

---

## 📋 Database Status Checklist

- [ ] PostgreSQL is running on 127.0.0.1:5432
- [ ] `transactions_db` database exists
- [ ] `fraud_producer` user has write access
- [ ] `fraud_inference` user has read-only access
- [ ] `fraud_training` user has read-only access
- [ ] `mlflow` database exists
- [ ] `airflow` database exists (for docker-compose)
- [ ] Indexes are created on transactions table
- [ ] Producer can insert records
- [ ] Inference can read records
- [ ] Training can read records

---

## ✅ Verification Commands

```bash
# Test producer user
psql -h 127.0.0.1 -U fraud_producer -d transactions_db \
  -c "INSERT INTO transactions VALUES (...);"

# Test inference user
psql -h 127.0.0.1 -U fraud_inference -d transactions_db \
  -c "SELECT COUNT(*) FROM transactions;"

# Test training user
psql -h 127.0.0.1 -U fraud_training -d transactions_db \
  -c "SELECT * FROM transactions LIMIT 1;"

# Check all databases
psql -h 127.0.0.1 -U postgres -c "\l"

# Check all users
psql -h 127.0.0.1 -U postgres -c "\du"
```

---

## 📚 Related Documentation

- [QUICK_START_PRODUCER.md](QUICK_START_PRODUCER.md) - How to start producer
- [.env.example](.env.example) - Configuration variables
- [src/init-multiple-dbs.sh](src/init-multiple-dbs.sh) - Database setup script
- [producer/main.py](producer/main.py) - Producer implementation

---

**Architecture**: Isolated but interconnected  
**Security**: Role-based access control  
**Scalability**: Independent scaling per service  
**Status**: ✅ Ready for production
