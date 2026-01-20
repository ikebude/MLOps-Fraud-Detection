# 🌐 Complete Endpoint URLs Reference

**Base IP:** `4.153.190.166`  
**Protocol:** `http://` (HTTPS not configured)

---

## 📋 Table of Contents
1. [Airflow Endpoints](#airflow-endpoints)
2. [MLflow Endpoints](#mlflow-endpoints)
3. [FraudGuard Endpoints](#fraudguard-endpoints)
4. [Inference API Endpoints](#inference-api-endpoints)
5. [Flower Endpoints](#flower-endpoints)
6. [External Data Sources](#external-data-sources)

---

## 🔐 Airflow Endpoints

### Web UI
- **Main Dashboard:** `http://4.153.190.166/airflow/`
- **DAGs List:** `http://4.153.190.166/airflow/dags/`
- **DAG Details:** `http://4.153.190.166/airflow/dags/{dag_id}/grid`
- **DAG Code:** `http://4.153.190.166/airflow/dags/{dag_id}/code`
- **DAG Graph:** `http://4.153.190.166/airflow/dags/{dag_id}/graph`
- **DAG Logs:** `http://4.153.190.166/airflow/dags/{dag_id}/logs`
- **DAG Runs:** `http://4.153.190.166/airflow/dags/{dag_id}/dagRuns`
- **Task Instances:** `http://4.153.190.166/airflow/dags/{dag_id}/task-instances`
- **Task Logs:** `http://4.153.190.166/airflow/log?dag_id={dag_id}&task_id={task_id}&execution_date={date}`

### API Endpoints (v2)
- **Health Check:** `http://4.153.190.166/airflow/api/v2/monitor/health`
- **DAGs List:** `http://4.153.190.166/airflow/api/v2/dags`
- **DAG Details:** `http://4.153.190.166/airflow/api/v2/dags/{dag_id}`
- **DAG Runs:** `http://4.153.190.166/airflow/api/v2/dags/{dag_id}/dagRuns`
- **Trigger DAG:** `POST http://4.153.190.166/airflow/api/v2/dags/{dag_id}/dagRuns`
- **Task Instances:** `http://4.153.190.166/airflow/api/v2/dags/{dag_id}/taskInstances`
- **Task Logs:** `http://4.153.190.166/airflow/api/v2/dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances/{task_id}/logs/{task_try_number}`
- **Variables:** `http://4.153.190.166/airflow/api/v2/variables`
- **Connections:** `http://4.153.190.166/airflow/api/v2/connections`
- **Pools:** `http://4.153.190.166/airflow/api/v2/pools`
- **XComs:** `http://4.153.190.166/airflow/api/v2/dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances/{task_id}/xcomEntries`

### Authentication
- **Login:** `http://4.153.190.166/airflow/login/`
- **Logout:** `http://4.153.190.166/airflow/logout/`
- **Current User:** `http://4.153.190.166/airflow/api/v2/users/me`

**Default Credentials:**
- **Username:** `airflow`
- **Password:** `airflow`
- **Confirmed:** User exists in database (verified from pod logs)

---

## 📊 MLflow Endpoints

### Web UI
- **Main UI:** `http://4.153.190.166/mlflow/` ⚠️ **Note: Requires trailing slash**
- **Experiments:** `http://4.153.190.166/mlflow/#/experiments/0`
- **Models:** `http://4.153.190.166/mlflow/#/models`
- **Model Versions:** `http://4.153.190.166/mlflow/#/models/{model_name}/versions/{version}`
- **Runs:** `http://4.153.190.166/mlflow/#/experiments/{experiment_id}/runs/{run_id}`

### API Endpoints (v2.0)
- **Health:** `http://4.153.190.166/mlflow/health`
- **Search Experiments:** `POST http://4.153.190.166/mlflow/api/2.0/mlflow/experiments/search`
- **Get Experiment:** `GET http://4.153.190.166/mlflow/api/2.0/mlflow/experiments/get?experiment_id={id}`
- **Search Runs:** `POST http://4.153.190.166/mlflow/api/2.0/mlflow/runs/search`
- **Get Run:** `GET http://4.153.190.166/mlflow/api/2.0/mlflow/runs/get?run_id={id}`
- **Search Registered Models:** `POST http://4.153.190.166/mlflow/api/2.0/mlflow/registered-models/search`
- **Get Model:** `GET http://4.153.190.166/mlflow/api/2.0/mlflow/registered-models/get?name={model_name}`
- **Get Model Version:** `GET http://4.153.190.166/mlflow/api/2.0/mlflow/model-versions/get?name={model_name}&version={version}`
- **Get Latest Model Version:** `GET http://4.153.190.166/mlflow/api/2.0/mlflow/model-versions/get-latest-versions?name={model_name}`
- **Download Artifacts:** `GET http://4.153.190.166/mlflow/api/2.0/mlflow/artifacts/download?run_id={id}&path={path}`

**Default Model Name:** `fraud_detection_model`

---

## 🛡️ FraudGuard Endpoints

### Web UI Pages
- **Dashboard Overview:** `http://4.153.190.166/fraudguard/`
- **Transactions:** `http://4.153.190.166/fraudguard/transactions`
- **Alerts:** `http://4.153.190.166/fraudguard/alerts`
- **System Health:** `http://4.153.190.166/fraudguard/system_health`
- **Settings:** `http://4.153.190.166/fraudguard/settings`

### API Endpoints
- **Health Check:** `GET http://4.153.190.166/fraudguard/api/health`
- **Dashboard Data:** `GET http://4.153.190.166/fraudguard/api/data`
- **Dashboard Data (with refresh):** `GET http://4.153.190.166/fraudguard/api/data?refresh=1`
- **Real-time Stream (SSE):** `GET http://4.153.190.166/fraudguard/api/stream`
- **Real-time Stream (custom interval):** `GET http://4.153.190.166/fraudguard/api/stream?interval_ms=2000`
- **Trigger Inference:** `POST http://4.153.190.166/fraudguard/api/inference/run`
- **Get Inference Results:** `GET http://4.153.190.166/fraudguard/api/inference/results`

### API Request Examples

**Get Dashboard Data:**
```powershell
Invoke-RestMethod -Uri "http://4.153.190.166/fraudguard/api/data?refresh=1"
```

**Trigger Inference:**
```powershell
Invoke-RestMethod -Uri "http://4.153.190.166/fraudguard/api/inference/run" `
    -Method POST `
    -ContentType "application/json" `
    -Body '{"max_records": 1000}'
```

---

## 🤖 Inference API Endpoints

### Base URL
- **Base:** `http://4.153.190.166/inference/`
- **Direct Access (LoadBalancer):** `http://20.15.87.21:8000/` (if LoadBalancer IP is accessible)

### Health & Status
- **Health Check:** `GET http://4.153.190.166/inference/health`
- **Health Check (alternative):** `GET http://4.153.190.166/inference/inference/health`

### Inference Operations
- **Run Inference (batch):** `POST http://4.153.190.166/inference/inference/run`
- **Run Inference (alternative):** `POST http://4.153.190.166/inference/run`
- **Real-time Predict:** `POST http://4.153.190.166/inference/inference/predict`
- **Real-time Predict (alternative):** `POST http://4.153.190.166/inference/predict`
- **Predict from API:** `POST http://4.153.190.166/inference/inference/predict_from_api`
- **Predict from API (alternative):** `POST http://4.153.190.166/inference/predict_from_api`

### Results & Statistics
- **Get Results:** `GET http://4.153.190.166/inference/inference/results`
- **Get Results (alternative):** `GET http://4.153.190.166/inference/results`
- **Get Results (paginated):** `GET http://4.153.190.166/inference/inference/results?page=1&per_page=100`
- **Get Stats:** `GET http://4.153.190.166/inference/inference/stats`
- **Get Stats (alternative):** `GET http://4.153.190.166/inference/stats`

### Request Examples

**Health Check:**
```powershell
Invoke-RestMethod -Uri "http://4.153.190.166/inference/health"
```

**Run Inference:**
```powershell
Invoke-RestMethod -Uri "http://4.153.190.166/inference/inference/run" `
    -Method POST `
    -ContentType "application/json" `
    -Body '{"max_records": 1000, "explain": true, "top_k": 5}'
```

**Get Stats:**
```powershell
Invoke-RestMethod -Uri "http://4.153.190.166/inference/inference/stats"
```

**Get Results (paginated):**
```powershell
Invoke-RestMethod -Uri "http://4.153.190.166/inference/inference/results?page=1&per_page=100"
```

**Real-time Predict (single transaction):**
```powershell
$payload = @{
    records = @(
        @{
            transaction_id = "12345"
            user_id = "user123"
            amount = 100.50
            timestamp = "2026-01-19T10:00:00Z"
        }
    )
    explain = $true
    top_k = 5
} | ConvertTo-Json -Depth 10

Invoke-RestMethod -Uri "http://4.153.190.166/inference/inference/predict" `
    -Method POST `
    -ContentType "application/json" `
    -Body $payload
```

**Predict from API (pulls from Fraud API):**
```powershell
Invoke-RestMethod -Uri "http://4.153.190.166/inference/inference/predict_from_api" `
    -Method POST `
    -ContentType "application/json" `
    -Body '{"max_records": 10, "explain": true}'
```

---

## 🌸 Flower Endpoints

### Web UI
- **Main Dashboard:** `http://4.153.190.166/flower/`
- **Workers:** `http://4.153.190.166/flower/workers`
- **Tasks:** `http://4.153.190.166/flower/tasks`
- **Monitor:** `http://4.153.190.166/flower/monitor`
- **Broker:** `http://4.153.190.166/flower/broker`

### API Endpoints
- **Workers:** `GET http://4.153.190.166/flower/api/workers`
- **Tasks:** `GET http://4.153.190.166/flower/api/tasks`
- **Task Info:** `GET http://4.153.190.166/flower/api/task/info/{task_id}`
- **Task Result:** `GET http://4.153.190.166/flower/api/task/result/{task_id}`
- **Broker:** `GET http://4.153.190.166/flower/api/broker`

---

## 🌍 External Data Sources

### Fraud Detection API
- **Base URL:** `https://3consult-ng.com/fraud_api.php`
- **With Pagination:** `https://3consult-ng.com/fraud_api.php?offset=0&limit=100`
- **Purpose:** Source of transaction data for inference
- **Format:** JSON array or object with `data`/`transactions` key

**Example:**
```powershell
Invoke-RestMethod -Uri "https://3consult-ng.com/fraud_api.php?offset=0&limit=10"
```

---

## 🔧 Port Forwarding (Alternative Access)

If ingress is not accessible, use port forwarding:

```powershell
# Airflow
kubectl port-forward -n mlops svc/airflow-webserver 8080:8080
# Access at: http://localhost:8080/airflow

# MLflow
kubectl port-forward -n mlops svc/mlflow 5000:5000
# Access at: http://localhost:5000

# FraudGuard
kubectl port-forward -n mlops svc/fraudguard 5001:5000
# Access at: http://localhost:5001

# Inference
kubectl port-forward -n mlops svc/inference 8000:8000
# Access at: http://localhost:8000

# Flower
kubectl port-forward -n mlops svc/flower 5555:5555
# Access at: http://localhost:5555
```

---

## 📝 Notes

1. **Trailing Slashes:**
   - MLflow requires trailing slash: `/mlflow/` ✅ (not `/mlflow` ❌)
   - Airflow works with or without: `/airflow/` or `/airflow` ✅
   - FraudGuard works with or without: `/fraudguard/` or `/fraudguard` ✅

2. **Inference API Paths:**
   - Some endpoints work with both `/inference/` and `/inference/inference/` prefix
   - This is due to ingress routing + Flask route definitions

3. **Authentication:**
   - Airflow: Requires login (default: `airflow`/`airflow`)
   - MLflow: No authentication (public access)
   - FraudGuard: No authentication (public access)
   - Inference API: No authentication (public access)
   - Flower: No authentication (public access)

4. **LoadBalancer IP:**
   - Inference service has direct LoadBalancer IP: `20.15.87.21:8000`
   - Can be accessed directly if firewall allows

5. **CORS:**
   - CORS is enabled for all services
   - Allows cross-origin requests

---

## 🚀 Quick Access Script

Use the provided script for easy port forwarding:
```powershell
.\scripts\quick-access-port-forward.ps1
```

---

**Last Updated:** 2026-01-19  
**Ingress IP:** 4.153.190.166
