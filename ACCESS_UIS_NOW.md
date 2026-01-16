# Access Your UIs Right Now

## ✅ Working Services (Access These Now)

The port forwarding script should be running. Access these UIs:

### 1. MLflow UI
- **URL**: http://localhost:5000
- **Status**: ✅ Working
- **What you'll see**: Model registry, experiments, runs

### 2. Inference API
- **URL**: http://localhost:8000
- **Status**: ✅ Working  
- **Test it**: http://localhost:8000/health
- **What you'll see**: REST API for fraud detection

### 3. Fraud Guard UI
- **URL**: http://localhost:5001
- **Status**: ✅ Working
- **What you'll see**: Dashboard, fraud detection monitoring

### 4. Redis (Internal)
- **Status**: ✅ Working (internal service)

## ⚠️ Services Needing Fix

### Airflow
- **Status**: CrashLoopBackOff (needs database fix)
- **Fix**: Run `.\scripts\fix-airflow-database.ps1`

### Flower
- **Status**: Error (depends on Airflow/Redis)
- **Fix**: Will work once Airflow is fixed

## Quick Access Commands

If port forwarding isn't running, use these:

```powershell
# MLflow
kubectl port-forward -n mlops svc/mlflow 5000:5000

# Inference API  
kubectl port-forward -n mlops svc/inference 8000:8000

# Fraud Guard
kubectl port-forward -n mlops svc/fraudguard 5001:5000
```

## Next: Set Up Ingress for Production

Once you've verified the UIs work, run:

```powershell
.\scripts\setup-ingress-simple.ps1
```

This will give you a single external IP for all services!
