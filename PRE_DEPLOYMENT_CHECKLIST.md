# Pre-Deployment Checklist

## Critical Items Before Running `deploy-oci-adb-complete.ps1`

### ✅ Secrets That MUST Be Created

The deployment script **MUST** create these secrets or they must exist:

1. **adb-credentials**
   ```yaml
   airflow-conn: "oracle+oracledb://..."
   mlflow-backend-store-uri: "postgresql://..."
   airflow-result-backend: "db+postgresql://..."
   admin-password: <ADB admin password>
   ```

2. **adb-wallet**
   - Must contain wallet files (wallet.zip contents extracted)
   - Mounted at `/opt/oracle/wallet`

3. **postgres-credentials**
   ```yaml
   username: postgres
   password: <secure password>
   mlflow-backend-store-uri: "postgresql://mlflow:password@postgres:5432/mlflow"
   ```

4. **object-storage-credentials**
   ```yaml
   aws_access_key_id: <your OCI Object Storage access key>
   aws_secret_access_key: <your OCI Object Storage secret>
   ```

5. **ocir-secret** (Image pull secret)
   - For pulling from OCIR registry

### ✅ ConfigMaps That MUST Be Created

1. **airflow-config**
   - Key: `AIRFLOW__CORE__EXECUTOR` = "CeleryExecutor"
   - Key: `AIRFLOW__CELERY__BROKER_URL` = "redis://redis:6379/0"

2. **object-storage-config**
   - Key: `s3-endpoint-url` = "https://axjkxzqfxgqu.compat.objectstorage.af-johannesburg-1.oraclecloud.com"

3. **mlflow-config**
   - Key: `MLFLOW_ARTIFACTS_DESTINATION` = "s3://mlops-artifacts/mlflow"

4. **app-config**
   - Should contain the mlflow experiment config

5. **inference-config**
   - Should contain inference service configuration

### ✅ Fixed Issues (Now in K8s Files)

These have been corrected:
- ✅ MLFlow health probe path: `/mlflow/` → `/` 
- ✅ Added startup probes to all services (tolerates slow app startup)
- ✅ Added failure thresholds to prevent aggressive restarts
- ✅ Flower health probes added
- ✅ Inference health probes added
- ✅ Redis now has data persistence (PVC)
- ✅ Postgres already has data persistence (StatefulSet)
- ✅ Airflow probes less aggressive (600s initial delay for startup)

### ⚠️ Services That Need Health Endpoints

Verify these apps have the following HTTP endpoints:

1. **MLFlow** (port 5000)
   - `GET /` - Should return 200 (used for liveness/readiness)

2. **Flower** (port 5555)
   - `GET /` - Should return 200 (Flower dashboard)

3. **Inference** (port 8000)
   - `GET /health` - Should return JSON health status

4. **FraudGuard** (port 5000)
   - `GET /api/health` - Should return health status

5. **Airflow Webserver** (port 8080)
   - `GET /` - Should return 200 (Airflow UI)

### 🔧 Post-Deployment Verification

After running the deployment script, verify:

```bash
# Check all pods are running
kubectl -n mlops get pods

# Check MLFlow connection
kubectl -n mlops exec mlflow-<pod-id> -- curl -v http://localhost:5000/

# Check Flower connection
kubectl -n mlops exec flower-<pod-id> -- curl -v http://localhost:5555/

# Check Inference endpoint
kubectl -n mlops exec inference-<pod-id> -- curl -v http://localhost:8000/health

# Check FraudGuard
kubectl -n mlops exec fraudguard-<pod-id> -- curl -v http://localhost:5000/api/health

# Check Airflow
kubectl -n mlops exec airflow-webserver-<pod-id> -- curl -v http://localhost:8080/
```

### 📋 Expected Status After Deployment

| Service | Image | Status | Health Check |
|---------|-------|--------|--------------|
| Airflow Webserver | airflow:2.10.1 | Running | `GET /` → 200 |
| Airflow Scheduler | airflow:2.10.1 | Running | Internal |
| Airflow Worker | airflow:2.10.1 | Running | Internal |
| Flower | airflow:latest | Running | `GET /` → 200 |
| MLFlow | mlflow:latest | Running | `GET /` → 200 |
| Inference | inference:latest | Running | `GET /health` → 200 |
| FraudGuard | fraudguard:latest | Running | `GET /api/health` → 200 |
| Postgres | postgres:16-alpine | Running | pg_isready |
| Redis | redis:7.2-bookworm | Running | TCP 6379 |

---

## What Changed in K8s Files

### Health Probe Improvements
- **Startup Probes**: Allow 2-3 minutes for apps to initialize
- **Readiness Probes**: Allow ingress traffic only when ready
- **Liveness Probes**: Restart only after 3+ consecutive failures
- **Proper Paths**: Corrected MLFlow from `/mlflow/` to `/`

### Persistence
- Redis now persists data with AOF (Append-Only File)
- Postgres already persists via StatefulSet

### Probe Tuning
- Longer startup periods before killing pods
- Proper failure thresholds (3-5 failures)
- Reasonable periods (30-60 seconds between checks)

---

## If Deployment Still Fails

1. **Check pod logs**: `kubectl -n mlops logs <pod-name> --tail=100`
2. **Check pod events**: `kubectl -n mlops describe pod <pod-name>`
3. **Check secrets exist**: `kubectl -n mlops get secrets`
4. **Check configmaps exist**: `kubectl -n mlops get configmaps`
5. **Check service discovery**: `kubectl -n mlops exec <pod> -- nslookup redis` (test DNS)

