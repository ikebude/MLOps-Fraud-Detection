# Azure Deployment Status

> 📖 **For detailed access instructions, see [AZURE_ACCESS_GUIDE.md](./AZURE_ACCESS_GUIDE.md)**

## Current Status: ✅ ALL SERVICES RUNNING

### Pod Status
All pods are now running successfully:
- ✅ Airflow Scheduler: Running
- ✅ Airflow Webserver: Running  
- ✅ Airflow Workers (2): Running
- ✅ Flower (Celery UI): Running
- ✅ MLflow: Running
- ✅ Inference: Running
- ✅ Fraud Guard: Running
- ✅ Redis: Running

### Service Endpoints

Get current IPs with:
```powershell
kubectl get svc -n mlops
```

### Azure Resources

**Resource Group: `mlops_fraud_analytics`**
- ACR: mlopsacr12345
- Storage: mlopsstorage12345
- PostgreSQL: mlops-postgres
- AKS Cluster: mlops-aks-cluster

**Managed Resource Group: `MC_mlops_fraud_analytics_mlops-aks-cluster_eastus2`**
- AKS Node VMs (auto-managed by Azure)
- Load Balancers
- Network resources

### PostgreSQL Databases (Active)

All databases are in use:
- ✅ **mlflow** - Used by MLflow service
- ✅ **airflow** - Used by Airflow (webserver, scheduler, workers)
- ✅ **postgres** - Available for other uses

### Cluster Configuration

- **Nodes**: 2 × Standard_D2s_v3 (2 vCPU, 8GB RAM each)
- **Total Capacity**: 4 vCPU, 16GB RAM
- **Namespace**: mlops

### Access URLs

Once LoadBalancer IPs are assigned:
- Fraud Guard: `http://<fraudguard-ip>:5000`
- Airflow: `http://<airflow-ip>:8080` (airflow/airflow)
- MLflow: `http://<mlflow-ip>:5000`
- Inference API: `http://<inference-ip>:8000`
- Flower: `http://<flower-ip>:5555`

### Quick Commands

```powershell
# Check pod status
kubectl get pods -n mlops

# Check services and IPs
kubectl get svc -n mlops

# View logs
kubectl logs -f deployment/<service-name> -n mlops

# Restart a service
kubectl rollout restart deployment/<service-name> -n mlops
```

---

**Last Updated**: After fixing connection strings and resource limits
**Status**: All services operational ✅
