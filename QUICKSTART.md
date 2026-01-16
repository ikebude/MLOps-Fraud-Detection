# Quick Start Guide

Get up and running with the MLOps Fraud Detection solution in minutes!

## Prerequisites Check

```bash
# Check Docker
docker --version

# Check Docker Compose
docker compose version

# Check available memory (should be 8GB+)
docker info | grep -i memory
```

## Step 1: Setup Environment

```bash
# Clone repository (if not already done)
git clone <repository-url>
cd MLOps_Fraud_Detection

# Run setup script
chmod +x scripts/setup-local.sh
./scripts/setup-local.sh
```

## Step 2: Configure Environment Variables

```bash
cd src

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    cp ../.env.example .env
fi

# Edit .env file - at minimum set:
# FRAUD_API_URL=https://3consult-ng.com/fraud_api.php
# FRAUD_API_MAX_RECORDS=50000  # Start with smaller number for testing
```

## Step 3: Build Images

```bash
# Build all services (this may take 10-15 minutes first time)
docker compose build

# Or build specific service
docker compose build inference
```

## Step 4: Start Services

```bash
# Start all services in background
docker compose up -d

# Check status
docker compose ps

# View logs
docker compose logs -f
```

## Step 5: Verify Services

Wait 2-3 minutes for services to start, then check:

```bash
# Check all services are healthy
docker compose ps

# Test endpoints
curl http://localhost:5000/api/health  # Fraud Guard
curl http://localhost:8000/health        # Inference API
curl http://localhost:5500/health        # MLflow
curl http://localhost:8080/health        # Airflow
```

## Step 6: Access Web UIs

Open in your browser:

- **Fraud Guard**: http://localhost:5000
- **Airflow**: http://localhost:8080 (login: airflow/airflow)
- **MLflow**: http://localhost:5500
- **MinIO Console**: http://localhost:9001 (login: minioadmin/minioadmin)

## Step 7: Run Training

### Option A: Via Airflow UI

1. Go to http://localhost:8080
2. Login with `airflow` / `airflow`
3. Find `fraud_detection_training` DAG
4. Toggle it ON (if paused)
5. Click "Trigger DAG" (play button)
6. Monitor progress in Graph View

### Option B: Wait for Schedule

The DAG runs daily at 12:00 UTC. You can change the schedule in `src/dags/fraud_detection_training_dag.py`.

## Step 8: Test Inference

Once training completes (check Airflow logs), test inference:

```bash
# Run inference via API
curl -X POST http://localhost:8000/inference/run \
  -H "Content-Type: application/json" \
  -d '{"max_records": 100}'

# Get results
curl http://localhost:8000/inference/results

# Get statistics
curl http://localhost:8000/inference/stats
```

Or use the Fraud Guard UI:
1. Go to http://localhost:5000
2. Navigate to Transactions or Dashboard
3. Click "Run Inference" button

## Common Issues

### Services won't start

```bash
# Check logs
docker compose logs [service-name]

# Check if ports are in use
netstat -an | grep 5000
netstat -an | grep 8000
netstat -an | grep 8080

# Restart specific service
docker compose restart [service-name]
```

### Out of memory

```bash
# Reduce training data size in .env
FRAUD_API_MAX_RECORDS=50000

# Restart services
docker compose down
docker compose up -d
```

### Can't access services

```bash
# Check if services are running
docker compose ps

# Check service logs
docker compose logs [service-name]

# Verify network
docker network ls
docker network inspect mlops_fraud-detection
```

## Next Steps

- Read [DEPLOYMENT.md](DEPLOYMENT.md) for production deployment
- Check [README.md](README.md) for detailed documentation
- Explore the Fraud Guard UI for monitoring
- Review MLflow experiments and model versions

## Stopping Services

```bash
# Stop all services
docker compose down

# Stop and remove volumes (⚠️ deletes data)
docker compose down -v
```

## Getting Help

- Check logs: `docker compose logs -f [service]`
- Review configuration: `src/.env` and `src/config.yaml`
- See troubleshooting section in [DEPLOYMENT.md](DEPLOYMENT.md)

---

**That's it!** You should now have a fully functional MLOps fraud detection system running locally.
