# Azure MLOps Endpoints Status Report

**Generated:** $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")  
**Ingress IP:** 4.153.190.166  
**Base URL:** http://4.153.190.166

## ✅ Endpoint Status Summary

| Service | Endpoint | Status | Notes |
|---------|----------|--------|-------|
| **Airflow UI** | `/airflow` | ✅ Working | Status 200 |
| **MLflow UI** | `/mlflow` | ⚠️ Redirect | Status 308 (use `/mlflow/` with trailing slash) |
| **Fraud Guard UI** | `/fraudguard` | ✅ Working | Status 200 |
| **Inference API** | `/inference/health` | ✅ Working | Status 200 |
| **Flower UI** | `/flower` | ✅ Working | Status 200 |

## 🔐 Airflow Login Credentials

- **URL:** http://4.153.190.166/airflow
- **Username:** `airflow`
- **Password:** `airflow`

⚠️ **Security Note:** Change these default credentials for production use!

## 📊 Service Details

### 1. Airflow Web UI
- **URL:** http://4.153.190.166/airflow
- **Status:** ✅ Running
- **Purpose:** Orchestrate training pipelines, manage DAGs
- **Features:**
  - DAG management
  - Task monitoring
  - Logs viewing
  - Trigger training jobs

### 2. MLflow UI
- **URL:** http://4.153.190.166/mlflow/ (note trailing slash)
- **Status:** ⚠️ Redirect (308) - use trailing slash
- **Purpose:** Model registry and experiment tracking
- **Features:**
  - Model versions
  - Experiments
  - Artifacts
  - Model comparison

**Note:** The MLflow API endpoint for checking models is at:
- `http://4.153.190.166/mlflow/api/2.0/mlflow/registered-models/search`

### 3. Fraud Guard UI
- **URL:** http://4.153.190.166/fraudguard
- **Status:** ✅ Running
- **Purpose:** Main dashboard for client IT team
- **Features:**
  - Fraud detection monitoring
  - Real-time alerts
  - System health
  - Transaction visualization
  - Metrics and analytics

**API Endpoints:**
- Health: `http://4.153.190.166/fraudguard/api/health`
- Data: `http://4.153.190.166/fraudguard/api/data`

### 4. Inference API
- **Base URL:** http://4.153.190.166/inference
- **Status:** ✅ Running

**Available Endpoints:**
- **Health Check:** `GET /inference/health` or `GET /inference/inference/health`
- **Run Inference:** `POST /inference/inference/run`
- **Get Results:** `GET /inference/inference/results?page=1&per_page=100`
- **Get Stats:** `GET /inference/inference/stats`
- **Real-time Predict:** `POST /inference/inference/predict`
- **Predict from API:** `POST /inference/inference/predict_from_api`

**Example Usage:**
```powershell
# Health check
Invoke-WebRequest -Uri "http://4.153.190.166/inference/health"

# Get stats
Invoke-WebRequest -Uri "http://4.153.190.166/inference/inference/stats"

# Run inference
Invoke-WebRequest -Uri "http://4.153.190.166/inference/inference/run" `
  -Method POST -ContentType "application/json" `
  -Body '{"max_records": 100, "explain": true}'
```

### 5. Flower UI (Celery Monitoring)
- **URL:** http://4.153.190.166/flower
- **Status:** ✅ Running
- **Purpose:** Monitor Celery workers
- **Features:**
  - Worker status
  - Task monitoring
  - Real-time metrics

## 🗄️ Data Sources

### Fraud API
- **URL:** https://3consult-ng.com/fraud_api.php
- **Status:** ✅ Accessible with data
- **Records Available:** Yes (tested with 10 sample records)
- **Purpose:** Source of transaction data for inference

**Note:** The inference service can successfully read from this API. The API supports pagination with `offset` and `limit` parameters.

### MLflow Models
- **Status:** ⚠️ Need to verify
- **Location:** MLflow tracking server at `http://mlflow:5000` (internal) or `http://4.153.190.166/mlflow` (external)
- **Model Name:** `fraud_detection_model` (default)

**To check for models:**
1. Access MLflow UI: http://4.153.190.166/mlflow/
2. Navigate to "Models" section
3. Look for registered model: `fraud_detection_model`

**If no models found:**
- Run the Airflow training DAG first
- The DAG will train the model and register it in MLflow

## 🐳 Kubernetes Pod Status

All pods are running and healthy:

```
NAME                                 READY   STATUS    RESTARTS   AGE
airflow-scheduler-98ff4f9bf-k6mjd    1/1     Running   0          10h
airflow-webserver-6d64c66857-fwxbb   1/1     Running   0          10h
airflow-worker-8bb864849-khl6k       1/1     Running   0          10h
flower-868b586648-v2cw7              1/1     Running   0          4d9h
fraudguard-7fd6894d8d-69klt           1/1     Running   0          10h
inference-676c7bd8cf-h4rpg           1/1     Running   0          10h
mlflow-cdc6786f5-hnhfl               1/1     Running   0          4d6h
redis-5bd5dc5f6-krnrc                1/1     Running   0          5d13h
```

## 🔧 Troubleshooting

### MLflow 308 Redirect
**Issue:** MLflow returns 308 redirect when accessing without trailing slash  
**Solution:** Always use `/mlflow/` with trailing slash

### Inference Stats Returns 404
**Issue:** `/inference/inference/stats` returns 404  
**Solution:** Try `/inference/stats` or check if inference has been run first (stats only available after running inference)

### No Models in MLflow
**Issue:** MLflow shows no registered models  
**Solution:**
1. Login to Airflow UI
2. Find the `fraud_detection_training` DAG
3. Trigger the DAG to train and register the model

### Fraud Guard Shows No Data
**Issue:** Fraud Guard UI shows empty or default data  
**Solution:**
1. Ensure inference service has run at least once
2. Check that Fraud API is accessible
3. Verify MLflow has a trained model
4. Click "Run Inference" button in Fraud Guard UI

## 📝 Next Steps

1. **Verify MLflow Models:**
   - Access http://4.153.190.166/mlflow/
   - Check if `fraud_detection_model` is registered
   - If not, run the Airflow training DAG

2. **Test Inference:**
   - Access http://4.153.190.166/inference/health to verify service is ready
   - Run inference via API or Fraud Guard UI
   - Check results at `/inference/inference/results`

3. **Monitor System:**
   - Use Fraud Guard UI for real-time monitoring
   - Use Airflow UI to monitor training jobs
   - Use Flower UI to monitor Celery workers

4. **Security:**
   - Change Airflow default credentials
   - Review ingress security settings
   - Consider enabling HTTPS/TLS

## 🧪 Testing Scripts

Use the provided test scripts to verify endpoints:

```powershell
# Quick endpoint test
.\scripts\quick-test-endpoints.ps1

# Check MLflow and Fraud API
.\scripts\check-mlflow-and-api.ps1
```

## 📞 Support

If you encounter issues:
1. Check pod logs: `kubectl logs -n mlops deployment/<service-name>`
2. Check service status: `kubectl get svc -n mlops`
3. Check ingress: `kubectl get ingress -n mlops`
4. Review logs in Airflow UI for DAG execution errors
