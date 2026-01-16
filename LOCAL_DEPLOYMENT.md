# Local Deployment Guide - MLOps Fraud Detection

Complete guide for running the MLOps Fraud Detection solution locally using Docker Compose.

## Prerequisites

- **Docker Desktop** (Windows/Mac) or **Docker Engine** (Linux)
- **Docker Compose** v2 or higher (included with Docker Desktop)
- **At least 8GB RAM** allocated to Docker
- **Git** (for cloning the repository)

## Quick Start (Windows PowerShell)

```powershell
# 1. Run setup script
.\scripts\setup-local.ps1

# 2. Navigate to src directory
cd src

# 3. Build all Docker images (takes 10-15 minutes first time)
docker compose build

# 4. Start all services
docker compose up -d

# 5. Check service status
docker compose ps

# 6. View logs
docker compose logs -f
```

## Quick Start (Linux/Mac Bash)

```bash
# 1. Run setup script
chmod +x scripts/setup-local.sh
./scripts/setup-local.sh

# 2. Navigate to src directory
cd src

# 3. Build all Docker images (takes 10-15 minutes first time)
docker compose build

# 4. Start all services
docker compose up -d

# 5. Check service status
docker compose ps

# 6. View logs
docker compose logs -f
```

## Step-by-Step Instructions

### Step 1: Setup Environment

**Windows:**
```powershell
.\scripts\setup-local.ps1
```

**Linux/Mac:**
```bash
chmod +x scripts/setup-local.sh
./scripts/setup-local.sh
```

This script will:
- Create a `.env` file in the `src` directory if it doesn't exist
- Create necessary directories (models, logs, state, data)
- Verify Docker and Docker Compose are installed

### Step 2: Configure Environment Variables

Edit `src/.env` file and configure at minimum:

```env
# Fraud Detection API (required)
FRAUD_API_URL=https://3consult-ng.com/fraud_api.php
FRAUD_API_MAX_RECORDS=50000  # Start with smaller number for testing

# Airflow Configuration
AIRFLOW_UID=50000
POSTGRES_USER=airflow
POSTGRES_PASSWORD=airflow
POSTGRES_DB=airflow
POSTGRES_HOST=postgres
POSTGRES_PORT=5432

# MLflow Configuration
MLFLOW_TRACKING_URI=http://mlflow-server:5500
MLFLOW_S3_ENDPOINT_URL=http://minio:9000

# MinIO Configuration
MINIO_USERNAME=minioadmin
MINIO_PASSWORD=minioadmin
AWS_ACCESS_KEY_ID=minioadmin
AWS_SECRET_ACCESS_KEY=minioadmin
```

### Step 3: Build Docker Images

**Option A: Build all images at once**
```bash
cd src
docker compose build
```

**Option B: Build images individually**
```bash
cd src

# Build Airflow
docker compose build airflow-webserver airflow-scheduler airflow-worker

# Build MLflow
docker compose build mlflow-server

# Build Inference
docker compose build inference

# Build Fraud Guard
docker compose build fraudguard
```

**Note:** The first build will take 10-15 minutes as it downloads base images and installs dependencies. Subsequent builds are faster due to Docker layer caching.

### Step 4: Start Services

```bash
cd src
docker compose up -d
```

The `-d` flag runs services in detached mode (background).

### Step 5: Verify Services

Wait 2-3 minutes for services to start, then check:

```bash
# Check all services are running
docker compose ps

# Test health endpoints
curl http://localhost:5000/api/health  # Fraud Guard
curl http://localhost:8000/health        # Inference API
curl http://localhost:5500/health        # MLflow
curl http://localhost:8080/health        # Airflow
```

**Windows PowerShell:**
```powershell
# Check services
docker compose ps

# Test endpoints
Invoke-WebRequest -Uri http://localhost:5000/api/health
Invoke-WebRequest -Uri http://localhost:8000/health
Invoke-WebRequest -Uri http://localhost:5500/health
Invoke-WebRequest -Uri http://localhost:8080/health
```

## Access Web UIs

Once services are running, access the following UIs in your browser:

| Service | URL | Credentials |
|---------|-----|-------------|
| **Fraud Guard** | http://localhost:5000 | N/A |
| **Airflow** | http://localhost:8080 | `airflow` / `airflow` |
| **MLflow** | http://localhost:5500 | N/A |
| **MinIO Console** | http://localhost:9001 | `minioadmin` / `minioadmin` |
| **Inference API** | http://localhost:8000 | N/A |
| **Flower** (Celery UI) | http://localhost:5555 | N/A |

