# Troubleshooting Azure AKS Deployment Issues

This guide helps you diagnose and fix common issues with your Azure AKS deployment.

## Quick Diagnosis

Run the diagnostic script to identify issues:

```powershell
.\scripts\diagnose-azure-issues.ps1
```

This will check:
- ✅ kubectl connectivity
- ✅ Namespace and resources
- ✅ ConfigMaps and Secrets
- ✅ Pod status and health
- ✅ Service LoadBalancer IPs
- ✅ Airflow and MLflow configurations

## Common Issues and Solutions

### Issue 1: Services Stuck in "Pending" Status

**Symptoms:**
- Services show `<pending>` for EXTERNAL-IP in `kubectl get svc`
- Services show "Pending" status in Azure Portal

**Causes:**
1. **Azure Public IP Quota Exceeded** (Most Common)
   - Azure subscriptions have a default limit on public IP addresses
   - Each LoadBalancer service requires a public IP

2. **LoadBalancer Provisioning Delay**
   - Azure can take 5-10 minutes to provision LoadBalancers

**Solutions:**

#### Option A: Use Port Forwarding (Immediate Access)
```powershell
# Run the quick access script
.\scripts\quick-access-port-forward.ps1

# Or manually:
kubectl port-forward -n mlops svc/airflow-webserver 8080:8080
kubectl port-forward -n mlops svc/mlflow 5000:5000
kubectl port-forward -n mlops svc/fraudguard 5000:5000
```

Then access services at:
- Airflow: http://localhost:8080
- MLflow: http://localhost:5000
- Fraud Guard: http://localhost:5000

#### Option B: Check and Increase Azure Quota
1. Go to Azure Portal → Subscriptions → Your Subscription
2. Click "Usage + quotas"
3. Search for "Public IP addresses"
4. Check current usage vs. limit
5. Click "Request increase" if needed

#### Option C: Use Ingress Controller (Recommended for Production)
Instead of multiple LoadBalancers, use a single Ingress Controller:
- One public IP for all services
- More cost-effective
- Better for production

### Issue 2: MLflow Not Working

**Symptoms:**
- MLflow has an external IP but UI doesn't load
- Pod keeps restarting
- Connection errors in logs

**Diagnosis:**
```powershell
# Check pod status
kubectl get pods -n mlops -l app=mlflow

# Check logs
kubectl logs -f deployment/mlflow -n mlops

# Check service
kubectl describe svc mlflow -n mlops
```

**Common Causes:**

1. **Database Connection Issues**
   ```powershell
   # Verify PostgreSQL firewall allows AKS IPs
   # Check connection string in ConfigMap
   kubectl get configmap mlflow-config -n mlops -o yaml
   ```

2. **Azure Storage Credentials Missing**
   ```powershell
   # Verify storage secret exists
   kubectl get secret storage-credentials -n mlops
   
   # Check if secret has correct keys
   kubectl get secret storage-credentials -n mlops -o jsonpath='{.data}'
   ```

3. **Pod Resource Limits**
   ```powershell
   # Check if pod is being killed due to memory
   kubectl describe pod -l app=mlflow -n mlops
   ```

**Fix:**
```powershell
# Restart MLflow
kubectl rollout restart deployment/mlflow -n mlops

# Wait for it to be ready
kubectl wait --for=condition=available --timeout=300s deployment/mlflow -n mlops
```

### Issue 3: Airflow Not Working / Can't Trigger DAGs

**Symptoms:**
- Airflow UI loads but shows errors
- Can't see DAGs
- Can't trigger DAGs
- Database connection errors

**Diagnosis:**
```powershell
# Check all Airflow pods
kubectl get pods -n mlops -l 'app in (airflow-webserver,airflow-scheduler,airflow-worker)'

# Check webserver logs
kubectl logs -f deployment/airflow-webserver -n mlops

# Check scheduler logs
kubectl logs -f deployment/airflow-scheduler -n mlops

# Check database connection
kubectl exec -it deployment/airflow-webserver -n mlops -- airflow db check
```

**Common Causes:**

1. **Database Not Initialized**
   ```powershell
   # Initialize database manually
   kubectl exec -it deployment/airflow-webserver -n mlops -- airflow db init
   
   # Or upgrade database
   kubectl exec -it deployment/airflow-webserver -n mlops -- airflow db upgrade
   ```

2. **Missing ConfigMap**
   ```powershell
   # Verify airflow-config exists
   kubectl get configmap airflow-config -n mlops
   
   # Check contents
   kubectl get configmap airflow-config -n mlops -o yaml
   ```

3. **Redis Connection Issues** (for CeleryExecutor)
   ```powershell
   # Check Redis pod
   kubectl get pods -n mlops -l app=redis
   
   # Test Redis connection
   kubectl exec -it deployment/redis -n mlops -- redis-cli ping
   ```

