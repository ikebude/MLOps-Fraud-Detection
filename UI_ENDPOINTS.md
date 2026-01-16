# UI Endpoints Reference

Quick reference for all user interfaces and API endpoints in the MLOps Fraud Detection solution.

## Local Development Endpoints

When running with `docker compose up`:

| Service | URL | Credentials | Purpose |
|---------|-----|-------------|---------|
| **Fraud Guard** | http://localhost:5000 | None | Main web dashboard for client IT team |
| **Airflow** | http://localhost:8080 | airflow/airflow | Workflow orchestration and DAG management |
| **MLflow** | http://localhost:5500 | None | Model registry and experiment tracking |
| **MinIO Console** | http://localhost:9001 | minioadmin/minioadmin | Object storage management |
| **Inference API** | http://localhost:8000 | None | REST API for fraud detection |
| **Flower** | http://localhost:5555 | None | Celery worker monitoring (requires `--profile flower`) |

## Azure Deployment Endpoints

After deploying to AKS, get LoadBalancer IPs with:
```bash
kubectl get svc -n mlops
```

| Service | URL Pattern | Credentials | Purpose |
|---------|------------|-------------|---------|
| **Fraud Guard** | `http://<fraudguard-ip>:5000` | None | Main web dashboard |
| **Airflow** | `http://<airflow-ip>:8080` | airflow/airflow | Workflow orchestration |
| **MLflow** | `http://<mlflow-ip>:5000` | None | Model registry |
| **Inference API** | `http://<inference-ip>:8000` | None | REST API |
| **Flower** | `http://<flower-ip>:5555` | None | Celery monitoring |

## API Endpoints

### Inference Service (`http://localhost:8000` or `<inference-ip>:8000`)

#### Health Check
```bash
GET /health
```
Returns service health status and model availability.

#### Run Inference
```bash
POST /inference/run
Content-Type: application/json

{
  "max_records": 1000
}
```
Runs fraud detection inference on transactions.

#### Get Results
```bash
GET /inference/results?page=1&per_page=100
```
Retrieves paginated inference results.

#### Get Statistics
```bash
GET /inference/stats
```
Returns summary statistics of latest inference run.

### Fraud Guard API (`http://localhost:5000` or `<fraudguard-ip>:5000`)

#### Health Check
```bash
GET /api/health
```
Returns health status of all connected services.

#### Trigger Inference
```bash
POST /api/inference/run
Content-Type: application/json

{
  "max_records": 1000
}
```
Triggers inference via Fraud Guard UI.

#### Get Inference Results
```bash
GET /api/inference/results
```
Gets latest inference results.

## Accessing Services

### Local Development

```bash
# Start all services
cd src
docker compose up -d

# Start with Flower (Celery UI)
docker compose --profile flower up -d

# Check service status
docker compose ps

# View logs
docker compose logs -f [service-name]
```

### Azure Deployment

```bash
# Get all service IPs
kubectl get svc -n mlops

# Get specific service IP
kubectl get svc fraudguard -n mlops -o jsonpath='{.status.loadBalancer.ingress[0].ip}'

# Port forward for testing (if LoadBalancer not ready)
kubectl port-forward -n mlops svc/fraudguard 5000:5000
```

## Service Details

### Fraud Guard (Port 5000)
- **Purpose**: Web dashboard for monitoring fraud detection
- **Features**: 
  - Real-time fraud alerts
  - Transaction monitoring
  - System health dashboard
  - Inference triggering
- **No authentication required** (add authentication for production)

### Airflow (Port 8080)
- **Purpose**: Workflow orchestration
- **Features**:
  - DAG management
  - Task monitoring
  - Log viewing
  - Trigger DAGs manually
- **Default credentials**: `airflow` / `airflow`
- **Change credentials** for production!

### MLflow (Port 5000)
- **Purpose**: Model registry and experiment tracking
- **Features**:
  - Model versions
  - Experiment comparison
  - Artifact storage
  - Model serving
- **No authentication** (add for production)

### MinIO Console (Port 9001)
- **Purpose**: Object storage management
- **Features**:
  - Bucket management
  - File browser
  - Access policies
- **Default credentials**: `minioadmin` / `minioadmin`
- **Local development only** (Azure uses Azure Blob Storage)

### Inference API (Port 8000)
- **Purpose**: REST API for fraud detection
- **Features**:
  - Real-time inference
  - Batch processing
  - Results retrieval
  - Statistics
- **No authentication** (add API keys for production)

### Flower (Port 5555)
- **Purpose**: Celery worker monitoring
- **Features**:
  - Worker status
  - Task monitoring
  - Real-time metrics
  - Task history
- **No authentication** (add for production)
- **Only available** when using CeleryExecutor

## Security Notes

⚠️ **Important**: These endpoints are configured for development. For production:

1. **Add authentication** to all UIs
2. **Use HTTPS** instead of HTTP
3. **Restrict access** with network policies
4. **Rotate credentials** regularly
5. **Enable TLS** for all services
6. **Use API keys** for Inference API
7. **Configure CORS** properly

## Troubleshooting

### Service Not Accessible

**Local:**
```bash
# Check if service is running
docker compose ps

# Check logs
docker compose logs [service-name]

# Restart service
docker compose restart [service-name]
```

**Azure:**
```bash
# Check pod status
kubectl get pods -n mlops

# Check service status
kubectl get svc -n mlops

# Check logs
kubectl logs -f deployment/[service-name] -n mlops
```

### Port Already in Use

```bash
# Find process using port
netstat -an | grep [port-number]

# Kill process or change port in docker-compose.yml
```

### LoadBalancer IP Pending (Azure)

```bash
# Check service events
kubectl describe svc [service-name] -n mlops

# Use port-forward as temporary solution
kubectl port-forward -n mlops svc/[service-name] [local-port]:[service-port]
```

---

**Quick Access**: Bookmark these URLs for easy access during development!
