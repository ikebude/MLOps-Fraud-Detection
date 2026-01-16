# Quick Deploy Guide

Fastest way to deploy to Azure with your configured settings.

## Your Azure Configuration

- **Resource Group**: `mlops_fraud_analytics`
- **AKS Cluster**: `mlops_aks_cluster`
- **ACR**: `mlopsacr12345.azurecr.io`

## One-Command Deployment

### Windows (PowerShell)

```powershell
.\scripts\deploy-azure-complete.ps1
```

Just press Enter when prompted to use defaults!

### Linux/Mac/Git Bash

```bash
chmod +x scripts/deploy-azure-complete.sh
./scripts/deploy-azure-complete.sh
```

Press Enter when prompted to use defaults!

## What Happens

1. ✅ Logs in to Azure and ACR
2. ✅ Builds 4 Docker images (Airflow, MLflow, Inference, Fraud Guard)
3. ✅ Pushes images to ACR
4. ✅ Connects to your AKS cluster
5. ✅ Deploys all services
6. ✅ Shows you all UI endpoints

## After Deployment

The script will show you URLs like:

```
Fraud Guard:    http://<ip>:5000
Airflow:       http://<ip>:8080
MLflow:         http://<ip>:5000
Inference API: http://<ip>:8000
Flower:         http://<ip>:5555
```

## Get Service IPs Later

```powershell
# PowerShell
kubectl get svc -n mlops

# Or get specific IPs
kubectl get svc fraudguard -n mlops -o jsonpath='{.status.loadBalancer.ingress[0].ip}'
kubectl get svc airflow-webserver -n mlops -o jsonpath='{.status.loadBalancer.ingress[0].ip}'
kubectl get svc mlflow -n mlops -o jsonpath='{.status.loadBalancer.ingress[0].ip}'
kubectl get svc inference -n mlops -o jsonpath='{.status.loadBalancer.ingress[0].ip}'
kubectl get svc flower -n mlops -o jsonpath='{.status.loadBalancer.ingress[0].ip}'
```

## Next Steps

1. **Wait for LoadBalancer IPs** (may take 2-5 minutes)
   ```powershell
   kubectl get svc -n mlops -w
   ```

2. **Access Fraud Guard UI**
   - Open the Fraud Guard URL in your browser
   - Verify all services are healthy

3. **Login to Airflow**
   - Open the Airflow URL
   - Login with `airflow` / `airflow`
   - Find `fraud_detection_training` DAG
   - Toggle it ON and click "Trigger DAG"

4. **Monitor Training**
   - Watch DAG progress in Airflow
   - View experiments in MLflow
   - Check worker status in Flower

## Troubleshooting

### Check Pod Status
```powershell
kubectl get pods -n mlops
```

### View Logs
```powershell
kubectl logs -f deployment/fraudguard -n mlops
kubectl logs -f deployment/airflow-webserver -n mlops
kubectl logs -f deployment/mlflow -n mlops
```

### Restart a Service
```powershell
kubectl rollout restart deployment/<service-name> -n mlops
```

---

**Ready?** Just run `.\scripts\deploy-azure-complete.ps1` and press Enter! 🚀
