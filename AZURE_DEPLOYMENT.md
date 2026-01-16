# Azure Deployment Guide - MLOps Fraud Detection

Complete guide for deploying the MLOps Fraud Detection solution to Azure Kubernetes Service (AKS).

## Prerequisites

- Azure CLI installed and configured
- kubectl installed
- Docker Desktop or Docker Engine
- Access to Azure subscription with permissions to create:
  - Azure Container Registry (ACR)
  - Azure Kubernetes Service (AKS)
  - Azure PostgreSQL Database
  - Azure Storage Account

## Azure Resources Configuration

### Already Configured Resources

- **ACR**: `mlopsacr12345.azurecr.io`
- **Azure Storage**: `mlopsstorage12345`
- **PostgreSQL**: `mlops-postgres.postgres.database.azure.com`
- **AKS Cluster**: (configured in your environment)

## Step 1: Login to Azure and ACR

> **Windows Users**: Use the PowerShell script instead: `.\scripts\deploy-azure-complete.ps1`
> See [scripts/deploy-azure-windows.md](scripts/deploy-azure-windows.md) for Windows-specific instructions.

```bash
# Login to Azure
az login

# Login to Azure Container Registry
az acr login --name mlopsacr12345
```

## Step 2: Build and Push Docker Images

```bash
# Build and push all images
chmod +x scripts/build-images.sh
./scripts/build-images.sh

# Or build individually:
cd src/airflow
docker build -t mlopsacr12345.azurecr.io/fraud-detection/airflow:latest .
docker push mlopsacr12345.azurecr.io/fraud-detection/airflow:latest

cd ../mlflow
docker build -t mlopsacr12345.azurecr.io/fraud-detection/mlflow:latest .
docker push mlopsacr12345.azurecr.io/fraud-detection/mlflow:latest

cd ../inference
docker build -t mlopsacr12345.azurecr.io/fraud-detection/inference:latest .
docker push mlopsacr12345.azurecr.io/fraud-detection/inference:latest

cd ../../fraudguard
docker build -t mlopsacr12345.azurecr.io/fraud-detection/fraudguard:latest .
docker push mlopsacr12345.azurecr.io/fraud-detection/fraudguard:latest
```

## Step 3: Configure AKS Access

```bash
# Get AKS credentials (using your configured values)
az aks get-credentials --resource-group mlops_fraud_analytics --name mlops_aks_cluster

# Verify connection
kubectl get nodes
```

## Step 4: Create Image Pull Secret for ACR

```bash
# Create secret for ACR authentication
kubectl create secret docker-registry acr-secret \
  --docker-server=mlopsacr12345.azurecr.io \
  --docker-username=mlopsacr12345 \
  --docker-password='Tfs3lQolzy3n4GGvwpgjmJIlCP0wWDsRLSjiHmA/HZ+ACRC0hFnV' \
  --namespace=mlops
```

## Step 5: Deploy Kubernetes Resources

Deploy in the following order:

```bash
# 1. Create namespace and secrets
kubectl apply -f k8s/secrets.yaml

# 2. Deploy Redis (required for Celery)
kubectl apply -f k8s/redis.yaml

# 3. Deploy MLflow
kubectl apply -f k8s/mlflow.yaml

# 4. Deploy Inference Service
kubectl apply -f k8s/inference-config.yaml
kubectl apply -f k8s/inference.yaml

# 5. Deploy Airflow
kubectl apply -f k8s/airflow.yaml

# 6. Deploy Flower (Celery monitoring UI)
kubectl apply -f k8s/flower.yaml

# 7. Deploy Fraud Guard
kubectl apply -f k8s/fraudguard.yaml
```

## Step 6: Wait for Services to Start

```bash
# Check pod status
kubectl get pods -n mlops

# Watch pods until all are Running
kubectl get pods -n mlops -w

# Check services
kubectl get svc -n mlops
```

## Step 7: Get External IPs (LoadBalancer Endpoints)

```bash
# Get all LoadBalancer external IPs
kubectl get svc -n mlops

# Or get specific service IPs:
kubectl get svc airflow-webserver -n mlops -o jsonpath='{.status.loadBalancer.ingress[0].ip}'
kubectl get svc mlflow -n mlops -o jsonpath='{.status.loadBalancer.ingress[0].ip}'
kubectl get svc inference -n mlops -o jsonpath='{.status.loadBalancer.ingress[0].ip}'
kubectl get svc fraudguard -n mlops -o jsonpath='{.status.loadBalancer.ingress[0].ip}'
kubectl get svc flower -n mlops -o jsonpath='{.status.loadBalancer.ingress[0].ip}'
```

## Step 8: Access All UIs

Once LoadBalancer IPs are assigned, access the services:

### Service Endpoints

1. **Fraud Guard Web UI**
   - URL: `http://<fraudguard-external-ip>:5000`
   - Purpose: Main dashboard for client IT team
   - Features: Fraud detection monitoring, alerts, system health

2. **Airflow Web UI**
   - URL: `http://<airflow-webserver-external-ip>:8080`
   - Login: `airflow` / `airflow`
   - Purpose: Orchestrate training pipelines
   - Features: DAG management, task monitoring, logs

3. **MLflow UI**
   - URL: `http://<mlflow-external-ip>:5000`
   - Purpose: Model registry and experiment tracking
   - Features: Model versions, experiments, artifacts

4. **Inference API**
   - URL: `http://<inference-external-ip>:8000`
   - Purpose: REST API for fraud detection
   - Endpoints:
     - `GET /health` - Health check
     - `POST /inference/run` - Run inference
     - `GET /inference/results` - Get results
     - `GET /inference/stats` - Get statistics

