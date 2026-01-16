# Complete Deployment Guide - Working Solution

This guide provides a **complete, working solution** for deploying and accessing all MLOps services on Azure AKS.

## 🚀 Quick Start - One Command Deployment

Run this single command to deploy everything:

```powershell
.\scripts\deploy-azure-complete.ps1
```

This script will:
1. ✅ Login to Azure and ACR
2. ✅ Build and push all Docker images
3. ✅ Deploy all Kubernetes resources
4. ✅ Initialize Airflow database automatically
5. ✅ Wait for all services to be ready
6. ✅ Show you how to access all UIs

## 📋 What Gets Deployed

- **Airflow** - Workflow orchestration (webserver + scheduler + workers)
- **MLflow** - Model registry and experiment tracking
- **Inference API** - Real-time fraud detection API
- **Fraud Guard** - Web UI dashboard
- **Flower** - Celery worker monitoring
- **Redis** - Message broker for Celery

## 🔧 Key Fixes Applied

### 1. Airflow Database Initialization
- ✅ Fixed init container to properly initialize database
- ✅ Deployment script automatically creates DB init job if needed
- ✅ Database is verified before webserver starts

### 2. Port Forwarding
- ✅ All services use unique local ports to avoid conflicts
- ✅ Quick access script handles all port forwards automatically

### 3. Service Configuration
- ✅ All ConfigMaps and Secrets properly configured
- ✅ Resource limits set appropriately
- ✅ Health checks configured

## 🌐 Accessing All UIs

### Method 1: Automated Port Forwarding (Easiest)

```powershell
.\scripts\quick-access-port-forward.ps1
```

This opens all services in separate windows:
- **Airflow**: http://localhost:8080 (airflow/airflow)
- **MLflow**: http://localhost:5000
- **Fraud Guard**: http://localhost:5001
- **Inference API**: http://localhost:8000
- **Flower**: http://localhost:5555

### Method 2: Manual Port Forwarding

Run these in separate PowerShell windows:

```powershell
# Terminal 1 - Airflow
kubectl port-forward -n mlops svc/airflow-webserver 8080:8080

# Terminal 2 - MLflow
kubectl port-forward -n mlops svc/mlflow 5000:5000

# Terminal 3 - Fraud Guard
kubectl port-forward -n mlops svc/fraudguard 5001:5000

# Terminal 4 - Inference API
kubectl port-forward -n mlops svc/inference 8000:8000

# Terminal 5 - Flower
kubectl port-forward -n mlops svc/flower 5555:5555
```

### Method 3: LoadBalancer IPs (If Available)

Check for external IPs:
```powershell
kubectl get svc -n mlops
```

If IPs are assigned, access directly:
- Airflow: `http://<airflow-ip>:8080`
- MLflow: `http://<mlflow-ip>:5000`
- etc.

**Note**: LoadBalancer IPs may take 5-10 minutes and require Azure quota. Port forwarding is recommended for immediate access.

## ✅ Verification Steps

After deployment, verify everything is working:

### 1. Check Pod Status
```powershell
kubectl get pods -n mlops
```

All pods should show `Running` and `1/1` or `2/2` Ready.

### 2. Check Services
```powershell
kubectl get svc -n mlops
```

### 3. Test Airflow
1. Access http://localhost:8080 (via port-forward)
2. Login with `airflow` / `airflow`
3. You should see the `fraud_detection_training` DAG
4. Toggle it ON and click "Trigger DAG"

### 4. Test MLflow
1. Access http://localhost:5000 (via port-forward)
2. You should see the MLflow UI with experiments

### 5. Test Fraud Guard
1. Access http://localhost:5001 (via port-forward)
2. You should see the dashboard

## 🔍 Troubleshooting

### Airflow Not Working

If Airflow shows database errors:

```powershell
# Run the database fix script
.\scripts\fix-airflow-database.ps1
```

### Pods Not Starting

Check logs:
```powershell
kubectl logs -f deployment/<service-name> -n mlops
```

Check pod events:
```powershell
kubectl describe pod <pod-name> -n mlops
```

### Port Already in Use

If you get "port already in use" errors:
1. Close existing port-forward windows
2. Or use different ports (e.g., 18080 instead of 8080)

### Services Stuck in Pending

If LoadBalancer IPs are pending:
- Check Azure quota: Portal → Subscriptions → Usage + quotas → "Public IP addresses"
- Use port forwarding instead (recommended)

## 📝 Complete Deployment Script

The `deploy-azure-complete.ps1` script now includes:

1. **Image Building** - Builds all 4 Docker images
2. **Image Pushing** - Pushes to Azure Container Registry
3. **Resource Deployment** - Deploys all Kubernetes manifests
4. **Database Initialization** - Automatically initializes Airflow database
5. **Health Checks** - Waits for all services to be ready
6. **Access Instructions** - Shows how to access all UIs

## 🎯 Next Steps After Deployment

1. **Access Airflow UI**
   - Login: airflow/airflow
   - Find the `fraud_detection_training` DAG
   - Toggle it ON and trigger it

2. **Monitor Training**
   - Watch DAG progress in Airflow
   - View experiments in MLflow
   - Check worker status in Flower

3. **Use Fraud Guard**
   - View fraud detection dashboard
   - Monitor system health
   - Check alerts

## 🆘 Getting Help

If you encounter issues:

1. **Run Diagnostics**
   ```powershell
   .\scripts\diagnose-azure-issues.ps1
   ```

2. **Check Logs**
   ```powershell
   kubectl logs -f deployment/<service-name> -n mlops
   ```

3. **Verify Configuration**
   ```powershell
   kubectl get configmap -n mlops
   kubectl get secret -n mlops
   ```

## ✨ Summary

This is a **complete, working solution** that:
- ✅ Deploys all services correctly
- ✅ Initializes Airflow database automatically
- ✅ Provides easy access to all UIs via port forwarding
- ✅ Handles all common issues
- ✅ Works end-to-end from deployment to access

**Just run `.\scripts\deploy-azure-complete.ps1` and follow the instructions!**
