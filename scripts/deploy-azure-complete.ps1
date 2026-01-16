# Complete Azure Deployment Script (PowerShell)
# This script automates the entire Azure deployment process for Windows

$ErrorActionPreference = "Stop"

# Colors for output
function Write-ColorOutput($ForegroundColor) {
    $fc = $host.UI.RawUI.ForegroundColor
    $host.UI.RawUI.ForegroundColor = $ForegroundColor
    if ($args) {
        Write-Output $args
    }
    $host.UI.RawUI.ForegroundColor = $fc
}

# Configuration
$ACR_NAME = "mlopsacr12345"
$ACR_REGISTRY = "${ACR_NAME}.azurecr.io"
$ACR_USERNAME = "mlopsacr12345"
$ACR_PASSWORD = "Tfs3lQolzy3n4GGvwpgjmJIlCP0wWDsRLSjiHmA/HZ+ACRC0hFnV"
$NAMESPACE = "mlops"
$IMAGE_PREFIX = "fraud-detection"

# Store project root directory
$ScriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptPath
Set-Location $ProjectRoot
Write-Output "Project root: $ProjectRoot"

# Get AKS details (with defaults)
$AKS_RESOURCE_GROUP = if ($env:AKS_RESOURCE_GROUP) { $env:AKS_RESOURCE_GROUP } else { "mlops_fraud_analytics" }
$AKS_CLUSTER_NAME = if ($env:AKS_CLUSTER_NAME) { $env:AKS_CLUSTER_NAME } else { "mlops-aks-cluster" }

# Allow override via prompt if needed
$override = Read-Host "Use default AKS settings? (mlops_fraud_analytics/mlops_aks_cluster) [Y/n]"
if ($override -eq "n" -or $override -eq "N") {
    $AKS_RESOURCE_GROUP = Read-Host "AKS Resource Group" 
    $AKS_CLUSTER_NAME = Read-Host "AKS Cluster Name"
}

Write-ColorOutput Green "=== Azure MLOps Fraud Detection Deployment ==="
Write-Output ""
Write-ColorOutput Green "Configuration:"
Write-Output "  ACR: $ACR_REGISTRY"
Write-Output "  AKS Resource Group: $AKS_RESOURCE_GROUP"
Write-Output "  AKS Cluster: $AKS_CLUSTER_NAME"
Write-Output "  Namespace: $NAMESPACE"
Write-Output ""

# Step 1: Login to Azure
Write-ColorOutput Yellow "Step 1: Logging in to Azure..."
try {
    $account = az account show 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        az login
    } else {
        Write-ColorOutput Green "[OK] Already logged in to Azure"
    }
} catch {
    az login
}
Write-ColorOutput Green "[OK] Logged in to Azure"

# Step 2: Login to ACR
Write-ColorOutput Yellow "Step 2: Logging in to ACR..."
az acr login --name $ACR_NAME
if ($LASTEXITCODE -ne 0) {
    Write-ColorOutput Red "[ERROR] Failed to login to ACR"
    exit 1
}
Write-ColorOutput Green "[OK] Logged in to ACR"

# Step 3: Build and push images
Write-ColorOutput Yellow "Step 3: Building and pushing Docker images..."
Write-Output "  This may take 10-15 minutes..."

# Build Airflow (from project root to access src/dags and src/plugins)
Write-Output "  Building Airflow image..."
Set-Location $ProjectRoot
docker build -f src/airflow/Dockerfile -t "${ACR_REGISTRY}/${IMAGE_PREFIX}/airflow:latest" .
if ($LASTEXITCODE -ne 0) {
    Write-ColorOutput Red "[ERROR] Failed to build Airflow image"
    exit 1
}
docker push "${ACR_REGISTRY}/${IMAGE_PREFIX}/airflow:latest"
if ($LASTEXITCODE -ne 0) {
    Write-ColorOutput Red "[ERROR] Failed to push Airflow image"
    exit 1
}
Write-ColorOutput Green "[OK] Airflow image pushed"

# Build MLflow
Write-Output "  Building MLflow image..."
Set-Location $ProjectRoot
docker build -f src/mlflow/Dockerfile -t "${ACR_REGISTRY}/${IMAGE_PREFIX}/mlflow:latest" .
if ($LASTEXITCODE -ne 0) {
    Write-ColorOutput Red "[ERROR] Failed to build MLflow image"
    exit 1
}
docker push "${ACR_REGISTRY}/${IMAGE_PREFIX}/mlflow:latest"
if ($LASTEXITCODE -ne 0) {
    Write-ColorOutput Red "[ERROR] Failed to push MLflow image"
    exit 1
}
Write-ColorOutput Green "[OK] MLflow image pushed"

