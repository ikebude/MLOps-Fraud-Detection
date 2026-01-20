# Quick Reference Card - Azure MLOps Endpoints

## 🔐 Airflow Login
- **URL:** http://4.153.190.166/airflow
- **Username:** `airflow`
- **Password:** `airflow`

## 🌐 All Service URLs

| Service | URL |
|---------|-----|
| **Airflow** | http://4.153.190.166/airflow |
| **MLflow** | http://4.153.190.166/mlflow/ ⚠️ (use trailing slash) |
| **Fraud Guard** | http://4.153.190.166/fraudguard |
| **Inference API** | http://4.153.190.166/inference |
| **Flower** | http://4.153.190.166/flower |

## 📊 Current Status

- ✅ **Model Loaded:** Version 8
- ✅ **Records Processed:** 102
- ✅ **Fraud Rate:** 22.55%
- ✅ **All Services:** Running

## 🔧 Quick Tests

```powershell
# Test all endpoints
.\scripts\quick-test-endpoints.ps1

# Check MLflow models
.\scripts\check-mlflow-and-api.ps1

# Full verification
.\scripts\final-endpoint-check.ps1
```

## 📞 Key Endpoints

**Inference:**
- Health: `GET /inference/health`
- Stats: `GET /inference/stats`
- Run: `POST /inference/inference/run`

**Fraud Guard:**
- Health: `GET /fraudguard/api/health`
- Data: `GET /fraudguard/api/data`
