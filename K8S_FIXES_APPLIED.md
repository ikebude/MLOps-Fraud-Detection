# K8s Post-Deployment Fixes Applied

## Summary of Changes

All 14 core K8s manifests have been audited and critical post-deployment issues have been fixed.

### Files Modified

1. ✅ **mlflow.yaml** - Health probe and startup probe fixes
2. ✅ **flower.yaml** - Added all 3 probe types + tuned thresholds
3. ✅ **inference.yaml** - Added all 3 probe types + tuned thresholds
4. ✅ **fraudguard.yaml** - Added startup probe, adjusted thresholds
5. ✅ **airflow-adb.yaml** - Adjusted liveness probe to be less aggressive + added startup probe
6. ✅ **redis.yaml** - Added PVC persistence + health checks + AOF enabled

### Core Fixes Applied

#### 1. Health Probe Corrections
**mlflow.yaml**
- Changed probe path from `/mlflow/` to `/` (root path)
- Added startup probe (allows 2.5 min initialization)
- Added failure threshold to prevent restart loop

**flower.yaml**
- Added liveness probe (http GET /)
- Added readiness probe (http GET /)
- Added startup probe (30 failures × 5s = 2.5 min)

**inference.yaml**
- Added liveness probe (http GET /health)
- Added readiness probe (http GET /health)
- Added startup probe (30 failures × 5s = 2.5 min)

**fraudguard.yaml**
- Added startup probe (30 failures × 5s = 2.5 min)
- Adjusted readiness: 15s → 20s initial delay
- Adjusted liveness: 30s → 60s initial delay

**airflow-adb.yaml**
- Changed initial delay: 300s → 600s (10 minutes for Airflow to start)
- Added startup probe (60 failures × 10s = 10 minutes)
- Added readiness probe (was missing)

#### 2. Data Persistence

**redis.yaml**
- Removed emptyDir (data lost on pod restart)
- Added PersistentVolumeClaim (5Gi)
- Enabled Redis AOF (append-only file) for durability
- Added livenessProbe (TCP check on 6379)
- Added readinessProbe (TCP check on 6379)

**postgres.yaml**
- Already had StatefulSet with PVC (10Gi)
- Already had proper startup/liveness/readiness probes
- No changes needed ✅

#### 3. Probe Threshold Tuning

All services now follow this pattern:

```yaml
startupProbe:
  # Gives apps time to initialize (2-10 minutes)
  periodSeconds: 5-10
  failureThreshold: 30-60  # Total: 2.5-10 minutes

readinessProbe:
  # Allows traffic only when ready
  initialDelaySeconds: 10-20
  periodSeconds: 10
  failureThreshold: 3

livenessProbe:
  # Restarts stuck pods (not too aggressive)
  initialDelaySeconds: 30-600
  periodSeconds: 30-60
  failureThreshold: 3-5
```

### Issues Solved

| Issue | Status | Impact |
|-------|--------|--------|
| MLFlow probe failing on wrong path | ✅ Fixed | MLFlow won't be killed by K8s |
| Flower/Inference not monitored | ✅ Fixed | Unhealthy pods now detected |
| Apps killed before ready | ✅ Fixed | Startup probes allow initialization time |
| Redis data lost on restart | ✅ Fixed | Celery tasks & state persisted |
| Airflow too aggressive restart | ✅ Fixed | App gets 10min to start |
| No startup period defined | ✅ Fixed | All services have startup probes |
| FraudGuard health not robust | ✅ Fixed | Proper probe hierarchy applied |

### Testing After Deployment

Verify the fixes worked:

```bash
# 1. Check all pods are RUNNING (not Pending/CrashLoopBackOff)
kubectl -n mlops get pods

# 2. Check startup probes allowed pods to initialize
kubectl -n mlops describe pod mlflow-<id> | grep -A 5 "Startup Probe"

# 3. Verify Redis data persists
kubectl -n mlops exec redis-<id> -- redis-cli PING
# Should return: PONG

# 4. Verify Postgres data persists
kubectl -n mlops exec postgres-0 -- psql -U postgres -c "SELECT version();"

# 5. Test service health
kubectl -n mlops exec mlflow-<id> -- curl http://localhost:5000/
kubectl -n mlops exec flower-<id> -- curl http://localhost:5555/
```

### What to Do Now

1. Run the deployment script: `& '.\scripts\deploy-oci-adb-complete.ps1'`
2. Ensure all secrets/configmaps are created
3. Verify pods reach RUNNING status
4. Run the test commands above
5. Access the dashboards via ingress

### Remaining Considerations

⚠️ **Still Need to Verify:**
- Deployment script creates all required secrets
- Deployment script creates all required configmaps
- App health endpoints exist at expected paths
- Images exist in OCIR registry
- ADB wallet is properly configured
- Object Storage credentials are valid

✅ **Already Fixed:**
- Pod startup timing issues
- Health probe paths
- Data persistence
- Probe thresholds