# Build Inference
Write-Output "  Building Inference image..."
Set-Location $ProjectRoot
docker build -f src/inference/Dockerfile -t "${ACR_REGISTRY}/${IMAGE_PREFIX}/inference:latest" .
if ($LASTEXITCODE -ne 0) {
    Write-ColorOutput Red "[ERROR] Failed to build Inference image"
    exit 1
}
docker push "${ACR_REGISTRY}/${IMAGE_PREFIX}/inference:latest"
if ($LASTEXITCODE -ne 0) {
    Write-ColorOutput Red "[ERROR] Failed to push Inference image"
    exit 1
}
Write-ColorOutput Green "[OK] Inference image pushed"

# Build Fraud Guard
Write-Output "  Building Fraud Guard image..."
Set-Location $ProjectRoot
docker build -f fraudguard/Dockerfile -t "${ACR_REGISTRY}/${IMAGE_PREFIX}/fraudguard:latest" fraudguard
if ($LASTEXITCODE -ne 0) {
    Write-ColorOutput Red "[ERROR] Failed to build Fraud Guard image"
    exit 1
}
docker push "${ACR_REGISTRY}/${IMAGE_PREFIX}/fraudguard:latest"
if ($LASTEXITCODE -ne 0) {
    Write-ColorOutput Red "[ERROR] Failed to push Fraud Guard image"
    exit 1
}
Write-ColorOutput Green "[OK] Fraud Guard image pushed"

# Return to project root
Set-Location $ProjectRoot

# Step 4: Get AKS credentials
Write-ColorOutput Yellow "Step 4: Getting AKS credentials..."
az aks get-credentials --resource-group $AKS_RESOURCE_GROUP --name $AKS_CLUSTER_NAME --overwrite-existing
if ($LASTEXITCODE -ne 0) {
    Write-ColorOutput Red "[ERROR] Failed to get AKS credentials"
    exit 1
}
Write-ColorOutput Green "[OK] AKS credentials configured"

# Step 5: Create namespace
Write-ColorOutput Yellow "Step 5: Creating namespace..."
kubectl create namespace $NAMESPACE --dry-run=client -o yaml | kubectl apply -f -
Write-ColorOutput Green "[OK] Namespace created"