5. **Flower (Celery Monitoring)**
   - URL: `http://<flower-external-ip>:5555`
   - Purpose: Monitor Celery workers
   - Features: Worker status, task monitoring, real-time metrics

## Step 9: Initialize Airflow Database

```bash
# Run Airflow database migrations
kubectl exec -it deployment/airflow-webserver -n mlops -- airflow db upgrade

# Create Airflow admin user
kubectl exec -it deployment/airflow-webserver -n mlops -- \
  airflow users create \
  --username airflow \
  --firstname Admin \
  --lastname User \
  --role Admin \
  --email admin@example.com \
  --password airflow
```

## Step 10: Upload DAGs to Airflow

The DAGs are already configured in the ConfigMap, but if you need to update them:

```bash
# Update DAGs ConfigMap
kubectl create configmap airflow-dags \
  --from-file=src/dags/ \
  --dry-run=client -o yaml | kubectl apply -f - -n mlops

# Restart Airflow to pick up new DAGs
kubectl rollout restart deployment/airflow-webserver -n mlops
kubectl rollout restart deployment/airflow-scheduler -n mlops
```

## Step 11: Trigger Training DAG

### Via Airflow UI:
1. Navigate to Airflow UI: `http://<airflow-ip>:8080`
2. Login with `airflow` / `airflow`
3. Find `fraud_detection_training` DAG
4. Toggle it ON (if paused)
5. Click "Trigger DAG" button
6. Monitor progress in Graph View

### Via API:
```bash
# Get Airflow service IP
AIRFLOW_IP=$(kubectl get svc airflow-webserver -n mlops -o jsonpath='{.status.loadBalancer.ingress[0].ip}')

# Trigger DAG
curl -X POST "http://${AIRFLOW_IP}:8080/api/v1/dags/fraud_detection_training/dagRuns" \
  -H "Content-Type: application/json" \
  -u airflow:airflow \
  -d '{"dag_run_id": "manual_trigger_'$(date +%s)'"}'
```

## Step 12: Test Inference Service

```bash
# Get Inference service IP
INFERENCE_IP=$(kubectl get svc inference -n mlops -o jsonpath='{.status.loadBalancer.ingress[0].ip}')

# Health check
curl http://${INFERENCE_IP}:8000/health

# Run inference
curl -X POST http://${INFERENCE_IP}:8000/inference/run \
  -H "Content-Type: application/json" \
  -d '{"max_records": 100}'

# Get results
curl http://${INFERENCE_IP}:8000/inference/results
```

## Monitoring and Logs

### View Pod Logs
```bash
# Airflow webserver
kubectl logs -f deployment/airflow-webserver -n mlops

# Airflow scheduler
kubectl logs -f deployment/airflow-scheduler -n mlops

# Airflow worker
kubectl logs -f deployment/airflow-worker -n mlops

# MLflow
kubectl logs -f deployment/mlflow -n mlops

# Inference
kubectl logs -f deployment/inference -n mlops

# Fraud Guard
kubectl logs -f deployment/fraudguard -n mlops

# Flower
kubectl logs -f deployment/flower -n mlops
```

### Check Pod Status
```bash
# All pods
kubectl get pods -n mlops

# Detailed status
kubectl describe pod <pod-name> -n mlops

# Events
kubectl get events -n mlops --sort-by='.lastTimestamp'
```

## Troubleshooting

### Pods Not Starting

```bash
# Check pod status
kubectl describe pod <pod-name> -n mlops

# Common issues:
# 1. Image pull errors - verify ACR credentials
# 2. Resource limits - check node capacity
# 3. ConfigMap/Secret issues - verify secrets exist
```

### Services Not Accessible

```bash
# Check LoadBalancer status
kubectl get svc -n mlops

# If External IP is pending, check:
# - AKS cluster has LoadBalancer support
# - Sufficient public IP quota
# - Network security group rules
```

### Airflow Database Connection Issues

```bash
# Test PostgreSQL connection from pod
kubectl exec -it deployment/airflow-webserver -n mlops -- \
  psql "postgresql://postgres:Ikebude99!@mlops-postgres.postgres.database.azure.com:5432/airflow?ssl=true"

# Verify firewall rules allow AKS IPs
```

### MLflow Artifact Storage Issues

```bash
# Verify Azure Storage credentials
kubectl get secret storage-credentials -n mlops -o yaml

# Test Azure Storage connection
kubectl exec -it deployment/mlflow -n mlops -- \
  env | grep AZURE_STORAGE
```

## Scaling Services

### Scale Airflow Workers
```bash
kubectl scale deployment airflow-worker --replicas=4 -n mlops
```

### Scale Inference Service
```bash
kubectl scale deployment inference --replicas=3 -n mlops
```

## Cleanup

```bash
# Delete all resources
kubectl delete namespace mlops

# Or delete individually
kubectl delete -f k8s/
```

## Quick Reference: All UI Endpoints

After deployment, access these URLs (replace with your LoadBalancer IPs):

| Service | URL | Credentials |
|---------|-----|-------------|
| Fraud Guard | `http://<fraudguard-ip>:5000` | None |
| Airflow | `http://<airflow-ip>:8080` | airflow/airflow |
| MLflow | `http://<mlflow-ip>:5000` | None |
| Inference API | `http://<inference-ip>:8000` | None |
| Flower | `http://<flower-ip>:5555` | None |

## Next Steps

1. **Monitor Training**: Check Airflow UI for DAG execution
2. **View Models**: Access MLflow UI to see experiment results
3. **Test Inference**: Use Fraud Guard UI or Inference API
4. **Set Up Alerts**: Configure Azure Monitor for notifications
5. **Scale Resources**: Adjust based on workload

---

**Ready to deploy?** Follow the steps above to get your MLOps solution running on Azure!
