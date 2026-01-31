# ✅ Isolated Database Setup Checklist

## What Changed

Your database is now properly isolated with these roles:

| Database | Owner | Users | Purpose |
|----------|-------|-------|---------|
| `transactions_db` | `fraud_producer` | `fraud_inference`, `fraud_training` (read-only) | Producer writes, others read |
| `mlflow` | `mlflow` | - | MLflow experiment tracking |
| `airflow` | `airflow` | - | Airflow DAG metadata |

---

## 🚀 Quick Start with Isolated Database

### Step 1: Copy Updated Configuration
```powershell
# You already have .env.example updated with new users
cp .env.example .env

# Default credentials are set in init-multiple-dbs.sh:
# Producer: fraud_producer / producer_password
# Inference: fraud_inference / inference_password
# Training: fraud_training / training_password
```

### Step 2: Start PostgreSQL
```powershell
# Option A: Docker (recommended)
docker run -d --name fraud-postgres -p 5432:5432 postgres:13

# Option B: Or use existing local PostgreSQL
psql -U postgres -c "SELECT 1"
```

### Step 3: Initialize Databases
```bash
# If using Docker, copy init script to container
docker cp src/init-multiple-dbs.sh fraud-postgres:/tmp/

# Run initialization
docker exec -it fraud-postgres psql -U postgres -f /tmp/init-multiple-dbs.sh
```

**Or manually** (local PostgreSQL):
```bash
psql -U postgres -f src/init-multiple-dbs.sh
```

### Step 4: Start Producer
```powershell
.\scripts\start-producer.ps1
```

**Producer now writes to `transactions_db` with `fraud_producer` user**

### Step 5: Start Full Stack (Optional)
```powershell
cd src
docker-compose up -d
```

**Inference & Training automatically read from same `transactions_db`**

---

## 📋 Verification Commands

### Check Databases Created
```bash
psql -U postgres -c "\l"
# Should show:
#  - transactions_db
#  - mlflow
#  - airflow
```

### Check Users Created
```bash
psql -U postgres -c "\du"
# Should show:
#  - fraud_producer (superuser on transactions_db)
#  - fraud_inference (read-only on transactions_db)
#  - fraud_training (read-only on transactions_db)
#  - mlflow
#  - airflow
```

### Verify Permissions
```bash
# Test producer (should succeed)
psql -h 127.0.0.1 -U fraud_producer -d transactions_db -c "SELECT 1;"

# Test inference (should succeed - read-only)
psql -h 127.0.0.1 -U fraud_inference -d transactions_db -c "SELECT COUNT(*) FROM transactions;"

# Test training (should succeed - read-only)
psql -h 127.0.0.1 -U fraud_training -d transactions_db -c "SELECT COUNT(*) FROM transactions;"
```

---

## 🎯 Common Workflows

### Workflow 1: Producer → Inference
```powershell
# Terminal 1: Start PostgreSQL
docker run -d -p 5432:5432 postgres:13
# Wait 10 seconds for startup

# Terminal 2: Initialize & start producer
psql -U postgres -f src/init-multiple-dbs.sh
.\scripts\start-producer.ps1

# Terminal 3: Run inference (reads producer's data)
python src/inference/inference.py --monitor
```

### Workflow 2: Producer → Full Stack
```powershell
# Terminal 1: Start full stack
cd src
docker-compose up -d

# Terminal 2: Start producer (standalone)
# Producer connects to docker's PostgreSQL (port 5432 exposed)
.\scripts\start-producer.ps1

# Terminal 3: Monitor all
# Producer writes to transactions_db
# Airflow training DAG reads from transactions_db
# Inference reads from transactions_db
# FraudGuard queries transactions_db
```

### Workflow 3: Producer Before Docker (Accumulate Data)
```powershell
# Step 1: Start producer 24/7
.\scripts\start-producer.ps1
# Generate data for hours/days

# Step 2: Later, start full stack
cd src
docker-compose up -d
# Training immediately has data to work with
```