# Step 6: Create ACR secret
Write-ColorOutput Yellow "Step 6: Creating ACR image pull secret..."
kubectl create secret docker-registry acr-secret `
  --docker-server=$ACR_REGISTRY `
  --docker-username=$ACR_USERNAME `
  --docker-password=$ACR_PASSWORD `
  --namespace=$NAMESPACE `
  --dry-run=client -o yaml | kubectl apply -f -
Write-ColorOutput Green "[OK] ACR secret created"

# Step 7: Deploy Kubernetes resources
Write-ColorOutput Yellow "Step 7: Deploying Kubernetes resources..."

# Ensure we're in the project root
Set-Location $ProjectRoot
if (-not (Test-Path "k8s")) {
    Write-ColorOutput Red "[ERROR] Cannot find k8s directory. Current directory: $(Get-Location)"
    Write-ColorOutput Red "[ERROR] Expected k8s directory at: $(Join-Path $ProjectRoot 'k8s')"
    exit 1
}

Write-Output "  Current directory: $(Get-Location)"
Write-Output "  Deploying secrets..."
kubectl apply -f k8s/secrets.yaml

Write-Output "  Deploying Redis..."
kubectl apply -f k8s/redis.yaml

Write-Output "  Deploying MLflow..."
kubectl apply -f k8s/mlflow.yaml

Write-Output "  Deploying Inference..."
kubectl apply -f k8s/inference-config.yaml
kubectl apply -f k8s/inference.yaml

Write-Output "  Deploying Airflow configs..."
kubectl apply -f k8s/airflow-configmap.yaml

Write-Output "  Deploying Airflow..."
kubectl apply -f k8s/airflow.yaml

Write-Output "  Deploying Flower..."
kubectl apply -f k8s/flower.yaml

Write-Output "  Deploying Fraud Guard..."
kubectl apply -f k8s/fraudguard.yaml

Write-ColorOutput Green "[OK] All resources deployed"

# Step 8: Wait for deployments
Write-ColorOutput Yellow "Step 8: Waiting for deployments to be ready..."
Write-Output "  This may take a few minutes..."
# Wait for deployments (ignore errors if they don't exist yet)
kubectl wait --for=condition=available --timeout=300s deployment/redis -n $NAMESPACE 2>&1 | Out-Null
kubectl wait --for=condition=available --timeout=300s deployment/mlflow -n $NAMESPACE 2>&1 | Out-Null
kubectl wait --for=condition=available --timeout=300s deployment/inference -n $NAMESPACE 2>&1 | Out-Null
kubectl wait --for=condition=available --timeout=300s deployment/fraudguard -n $NAMESPACE 2>&1 | Out-Null

# Step 9: Get service IPs
Write-ColorOutput Yellow "Step 9: Getting service endpoints..."
Write-Output ""
Write-ColorOutput Green "=== Service Endpoints ==="
Write-Output ""

function Get-ExternalIP {
    param($ServiceName)
    $ip = kubectl get svc $ServiceName -n $NAMESPACE -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>&1
    if (-not $ip -or $ip -match "error" -or $ip -eq "") {
        return "Pending..."
    }
    return $ip
}

$fraudguardIP = Get-ExternalIP "fraudguard"
$airflowIP = Get-ExternalIP "airflow-webserver"
$mlflowIP = Get-ExternalIP "mlflow"
$inferenceIP = Get-ExternalIP "inference"
$flowerIP = Get-ExternalIP "flower"

Write-Output "Fraud Guard:    http://${fraudguardIP}:5000"
Write-Output "Airflow:       http://${airflowIP}:8080"
Write-Output "MLflow:         http://${mlflowIP}:5000"
Write-Output "Inference API: http://${inferenceIP}:8000"
Write-Output "Flower:         http://${flowerIP}:5555"
Write-Output ""

Write-ColorOutput Yellow "Note: LoadBalancer IPs may take a few minutes to be assigned."
Write-ColorOutput Yellow "Run 'kubectl get svc -n $NAMESPACE' to check status."
Write-Output ""

# Step 10: Initialize Airflow Database
Write-ColorOutput Yellow "Step 10: Initializing Airflow database..."
Write-Output "  This step ensures the database is properly initialized before the webserver starts."

# Wait for the deployment to be available
Write-Output "  Waiting for Airflow webserver deployment..."
kubectl wait --for=condition=available --timeout=300s deployment/airflow-webserver -n $NAMESPACE 2>&1 | Out-Null

# Wait for init container to complete
Write-Output "  Waiting for init container to complete database initialization..."
$maxWait = 180
$waited = 0
$podReady = $false

while ($waited -lt $maxWait -and -not $podReady) {
    $podName = kubectl get pods -n $NAMESPACE -l app=airflow-webserver -o jsonpath='{.items[0].metadata.name}' 2>&1
    
    if ($podName -and -not ($podName -match "error")) {
        $initStatus = kubectl get pod $podName -n $NAMESPACE -o jsonpath='{.status.initContainerStatuses[0].ready}' 2>&1
        $podStatus = kubectl get pod $podName -n $NAMESPACE -o jsonpath='{.status.phase}' 2>&1
        
        if ($initStatus -eq "true" -and $podStatus -eq "Running") {
            # Check if container is ready
            $containerReady = kubectl get pod $podName -n $NAMESPACE -o jsonpath='{.status.containerStatuses[0].ready}' 2>&1
            if ($containerReady -eq "true") {
                $podReady = $true
                Write-ColorOutput Green "[OK] Pod is ready"
                break
            }
        }
    }
    
    Start-Sleep -Seconds 5
    $waited += 5
    if ($waited % 15 -eq 0) {
        Write-Output "  Waiting... ($waited/$maxWait seconds)"
    }
}

if (-not $podReady) {
    Write-ColorOutput Yellow "[WARNING] Pod may still be initializing. Creating database initialization job..."
    
    # Create a job to ensure database is initialized
    $jobYaml = @"
apiVersion: batch/v1
kind: Job
metadata:
  name: airflow-db-init-$(Get-Date -Format 'yyyyMMddHHmmss')
  namespace: $NAMESPACE
spec:
  template:
    spec:
      imagePullSecrets:
      - name: acr-secret
      containers:
      - name: init-db
        image: ${ACR_REGISTRY}/${IMAGE_PREFIX}/airflow:latest
        command: ["sh", "-c"]
        args:
        - |
          set -e
          echo "Initializing Airflow database..."
          airflow db init
          echo "Verifying database..."
          airflow db check
          echo "Database ready!"
        env:
        - name: AIRFLOW__DATABASE__SQL_ALCHEMY_CONN
          valueFrom:
            configMapKeyRef:
              name: airflow-config
              key: AIRFLOW__CORE__SQL_ALCHEMY_CONN
        - name: AIRFLOW__CORE__EXECUTOR
          valueFrom:
            configMapKeyRef:
              name: airflow-config
              key: AIRFLOW__CORE__EXECUTOR
      restartPolicy: Never
"@
    
    $jobYaml | kubectl apply -f - 2>&1 | Out-Null
    
    if ($LASTEXITCODE -eq 0) {
        Write-Output "  Waiting for database initialization job to complete..."
        $jobName = kubectl get jobs -n $NAMESPACE -o jsonpath='{.items[-1].metadata.name}' 2>&1
        
        $jobWaited = 0
        $jobMaxWait = 120
        while ($jobWaited -lt $jobMaxWait) {
            $jobSucceeded = kubectl get job $jobName -n $NAMESPACE -o jsonpath='{.status.succeeded}' 2>&1
            if ($jobSucceeded -eq "1") {
                Write-ColorOutput Green "[OK] Database initialized successfully"
                kubectl delete job $jobName -n $NAMESPACE 2>&1 | Out-Null
                break
            }
            
            $jobFailed = kubectl get job $jobName -n $NAMESPACE -o jsonpath='{.status.failed}' 2>&1
            if ($jobFailed -match "^[1-9]") {
                Write-ColorOutput Red "[ERROR] Database initialization failed"
                $jobPod = kubectl get pods -n $NAMESPACE -l job-name=$jobName -o jsonpath='{.items[0].metadata.name}' 2>&1
                kubectl logs $jobPod -n $NAMESPACE 2>&1
                kubectl delete job $jobName -n $NAMESPACE 2>&1 | Out-Null
                exit 1
            }
            
            Start-Sleep -Seconds 5
            $jobWaited += 5
        }
        
        # Restart deployments to pick up initialized database
        Write-Output "  Restarting Airflow deployments..."
        kubectl rollout restart deployment/airflow-webserver -n $NAMESPACE 2>&1 | Out-Null
        kubectl rollout restart deployment/airflow-scheduler -n $NAMESPACE 2>&1 | Out-Null
        
        Write-Output "  Waiting for pods to be ready..."
        Start-Sleep -Seconds 10
    }
}

Write-ColorOutput Green "[OK] Airflow database initialization complete"

# Step 11: Setup Port Forwarding for Easy Access
Write-ColorOutput Yellow "Step 11: Setting up port forwarding for easy UI access..."
Write-Output ""
Write-ColorOutput Cyan "To access all UIs, run the following commands in separate terminals:"
Write-Output ""
Write-ColorOutput Green "  Terminal 1 - Airflow:"
Write-Output "    kubectl port-forward -n $NAMESPACE svc/airflow-webserver 8080:8080"
Write-Output "    Access at: http://localhost:8080 (airflow/airflow)"
Write-Output ""
Write-ColorOutput Green "  Terminal 2 - MLflow:"
Write-Output "    kubectl port-forward -n $NAMESPACE svc/mlflow 5000:5000"
Write-Output "    Access at: http://localhost:5000"
Write-Output ""
Write-ColorOutput Green "  Terminal 3 - Fraud Guard:"
Write-Output "    kubectl port-forward -n $NAMESPACE svc/fraudguard 5001:5000"
Write-Output "    Access at: http://localhost:5001"
Write-Output ""
Write-ColorOutput Green "  Terminal 4 - Inference API:"
Write-Output "    kubectl port-forward -n $NAMESPACE svc/inference 8000:8000"
Write-Output "    Access at: http://localhost:8000"
Write-Output ""
Write-ColorOutput Green "  Terminal 5 - Flower:"
Write-Output "    kubectl port-forward -n $NAMESPACE svc/flower 5555:5555"
Write-Output "    Access at: http://localhost:5555"
Write-Output ""
Write-ColorOutput Cyan "Or use the quick access script:"
Write-Output "  .\scripts\quick-access-port-forward.ps1"
Write-Output ""

Write-Output ""
Write-ColorOutput Green "=== Deployment Complete! ==="
Write-Output ""
Write-Output "Service Status:"
kubectl get pods -n $NAMESPACE -o wide | Select-Object -First 15
Write-Output ""
Write-Output "Service Endpoints:"
kubectl get svc -n $NAMESPACE
Write-Output ""
Write-ColorOutput Yellow "Next steps:"
Write-Output "1. Use port-forwarding to access UIs (see commands above)"
Write-Output "2. Login to Airflow UI (airflow/airflow) and trigger the training DAG"
Write-Output "3. Monitor training progress in Airflow and MLflow UIs"
Write-Output ""
Write-Output "To view logs:"
Write-Output "  kubectl logs -f deployment/<service-name> -n $NAMESPACE"
Write-Output ""
Write-Output "To check pod status:"
Write-Output "  kubectl get pods -n $NAMESPACE"