4. **DAGs Not Loading**
   ```powershell
   # Verify DAGs ConfigMap exists
   kubectl get configmap airflow-dags -n mlops
   
   # Check DAG files
   kubectl exec -it deployment/airflow-webserver -n mlops -- ls -la /opt/airflow/dags
   ```

**Fix:**
```powershell
# Run the fix script
.\scripts\fix-azure-services.ps1

# Or manually restart Airflow components
kubectl rollout restart deployment/airflow-webserver -n mlops
kubectl rollout restart deployment/airflow-scheduler -n mlops
kubectl rollout restart deployment/airflow-worker -n mlops

# Wait for all to be ready
kubectl wait --for=condition=available --timeout=300s deployment/airflow-webserver -n mlops
kubectl wait --for=condition=available --timeout=300s deployment/airflow-scheduler -n mlops
```

### Issue 4: Pods Not Starting / Image Pull Errors

**Symptoms:**
- Pods stuck in "ImagePullBackOff" or "ErrImagePull"
- Pods in "Pending" state

**Diagnosis:**
```powershell
# Check pod events
kubectl describe pod <pod-name> -n mlops

# Check for image pull errors
kubectl get events -n mlops --sort-by='.lastTimestamp'
```

**Common Causes:**

1. **ACR Secret Missing or Invalid**
   ```powershell
   # Check if secret exists
   kubectl get secret acr-secret -n mlops
   
   # Recreate if needed
   az acr credential show --name mlopsacr12345
   kubectl create secret docker-registry acr-secret \
     --docker-server=mlopsacr12345.azurecr.io \
     --docker-username=mlopsacr12345 \
     --docker-password=<password> \
     -n mlops
   ```

2. **Image Doesn't Exist in ACR**
   ```powershell
   # List images in ACR
   az acr repository list --name mlopsacr12345
   
   # Check specific image
   az acr repository show-tags --name mlopsacr12345 --repository fraud-detection/airflow
   ```

3. **AKS Doesn't Have ACR Access**
   ```powershell
   # Attach ACR to AKS
   az aks update --name mlops-aks-cluster \
     --resource-group mlops_fraud_analytics \
     --attach-acr mlopsacr12345
   ```

**Fix:**
```powershell
# Run the fix script which handles ACR secret
.\scripts\fix-azure-services.ps1
```

### Issue 5: Services Have IPs But Can't Access

**Symptoms:**
- Services have external IPs assigned
- Can't connect from browser
- Connection timeout

**Diagnosis:**
```powershell
# Check if pods are actually running
kubectl get pods -n mlops

# Check service endpoints
kubectl get endpoints -n mlops

# Test from within cluster
kubectl run -it --rm debug --image=busybox --restart=Never -n mlops -- wget -O- http://mlflow:5000
```

**Common Causes:**

1. **Pods Not Ready**
   - Service has IP but no healthy pods
   - Check pod status and logs

2. **Firewall/Network Security Group Rules**
   - Azure NSG blocking traffic
   - Check NSG rules in Azure Portal

3. **Service Port Mismatch**
   - Service port doesn't match container port
   - Check service and deployment configurations

**Fix:**
```powershell
# Check pod health
kubectl get pods -n mlops -o wide

# Restart unhealthy pods
kubectl delete pod <pod-name> -n mlops

# Check service configuration
kubectl get svc -n mlops -o yaml
```

## Quick Fix Commands

### Restart All Services
```powershell
.\scripts\fix-azure-services.ps1
```

### Access Services Immediately
```powershell
.\scripts\quick-access-port-forward.ps1
```

### Full Diagnostic
```powershell
.\scripts\diagnose-azure-issues.ps1
```

## Getting Help

If issues persist:

1. **Collect Information:**
   ```powershell
   # Save diagnostic output
   .\scripts\diagnose-azure-issues.ps1 | Out-File diagnostics.txt
   
   # Get pod logs
   kubectl logs deployment/airflow-webserver -n mlops > airflow-logs.txt
   kubectl logs deployment/mlflow -n mlops > mlflow-logs.txt
   ```

2. **Check Azure Resources:**
   - AKS cluster health in Azure Portal
   - PostgreSQL firewall rules
   - Storage account access
   - Public IP quota

3. **Verify Configuration:**
   - All ConfigMaps and Secrets exist
   - Database connection strings are correct
   - Storage credentials are valid
   - ACR images are pushed

## Prevention

To avoid these issues:

1. **Check Quotas Before Deployment**
   - Verify public IP quota is sufficient
   - Consider using Ingress instead of LoadBalancer

2. **Verify All Resources Exist**
   - Run diagnostics before deployment
   - Ensure ACR images are built and pushed

3. **Monitor Pod Health**
   - Regularly check pod status
   - Monitor logs for errors

4. **Use Health Checks**
   - Configure liveness and readiness probes
   - Monitor service endpoints