---

## 🔍 Monitoring

### Check Transaction Count (As Producer)
```bash
psql -h 127.0.0.1 -U fraud_producer -d transactions_db \
  -c "SELECT COUNT(*) as total, COUNT(CASE WHEN is_fraud=1 THEN 1 END) as fraud_count FROM transactions;"
```

### Check Transaction Count (As Inference - Read-Only)
```bash
psql -h 127.0.0.1 -U fraud_inference -d transactions_db \
  -c "SELECT COUNT(*) FROM transactions;"
```

### Monitor Producer Growth
```bash
# Every 10 seconds, show transaction count
while true; do 
  psql -h 127.0.0.1 -U fraud_producer -d transactions_db \
    -c "SELECT NOW() as time, COUNT(*) as transactions FROM transactions;" ; 
  sleep 10
done
```

---

## 🆘 Troubleshooting

### Error: "Database transactions_db does not exist"
**Solution**: Run initialization script
```bash
psql -U postgres -f src/init-multiple-dbs.sh
```

### Error: "FATAL: remaining connection slots are reserved"
**Solution**: Too many connections. Increase PostgreSQL max connections or reduce pool size.

### Error: "Permission denied for schema public"
**Solution**: Run initialization script (permissions weren't set correctly)
```bash
psql -U postgres -f src/init-multiple-dbs.sh
```

### Producer can't write but inference can read
**Solution**: This is correct! Check that:
- Producer writes with `fraud_producer` user
- Inference reads with `fraud_inference` user
- Both can access `transactions_db`

---

## 📊 Database Passwords (Change These!)

Edit the init script before first run if you want custom passwords:

```bash
# In src/init-multiple-dbs.sh, line ~27:
CREATE USER fraud_producer WITH PASSWORD 'producer_password';
# Change 'producer_password' to something secure

# Line ~30:
CREATE USER fraud_inference WITH PASSWORD 'inference_password';
# Change to something secure

# Line ~33:
CREATE USER fraud_training WITH PASSWORD 'training_password';
# Change to something secure
```

Then update `.env` file to match:
```env
DB_USER=fraud_producer
DB_PASSWORD=your_new_secure_password

INFERENCE_DB_USER=fraud_inference
INFERENCE_DB_PASSWORD=your_new_secure_password

TRAINING_DB_USER=fraud_training
TRAINING_DB_PASSWORD=your_new_secure_password
```

---

## ✨ Key Benefits

✅ **Producer Independence** - Runs standalone, stacks data continuously
✅ **Read-Only Safety** - Inference/Training can't corrupt data
✅ **Proper Isolation** - Each service has its own credentials
✅ **Audit Trail** - Can track which service modified data
✅ **Docker Compatible** - Works with docker-compose
✅ **Scalable** - Easy to add more inference/training instances

---

## 📈 Next Steps

1. **Initialize databases** (one-time setup)
2. **Start producer** (anytime to stack data)
3. **Start docker-compose** (when you need training/inference/dashboard)
4. **Monitor** `transactions_db` growing as producer adds records
5. **Run training** which reads accumulated producer data
6. **Deploy inference** which serves predictions
7. **View FraudGuard** dashboard with results

---

## 📚 Related Files

- [DATABASE_ARCHITECTURE.md](DATABASE_ARCHITECTURE.md) - Full architecture explanation
- [.env.example](.env.example) - Configuration with all users
- [src/init-multiple-dbs.sh](src/init-multiple-dbs.sh) - Database setup script
- [QUICK_START_PRODUCER.md](QUICK_START_PRODUCER.md) - Producer startup guide
- [src/docker-compose.yml](src/docker-compose.yml) - Docker stack definition

---

**Status**: ✅ Ready to implement
**Complexity**: Low (just run init script once)
**Time to Setup**: 2 minutes
