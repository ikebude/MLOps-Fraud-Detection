# MLOps Fraud Detection - Deployment Guide

This guide covers deploying the MLOps Fraud Detection solution locally and to Kubernetes.

## Table of Contents

1. [Local Development Setup](#local-development-setup)
2. [Docker Compose Deployment](#docker-compose-deployment)
3. [Kubernetes Deployment](#kubernetes-deployment)
4. [Architecture Overview](#architecture-overview)
5. [Troubleshooting](#troubleshooting)

## Local Development Setup

### Prerequisites

- Docker Desktop (Windows/Mac) or Docker Engine (Linux)
- Docker Compose v2 or higher
- At least 8GB RAM allocated to Docker
- Git

### Quick Start

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd MLOps_Fraud_Detection
   ```

2. **Run setup script**
   ```bash
   chmod +x scripts/setup-local.sh
   ./scripts/setup-local.sh
   ```

3. **Configure environment variables**
   ```bash
   cd src
   # Edit .env file with your configuration
   # See .env.example for all available options
   ```

4. **Build and start services**
   ```bash
   docker compose build
   docker compose up -d
   ```

5. **Access services**
   - **Fraud Guard Web UI**: http://localhost:5000
   - **Airflow Web UI**: http://localhost:8080 (username: airflow, password: airflow)
   - **MLflow UI**: http://localhost:5000
   - **MinIO Console**: http://localhost:9001 (username: minioadmin, password: minioadmin)
   - **Inference API**: http://localhost:8000

### Service Health Checks

Check if all services are running:
```bash
docker compose ps
```

View logs:
```bash
docker compose logs -f [service-name]
```

## Docker Compose Deployment

### Building Images

Build all images locally:
```bash
chmod +x scripts/build-images.sh
./scripts/build-images.sh
```

Or build individually:
```bash
cd src
docker compose build [service-name]
```

### Starting Services

Start all services:
```bash
cd src
docker compose up -d
```

Start specific services:
```bash
docker compose up -d postgres redis mlflow-server
```

### Stopping Services

Stop all services:
```bash
docker compose down
```

Stop and remove volumes (⚠️ deletes data):
```bash
docker compose down -v
```

### Updating Services

After code changes:
```bash
docker compose build [service-name]
docker compose up -d [service-name]
```

## Kubernetes Deployment

For Kubernetes deployment instructions, see:

- `OCI_DEPLOYMENT.md`

## Architecture Overview

### Components

1. **Fraud Guard Web UI**
   - Port: 5000

2. **Inference Service** (`src/inference/`)
   - REST API for real-time fraud detection
   - Processes transactions and returns predictions
   - Port: 8000

3. **Airflow** (`src/airflow/`)
   - Orchestrates training pipeline
   - Manages scheduled model retraining
   - Port: 8080

4. **MLflow** (`src/mlflow/`)
   - Model registry and experiment tracking
   - Port: 5000

5. **MinIO**
   - S3-compatible object storage
   - Stores MLflow artifacts
   - Ports: 9000 (API), 9001 (Console)

6. **PostgreSQL**
   - Airflow metadata database
   - MLflow backend store
   - Port: 5432

7. **Redis**
   - Celery broker for Airflow
   - Port: 6379

### Data Flow

```
Fraud API → Airflow DAG → Training Pipeline → MLflow → Model Storage (MinIO)
                                                              ↓
                                                         Inference Service
                                                              ↓
                                                         Fraud Guard UI
```

## Troubleshooting

### Common Issues

#### 1. Services not starting
```bash
# Check logs
docker compose logs [service-name]

# Check resource usage
docker stats

# Restart service
docker compose restart [service-name]
```

#### 2. Out of Memory Errors
- Reduce `FRAUD_API_MAX_RECORDS` in `.env`
- Increase Docker Desktop memory allocation
- Reduce number of Airflow workers

#### 3. Port Conflicts
- Check if ports are already in use:
  ```bash
  netstat -an | grep [port-number]
  ```
- Update port mappings in `docker-compose.yml`

#### 4. Model Not Found
- Ensure training DAG has run successfully
- Check model path: `src/models/fraud_detection_model.pkl`
- Verify MLflow connection



### Performance Tuning

#### Local Development
- Use `FRAUD_API_MAX_RECORDS=50000` for faster training
- Reduce Airflow workers to 1
- Use SQLite for MLflow (not recommended for production)



## Next Steps

1. **Monitor Training**: Check Airflow UI for DAG runs
2. **View Models**: Access MLflow UI to see experiment results
3. **Test Inference**: Use Fraud Guard UI or Inference API
4. **Set Up Alerts**: Configure monitoring and alerting
5. **Scale**: Adjust resources based on workload

## Support

For issues or questions:
- Check logs: `docker compose logs` or `kubectl logs`
- Review configuration in `.env` and `config.yaml`
- Check service health endpoints