## Running Training

### Option A: Via Airflow UI (Recommended)

1. Open http://localhost:8080
2. Login with `airflow` / `airflow`
3. Find the `fraud_detection_training` DAG
4. Toggle it **ON** (if paused) - click the toggle switch on the left
5. Click **"Trigger DAG"** (play button) to run immediately
6. Monitor progress in **Graph View**

### Option B: Wait for Scheduled Run

The DAG is scheduled to run daily at 12:00 UTC. You can change the schedule in `src/dags/fraud_detection_training_dag.py`.

### Option C: Trigger via API

```bash
# Get Airflow API credentials (base64 encoded)
# Username: airflow, Password: airflow
# In PowerShell:
$cred = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("airflow:airflow"))

# Trigger DAG
Invoke-WebRequest -Uri "http://localhost:8080/api/v1/dags/fraud_detection_training/dagRuns" `
  -Method POST `
  -Headers @{Authorization="Basic $cred"} `
  -ContentType "application/json" `
  -Body '{}'
```

## Testing Inference

Once training completes, test the inference service:

```bash
# Run inference via API
curl -X POST http://localhost:8000/inference/run `
  -H "Content-Type: application/json" `
  -d '{\"max_records\": 100}'

# Get results
curl http://localhost:8000/inference/results

# Get statistics
curl http://localhost:8000/inference/stats
```

Or use the Fraud Guard UI:
1. Go to http://localhost:5000
2. Navigate to **Transactions** or **Dashboard**
3. Click **"Run Inference"** button

## Viewing Logs

```bash
# View all logs
docker compose logs -f

# View specific service logs
docker compose logs -f airflow-webserver
docker compose logs -f airflow-scheduler
docker compose logs -f inference
docker compose logs -f mlflow-server

# View last 100 lines
docker compose logs --tail=100 airflow-webserver
```

## Common Issues

### Services Won't Start

```bash
# Check logs for errors
docker compose logs [service-name]

# Check if ports are in use (Windows)
netstat -an | findstr "5000 8000 8080 5500"

# Restart specific service
docker compose restart [service-name]
```

### Out of Memory

If services crash or restart frequently:

1. **Reduce training data size** in `src/.env`:
   ```env
   FRAUD_API_MAX_RECORDS=50000  # Reduce from 100000
   ```

2. **Increase Docker memory allocation**:
   - Docker Desktop → Settings → Resources → Memory
   - Set to at least 8GB (16GB recommended)

3. **Restart services**:
   ```bash
   docker compose down
   docker compose up -d
   ```

### Can't Access Services

```bash
# Check if services are running
docker compose ps

# Check service logs
docker compose logs [service-name]

# Verify network
docker network ls
docker network inspect mlops_fraud-detection
```

### Airflow Database Issues

If Airflow shows database errors:

```bash
# Restart Airflow services
docker compose restart airflow-webserver airflow-scheduler

# Or reset Airflow database (⚠️ deletes all DAG runs)
docker compose down
docker volume rm mlops_fraud-detection_postgres-db-volume
docker compose up -d
```

### Port Already in Use

If you get "port already in use" errors:

```bash
# Find process using port (Windows)
netstat -ano | findstr :8080

# Kill process (replace PID)
taskkill /PID [PID] /F

# Or change ports in docker-compose.yml
```

## Stopping Services

```bash
# Stop all services (keeps data)
docker compose down

# Stop and remove volumes (⚠️ deletes all data)
docker compose down -v

# Stop specific service
docker compose stop [service-name]
```

## Rebuilding After Code Changes

```bash
# Rebuild and restart specific service
docker compose build [service-name]
docker compose up -d [service-name]

# Rebuild all services
docker compose build
docker compose up -d
```

## Development Workflow

1. **Make code changes** in your editor
2. **Rebuild the affected service**:
   ```bash
   docker compose build [service-name]
   docker compose up -d [service-name]
   ```
3. **Check logs** to verify changes:
   ```bash
   docker compose logs -f [service-name]
   ```

## Next Steps

- Read [QUICKSTART.md](QUICKSTART.md) for more detailed quick start guide
- Check [README.md](README.md) for architecture and design details
- Review [DEPLOYMENT.md](DEPLOYMENT.md) for production deployment options
- Explore the Fraud Guard UI for monitoring and visualization

## Getting Help

- Check logs: `docker compose logs -f [service]`
- Verify setup: `docker compose ps`
- Test endpoints: Use curl or browser to access service URLs
- Review service-specific documentation in each service directory
