# MLOps Fraud Detection - Deployment Guide

This guide covers deploying the MLOps Fraud Detection solution both locally and to Azure (AKS/ACR).

## Table of Contents

1. [Local Development Setup](#local-development-setup)
2. [Docker Compose Deployment](#docker-compose-deployment)
3. [Azure Deployment](#azure-deployment)
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
   - **MLflow UI**: http://localhost:5500
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

## Azure Deployment

> **For detailed Azure deployment instructions, see [AZURE_DEPLOYMENT.md](AZURE_DEPLOYMENT.md)**

### Quick Azure Deploy

```bash
# Automated deployment script
chmod +x scripts/deploy-azure-complete.sh
./scripts/deploy-azure-complete.sh
```

This will:
1. Build and push all Docker images to ACR
2. Deploy all Kubernetes resources
3. Configure all services with Azure resources
4. Display all UI endpoints

### All UI Endpoints (Azure)

After deployment, access these services:

- **Fraud Guard**: `http://<fraudguard-ip>:5000`
- **Airflow**: `http://<airflow-ip>:8080` (airflow/airflow)
- **MLflow**: `http://<mlflow-ip>:5000`
- **Inference API**: `http://<inference-ip>:8000`
- **Flower (Celery UI)**: `http://<flower-ip>:5555`

Get IPs with:
```bash
kubectl get svc -n mlops
```

## Azure Deployment (Legacy)

### Prerequisites

- Azure CLI installed and configured
- Azure subscription with permissions to create:
  - Azure Container Registry (ACR)
  - Azure Kubernetes Service (AKS)
  - Resource Groups
- kubectl installed
- Docker Desktop or Docker Engine

### Step 1: Create Azure Resources

#### Create Resource Group
```bash
az group create --name mlops-rg --location eastus
```

#### Create Azure Container Registry
```bash
az acr create --resource-group mlops-rg --name mlopsacr12345 --sku Basic
```

#### Create Azure Kubernetes Service
```bash
az aks create \
  --resource-group mlops-rg \
  --name mlops-aks \
  --node-count 3 \
  --enable-addons monitoring \
  --generate-ssh-keys \
  --attach-acr mlopsacr12345
```

### Step 2: Configure Environment Variables

Create or update `.env` file with Azure-specific values:
```bash
ACR_NAME=mlopsacr12345
ACR_REGISTRY=mlopsacr12345.azurecr.io
AKS_RESOURCE_GROUP=mlops-rg
AKS_CLUSTER_NAME=mlops-aks
AKS_NAMESPACE=mlops
```

### Step 3: Build and Push Images

#### Option A: Using the deployment script
```bash
chmod +x scripts/deploy-to-azure.sh
./scripts/deploy-to-azure.sh
```

#### Option B: Manual steps

1. **Login to Azure and ACR**
   ```bash
   az login
   az acr login --name mlopsacr12345
   ```

2. **Build and push images**
   ```bash
   # Airflow
   cd src/airflow
   docker build -t mlopsacr12345.azurecr.io/fraud-detection/airflow:latest .
   docker push mlopsacr12345.azurecr.io/fraud-detection/airflow:latest
   
   # MLflow
   cd ../mlflow
   docker build -t mlopsacr12345.azurecr.io/fraud-detection/mlflow:latest .
   docker push mlopsacr12345.azurecr.io/fraud-detection/mlflow:latest
   
   # Inference
   cd ../inference
   docker build -t mlopsacr12345.azurecr.io/fraud-detection/inference:latest .
   docker push mlopsacr12345.azurecr.io/fraud-detection/inference:latest
   
   # Fraud Guard
   cd ../../fraudguard
   docker build -t mlopsacr12345.azurecr.io/fraud-detection/fraudguard:latest .
   docker push mlopsacr12345.azurecr.io/fraud-detection/fraudguard:latest
   ```

### Step 4: Deploy to AKS

1. **Get AKS credentials**
   ```bash
   az aks get-credentials --resource-group mlops-rg --name mlops-aks
   ```

2. **Create namespace**
   ```bash
   kubectl create namespace mlops
   ```

3. **Create secrets** (update k8s/secrets.yaml with your values first)
   ```bash
   kubectl apply -f k8s/secrets.yaml -n mlops
   ```

4. **Deploy services**
   ```bash
   kubectl apply -f k8s/mlflow.yaml -n mlops
   kubectl apply -f k8s/inference-config.yaml -n mlops
   kubectl apply -f k8s/inference.yaml -n mlops
   kubectl apply -f k8s/airflow.yaml -n mlops
   ```

5. **Check deployment status**
   ```bash
   kubectl get pods -n mlops
   kubectl get services -n mlops
   ```

### Step 5: Access Services

Get service URLs:
```bash
# Get LoadBalancer IPs
kubectl get svc -n mlops

# Or use port-forwarding for testing
kubectl port-forward -n mlops svc/mlflow 5500:5500
kubectl port-forward -n mlops svc/inference 8000:8000
kubectl port-forward -n mlops svc/fraudguard 5000:5000
```

## Architecture Overview

### Components

1. **Fraud Guard Web Application** (`fraudguard/`)
   - Flask-based web UI for client IT team
   - Displays fraud detection results, alerts, and system health
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
   - Stores model artifacts in MinIO
   - Port: 5500

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

#### 5. Azure Deployment Issues

**Images not pulling:**
```bash
# Verify ACR login
az acr login --name [acr-name]

# Check image exists
az acr repository list --name [acr-name]

# Verify AKS has ACR access
az aks update --name [aks-name] --resource-group [rg-name] --attach-acr [acr-name]
```

**Pods not starting:**
```bash
# Check pod status
kubectl describe pod [pod-name] -n mlops

# Check logs
kubectl logs [pod-name] -n mlops

# Check events
kubectl get events -n mlops --sort-by='.lastTimestamp'
```

### Performance Tuning

#### Local Development
- Use `FRAUD_API_MAX_RECORDS=50000` for faster training
- Reduce Airflow workers to 1
- Use SQLite for MLflow (not recommended for production)

#### Azure Production
- Use managed PostgreSQL for Airflow
- Use Azure Blob Storage instead of MinIO
- Enable AKS autoscaling
- Use Azure Monitor for logging

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
