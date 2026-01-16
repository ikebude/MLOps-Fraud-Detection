# Windows Deployment Instructions

Since you're on Windows, use one of these methods to deploy:

## Option 1: PowerShell Script (Recommended)

Run the PowerShell version of the deployment script:

```powershell
.\scripts\deploy-azure-complete.ps1
```

The script uses these defaults:
- AKS Resource Group: `mlops_fraud_analytics`
- AKS Cluster Name: `mlops_aks_cluster`

It will prompt to confirm or override these defaults.

Or set them as environment variables:
```powershell
$env:AKS_RESOURCE_GROUP = "mlops_fraud_analytics"
$env:AKS_CLUSTER_NAME = "mlops_aks_cluster"
.\scripts\deploy-azure-complete.ps1
```

## Option 2: Git Bash or WSL

If you have Git Bash or WSL installed:

```bash
# In Git Bash or WSL
chmod +x scripts/deploy-azure-complete.sh
./scripts/deploy-azure-complete.sh
```

## Option 3: Manual Steps (PowerShell)

Run each step manually:

```powershell
# 1. Login to Azure
az login

# 2. Login to ACR
az acr login --name mlopsacr12345

# 3. Build and push images (run from project root)
cd src\airflow
docker build -t mlopsacr12345.azurecr.io/fraud-detection/airflow:latest .
docker push mlopsacr12345.azurecr.io/fraud-detection/airflow:latest

cd ..\mlflow
docker build -t mlopsacr12345.azurecr.io/fraud-detection/mlflow:latest .
docker push mlopsacr12345.azurecr.io/fraud-detection/mlflow:latest

cd ..\inference
docker build -t mlopsacr12345.azurecr.io/fraud-detection/inference:latest .
docker push mlopsacr12345.azurecr.io/fraud-detection/inference:latest

cd ..\..\fraudguard
docker build -t mlopsacr12345.azurecr.io/fraud-detection/fraudguard:latest .
docker push mlopsacr12345.azurecr.io/fraud-detection/fraudguard:latest

cd ..

# 4. Get AKS credentials
az aks get-credentials --resource-group mlops_fraud_analytics --name mlops_aks_cluster

# 5. Create namespace
kubectl create namespace mlops --dry-run=client -o yaml | kubectl apply -f -

# 6. Create ACR secret
kubectl create secret docker-registry acr-secret `
  --docker-server=mlopsacr12345.azurecr.io `
  --docker-username=mlopsacr12345 `
  --docker-password='Tfs3lQolzy3n4GGvwpgjmJIlCP0wWDsRLSjiHmA/HZ+ACRC0hFnV' `
  --namespace=mlops

# 7. Deploy all services
kubectl apply -f k8s\secrets.yaml
kubectl apply -f k8s\redis.yaml
kubectl apply -f k8s\mlflow.yaml
kubectl apply -f k8s\inference-config.yaml
kubectl apply -f k8s\inference.yaml
kubectl apply -f k8s\airflow.yaml
kubectl apply -f k8s\flower.yaml
kubectl apply -f k8s\fraudguard.yaml

# 8. Check service status
kubectl get svc -n mlops
kubectl get pods -n mlops
```

## Prerequisites

Make sure you have:
- Azure CLI installed: `az --version`
- Docker Desktop running: `docker --version`
- kubectl installed: `kubectl version --client`
- PowerShell 5.1+ or PowerShell Core

## Troubleshooting

### PowerShell Execution Policy

If you get an execution policy error:

```powershell
# Check current policy
Get-ExecutionPolicy

# Set policy for current user (if needed)
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Docker Not Running

Make sure Docker Desktop is running before building images.

### Azure CLI Not Found

Install Azure CLI:
```powershell
# Using winget
winget install -e --id Microsoft.AzureCLI

# Or download from: https://aka.ms/installazurecliwindows
```

---

**Recommended**: Use Option 1 (PowerShell script) for the easiest deployment experience!
