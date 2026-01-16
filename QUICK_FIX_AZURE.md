# Quick Fix Guide for Azure AKS Issues

## 🚨 Immediate Access (No External IPs Needed)

If your services are stuck in "Pending" status, use port forwarding for immediate access:

```powershell
# Run this script to access all services
.\scripts\quick-access-port-forward.ps1
```

This will give you access to:
- **Airflow**: http://localhost:8080 (username: `airflow`, password: `airflow`)
- **MLflow**: http://localhost:5000
- **Fraud Guard**: http://localhost:5000
- **Inference API**: http://localhost:8000
- **Flower**: http://localhost:5555

## 🔍 Diagnose Issues

Run the diagnostic script to identify problems:

```powershell
.\scripts\diagnose-azure-issues.ps1
```

This checks:
- ✅ Cluster connectivity
- ✅ Pod status
- ✅ Service IPs
- ✅ ConfigMaps and Secrets
- ✅ Airflow and MLflow health

## 🔧 Fix Common Issues

Run the fix script to automatically resolve common problems:

```powershell
.\scripts\fix-azure-services.ps1
```

This will:
- ✅ Create missing ACR secrets
- ✅ Restart all services
- ✅ Wait for services to be ready
- ✅ Show service status

## 📋 Manual Commands

### Check Service Status
```powershell
# Check all services
kubectl get svc -n mlops

# Check pod status
kubectl get pods -n mlops

# Check specific service IP
kubectl get svc airflow-webserver -n mlops -o jsonpath='{.status.loadBalancer.ingress[0].ip}'
```

### Check Pod Logs
```powershell
# Airflow webserver
kubectl logs -f deployment/airflow-webserver -n mlops

# MLflow
kubectl logs -f deployment/mlflow -n mlops

# Fraud Guard
kubectl logs -f deployment/fraudguard -n mlops
```

### Restart Services
```powershell
# Restart all Airflow components
kubectl rollout restart deployment/airflow-webserver -n mlops
kubectl rollout restart deployment/airflow-scheduler -n mlops
kubectl rollout restart deployment/airflow-worker -n mlops

# Restart MLflow
kubectl rollout restart deployment/mlflow -n mlops

# Restart Fraud Guard
kubectl rollout restart deployment/fraudguard -n mlops
```

### Fix Airflow Database
```powershell
# Check database connection
kubectl exec -it deployment/airflow-webserver -n mlops -- airflow db check

# Initialize database (if needed)
kubectl exec -it deployment/airflow-webserver -n mlops -- airflow db init

# Upgrade database
kubectl exec -it deployment/airflow-webserver -n mlops -- airflow db upgrade
```

## 🎯 Common Issues

### Services Stuck in "Pending"
**Cause**: Azure public IP quota exceeded or provisioning delay

**Solution**: 
1. Use port forwarding (see above)
2. Check Azure quota: Portal → Subscriptions → Usage + quotas → "Public IP addresses"
3. Request quota increase if needed

### MLflow Not Working
**Check**:
```powershell
kubectl logs deployment/mlflow -n mlops
kubectl get pods -n mlops -l app=mlflow
```

**Fix**:
```powershell
kubectl rollout restart deployment/mlflow -n mlops
```

### Airflow Can't Trigger DAGs
**Check**:
```powershell
kubectl logs deployment/airflow-webserver -n mlops
kubectl logs deployment/airflow-scheduler -n mlops
```

**Fix**:
```powershell
# Restart Airflow
kubectl rollout restart deployment/airflow-webserver -n mlops
kubectl rollout restart deployment/airflow-scheduler -n mlops

# Check database
kubectl exec -it deployment/airflow-webserver -n mlops -- airflow db check
```

### Pods Not Starting
**Check**:
```powershell
kubectl describe pod <pod-name> -n mlops
kubectl get events -n mlops --sort-by='.lastTimestamp'
```

**Common fixes**:
- Missing ACR secret: `.\scripts\fix-azure-services.ps1`
- Image pull errors: Check ACR access
- Resource limits: Check node capacity

## 📚 More Help

For detailed troubleshooting, see:
- [TROUBLESHOOTING_AZURE.md](./TROUBLESHOOTING_AZURE.md) - Comprehensive troubleshooting guide
- [AZURE_ACCESS_GUIDE.md](./AZURE_ACCESS_GUIDE.md) - Access methods and endpoints

## ✅ Verification Checklist

After fixing issues, verify:

- [ ] All pods are running: `kubectl get pods -n mlops`
- [ ] Services have IPs or use port-forwarding
- [ ] Airflow UI loads and shows DAGs
- [ ] MLflow UI loads
- [ ] Can trigger DAGs in Airflow
- [ ] Fraud Guard UI loads

## 🆘 Still Having Issues?

1. Run diagnostics: `.\scripts\diagnose-azure-issues.ps1`
2. Check logs for errors
3. Verify Azure resources (PostgreSQL, Storage, ACR)
4. Review [TROUBLESHOOTING_AZURE.md](./TROUBLESHOOTING_AZURE.md)
