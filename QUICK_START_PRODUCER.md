# 🚀 Quick Start Guide: Local Producer Setup

## Overview

You now have a **complete, production-ready producer** that can:
- ✅ Run standalone locally  
- ✅ Generate realistic transaction data (2.8% fraud rate)
- ✅ Use connection pooling for efficiency
- ✅ Auto-create database schema
- ✅ Provide health checks and statistics
- ✅ Handle graceful shutdown

---

## Step 1: Setup Environment

### Create `.env` file
```bash
# Copy the template
cp .env.example .env

# Edit with your settings (or use defaults for local dev)
```

### OR Set Environment Variables
```powershell
# PowerShell
$env:DB_HOST = "127.0.0.1"
$env:DB_PORT = "5432"
$env:DB_NAME = "transactions_db"
$env:DB_USER = "fraud_user"
$env:DB_PASSWORD = "your_secure_password"
```

---

## Step 2: Install Dependencies

```bash
cd producer
pip install -r requirements.txt
```

### What Gets Installed
- `psycopg2-binary` - PostgreSQL adapter
- `faker` - Realistic data generation
- `jsonschema` - Schema validation
- `python-dotenv` - Environment variable management
- `confluent_kafka` - Kafka support (optional)

---

## Step 3: Prepare Database

### Option A: Using Docker (Recommended for Windows)
```bash
# Start PostgreSQL in Docker
docker run -d \
  --name fraud-postgres \
  -e POSTGRES_PASSWORD=postgres \
  -p 5432:5432 \
  postgres:13
```

### Option B: Local PostgreSQL Installation
```bash
# Ensure PostgreSQL is running
psql -U postgres -c "SELECT 1"
```

### Create Database & User
```bash
psql -U postgres -c "
  CREATE DATABASE transactions_db;
  CREATE USER fraud_user WITH PASSWORD 'your_secure_password';
  GRANT ALL ON DATABASE transactions_db TO fraud_user;
"
```

---

## Step 4: Start Producer

### Windows (PowerShell)
```powershell
.\scripts\start-producer.ps1
```

### Linux/Mac (Bash)
```bash
chmod +x scripts/start-producer.sh
./scripts/start-producer.sh
```

### Direct Python (Any OS)
```bash
cd producer
python main.py
```

---

## Step 5: Monitor Production

### View Live Logs
```powershell
# PowerShell
Get-Content producer/producer.log -Tail 50 -Wait

# Bash
tail -f producer/producer.log
```

### Check Database Statistics
```bash
psql -h 127.0.0.1 -U fraud_user -d transactions_db -c "
  SELECT 
    COUNT(*) as total_transactions,
    COUNT(CASE WHEN is_fraud=1 THEN 1 END) as fraud_count,
    ROUND(COUNT(CASE WHEN is_fraud=1 THEN 1 END)::numeric / COUNT(*) * 100, 2) as fraud_rate_pct
  FROM transactions;
"
```

### Expected Output
```
 total_transactions | fraud_count | fraud_rate_pct
--------------------+-------------+----------------
                250 |           7 |           2.80
```

---

## Configuration Reference

| Variable | Default | Purpose |
|----------|---------|---------|
| `DB_HOST` | 127.0.0.1 | PostgreSQL hostname |
| `DB_PORT` | 5432 | PostgreSQL port |
| `DB_NAME` | transactions_db | Database name |
| `DB_USER` | fraud_user | Database user |
| `DB_PASSWORD` | (required) | Database password |
| `PRODUCER_INTERVAL` | 0.5 | Seconds between batches |
| `PRODUCER_BATCH_SIZE` | 1 | Transactions per batch |
| `LOG_LEVEL` | INFO | Logging verbosity |

### Tuning for Performance

**For Testing/Development:**
```env
PRODUCER_INTERVAL=1.0
PRODUCER_BATCH_SIZE=10
LOG_LEVEL=INFO
```

