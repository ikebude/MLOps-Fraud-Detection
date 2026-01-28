# POST-DEPLOYMENT AUDIT REPORT
## Critical Issues Found & Fixes

### 🔴 CRITICAL ISSUES

#### 1. **MLFlow Health Probe Path WRONG**
- **File**: `k8s/mlflow.yaml`
- **Problem**: Health probe uses `/mlflow/` but MLFlow runs at `/`
- **Impact**: Pod will fail liveness/readiness probes → CrashLoopBackOff
- **Fix**: Change probe path to `/` (root)

#### 2. **Flower Missing Health Probes**
- **File**: `k8s/flower.yaml`
- **Problem**: No liveness/readiness probes defined
- **Impact**: Kubernetes won't know if pod is healthy
- **Fix**: Add HTTP health probes on port 5555

#### 3. **Inference Missing Health Probes**
- **File**: `k8s/inference.yaml`
- **Problem**: No liveness/readiness probes defined
- **Impact**: Pod failures won't be detected
- **Fix**: Add HTTP health probes on port 8000

#### 4. **FraudGuard Health Endpoint Path**
- **File**: `k8s/fraudguard.yaml`
- **Problem**: Uses `/api/health` - need to verify app has this endpoint
- **Impact**: Pod restart loops if endpoint doesn't exist
- **Fix**: Verify Flask app has `/api/health` route

#### 5. **Airflow Init Container References Wrong ConfigMap**
- **File**: `k8s/airflow-adb.yaml` line 38
- **Problem**: References `airflow-config` but should check what key exists
- **Impact**: Init container fails → pod never starts
- **Fix**: Verify `airflow-config` ConfigMap has `AIRFLOW__CORE__EXECUTOR` key

#### 6. **Airflow App-Config ConfigMap Reference is Optional but Referenced**
- **File**: `k8s/airflow-adb.yaml` line 156
- **Problem**: `app-config` is optional but if not created, app fails
- **Impact**: Silent failures if ConfigMap missing
- **Fix**: Make it required or ensure deployment script creates it

#### 7. **Postgres Data Not Persistent**
- **File**: `k8s/postgres.yaml`
- **Problem**: Postgres uses `emptyDir` for data → lost on pod restart
- **Impact**: All data lost, ML models lost, training progress lost
- **Fix**: Create PVC for postgres data persistence

#### 8. **Redis Data Not Persistent**
- **File**: `k8s/redis.yaml`
- **Problem**: Redis uses `emptyDir` → celery task queue lost on restart
- **Impact**: In-progress tasks lost, Airflow DAG state corrupted
- **Fix**: Create PVC for redis data persistence

#### 9. **Missing Startup Probes**
- **Files**: All deployments
- **Problem**: No startup probes - apps might be killed before ready
- **Impact**: Apps take time to initialize → get SIGKILL
- **Fix**: Add 60-120 second startup probes

#### 10. **Airflow Liveness Probe Too Aggressive**
- **File**: `k8s/airflow-adb.yaml` line 147
- **Problem**: 300s initial delay, but 60s periods with 5 failures = 8 minutes to kill
- **Impact**: Long app startup times cause restarts
- **Fix**: Increase failure threshold to 10 or initial delay to 600s

### 🟠 HIGH PRIORITY ISSUES

#### 11. **Missing Service Readiness (Airflow Workers)**
- **File**: `k8s/airflow-adb.yaml`
- **Problem**: No health checks on Celery workers
- **Impact**: Bad workers stay in rotation → DAGs fail
- **Fix**: Add health check endpoints to Airflow worker image

#### 12. **Inference ConfigMap Missing**
- **File**: `k8s/inference.yaml`
- **Problem**: References `inference-config` but not in manifests
- **Impact**: Pod won't start - ConfigMap not found
- **Fix**: Verify `inference-config` is created by deployment script

#### 13. **App-Config ConfigMap Not Provided**
- **File**: `k8s/airflow-configmap.yaml`
- **Problem**: References `app-config` but file named `airflow-app-config`
- **Impact**: ConfigMap reference fails
- **Fix**: Rename to `app-config` or update references

#### 14. **Missing Required Secrets**
- **Problem**: These secrets must exist before deployment:
  - `adb-credentials` (Airflow + MLFlow)
  - `adb-wallet` (Airflow)
  - `postgres-credentials` (MLFlow)
  - `object-storage-credentials` (All)
  - `object-storage-config` (All)
- **Impact**: Pods won't start - secret reference errors
- **Fix**: Deployment script MUST create all secrets first

#### 15. **MLFlow Postgres Connection String Missing**
- **File**: `k8s/mlflow.yaml`
- **Problem**: References `postgres-credentials` key `mlflow-backend-store-uri` but might not exist
- **Impact**: MLFlow can't connect to Postgres
- **Fix**: Ensure secret has this key with full connection string

### 🟡 MEDIUM PRIORITY ISSUES

#### 16. **No Pod Disruption Budgets**
- **Problem**: Cluster updates will immediately kill pods
- **Impact**: Data loss, incomplete DAGs
- **Fix**: Add PDB resources for critical deployments

#### 17. **No Init Container to Wait for Dependencies**
- **Problem**: Pods start before dependencies (Postgres, Redis, MLFlow) are ready
- **Impact**: Race conditions, connection timeouts
- **Fix**: Add init containers with network tests

#### 18. **Airflow Workers Missing Proper Config**
- **File**: `k8s/airflow-adb.yaml`
- **Problem**: Worker replicas/concurrency not defined
- **Impact**: Bottleneck in DAG execution
- **Fix**: Add replicas for worker pool scaling

#### 19. **No Resource Limits on Airflow Scheduler**
- **File**: `k8s/airflow-adb.yaml`
- **Problem**: Scheduler could consume all resources
- **Impact**: Other pods evicted
- **Fix**: Add CPU/memory limits to scheduler

#### 20. **Missing Graceful Shutdown**
- **Problem**: `terminationGracePeriodSeconds` too short
- **Impact**: In-flight DAGs terminated abruptly
- **Fix**: Set to at least 60 seconds

---

## PRIORITY FIX ORDER

1. ✅ Fix MLFlow probe path (quick win)
2. ✅ Add health probes to Flower & Inference
3. ✅ Create PVCs for Postgres & Redis
4. ✅ Verify all ConfigMaps match references
5. ✅ Verify all Secrets are defined
6. ✅ Add startup probes to all deployments
7. ✅ Create init containers for dependency checks
8. ✅ Adjust liveness probe thresholds