**For Production:**
```env
PRODUCER_INTERVAL=0.1
PRODUCER_BATCH_SIZE=100
LOG_LEVEL=WARNING
```

---

## Sample Output

When running, you'll see:

```
════════════════════════════════════════════════════════════════════════════════
Nigerian E-commerce Transaction Generator with Connection Pooling
════════════════════════════════════════════════════════════════════════════════
Database: 127.0.0.1:5432/transactions_db
Interval: 0.5s | Batch Size: 1
Fraud Rate: <3% (target: 2.8%)
Running 24/7 - Press Ctrl+C to stop
════════════════════════════════════════════════════════════════════════════════

[INFO] Connection pool initialized (min=2, max=10)
[INFO] Transactions table ready (with indexes)
[INFO] Database connection established and healthy
[INFO] Producer started

Producer is starting... (Press Ctrl+C to stop)

════════════════════════════════════════════════════════════════════════════════
PRODUCER STATS | Generated: 100 | Inserted: 100 | Fraud: 3 (3.00%) | Rate: 2.50 txn/s
DATABASE STATS | Total: 250 | Fraud: 7 | Unique Users: 125
════════════════════════════════════════════════════════════════════════════════
```

---

## Troubleshooting

### "Database connection refused"
```bash
# Check if PostgreSQL is running
psql -U postgres -c "SELECT 1"

# For Docker:
docker ps | grep postgres
```

### "Missing Python dependencies"
```bash
pip install -r producer/requirements.txt
```

### "Table already exists error"
Producer is designed to work with existing tables. This is normal.

### Producer suddenly stops
Check the log file for the reason:
```bash
tail -50 producer/producer.log
```

---

## Integration with Other Components

### Connect Inference Script
```python
# The inference script will automatically read from the transactions table
python src/inference/inference.py --monitor
```

### Connect Training DAG
```bash
# Airflow training will read the raw transactions
# Make sure DB_HOST is set to the same database
```

### Monitor in FraudGuard
```bash
# FraudGuard dashboard queries the database
# Open: http://localhost:5000
```

---

## Advanced: Docker Compose

To run everything together:

```bash
# From src/ directory
docker-compose up -d

# This starts:
# - PostgreSQL (with transactions_db)
# - Producer (if included in docker-compose.yml)
# - Airflow + MLflow
# - Inference API
# - FraudGuard UI
```

---

## Health Check Endpoint (Future Enhancement)

Once we add Flask to producer, you'll be able to:

```bash
curl http://localhost:5001/health
```

Response:
```json
{
  "status": "healthy",
  "transactions_generated": 10250,
  "fraud_count": 287,
  "rate_txn_per_sec": 2.5,
  "db_connected": true
}
```

---

## Key Features Implemented

✅ **Connection Pooling**: Min 2 / Max 10 concurrent connections
✅ **Health Checks**: Database connectivity validation  
✅ **Batch Insertion**: Optimized for 100+ records per insert
✅ **Statistics Tracking**: Real-time generation metrics
✅ **Schema Validation**: JSONSchema validation of transactions
✅ **Graceful Shutdown**: Proper cleanup on SIGTERM/SIGINT
✅ **Error Recovery**: Automatic connection retry with backoff
✅ **Comprehensive Logging**: Detailed operation and error logs
✅ **Fraud Simulation**: Realistic 2.8% fraud rate with patterns
✅ **Nigerian Data**: Localized names, locations, payment methods

---

## Next Steps

1. **Start the producer**: Run one of the startup commands above
2. **Monitor logs**: Watch real-time generation progress
3. **Check database**: Verify transactions are being inserted
4. **Connect inference**: Test predictions on generated data
5. **Run training DAG**: Train model on realistic transaction patterns

---

## Support

For issues or questions:
1. Check logs: `producer/producer.log`
2. Verify database: `psql -U fraud_user -d transactions_db`
3. Review configuration: Check `.env` file
4. Test connectivity: Try connecting to PostgreSQL manually

**Happy Fraud Detection! 🎯**
