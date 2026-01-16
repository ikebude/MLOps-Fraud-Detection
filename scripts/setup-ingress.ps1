# Setup Ingress Controller for Production Access
# This creates a single LoadBalancer IP that routes to all services

param(
    [string]$Namespace = "mlops"
)

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Setting Up Ingress Controller" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "This will:" -ForegroundColor Yellow
Write-Host "  1. Install NGINX Ingress Controller" -ForegroundColor White
Write-Host "  2. Create Ingress rules for all services" -ForegroundColor White
Write-Host "  3. Get you a single external IP for all services" -ForegroundColor White
Write-Host ""

$confirm = Read-Host "Continue? (Y/N)"
if ($confirm -ne "Y" -and $confirm -ne "y") {
    Write-Host "Cancelled." -ForegroundColor Yellow
    exit 0
}

Write-Host ""

# Step 1: Add NGINX Ingress Helm repository
Write-Host "[1] Adding NGINX Ingress Helm repository..." -ForegroundColor Yellow
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "  [WARNING] Helm may not be installed. Trying alternative method..." -ForegroundColor Yellow
    
    # Alternative: Use kubectl apply
    Write-Host "  Installing via kubectl..." -ForegroundColor Cyan
    kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.8.2/deploy/static/provider/cloud/deploy.yaml 2>&1 | Out-Null
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  [ERROR] Failed to install Ingress Controller" -ForegroundColor Red
        Write-Host "  Please install manually:" -ForegroundColor Yellow
        Write-Host "    kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.8.2/deploy/static/provider/cloud/deploy.yaml" -ForegroundColor Cyan
        exit 1
    }
} else {
    helm repo update 2>&1 | Out-Null
    
    # Step 2: Install NGINX Ingress Controller
    Write-Host "[2] Installing NGINX Ingress Controller..." -ForegroundColor Yellow
    helm install ingress-nginx ingress-nginx/ingress-nginx `
        --namespace ingress-nginx `
        --create-namespace `
        --set controller.service.type=LoadBalancer `
        --set controller.replicaCount=2 `
        --set controller.resources.requests.cpu=100m `
        --set controller.resources.requests.memory=128Mi `
        --set controller.resources.limits.cpu=500m `
        --set controller.resources.limits.memory=512Mi 2>&1 | Out-Null
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  [ERROR] Failed to install Ingress Controller" -ForegroundColor Red
        exit 1
    }
}

Write-Host "  [OK] Ingress Controller installed" -ForegroundColor Green
Write-Host ""

# Step 3: Wait for Ingress Controller to be ready
Write-Host "[3] Waiting for Ingress Controller to be ready..." -ForegroundColor Yellow
Write-Host "  This may take 2-3 minutes..." -ForegroundColor Cyan

$maxWait = 180
$waited = 0
$ingressReady = $false

while ($waited -lt $maxWait -and -not $ingressReady) {
    $ingressIP = kubectl get svc -n ingress-nginx ingress-nginx-controller -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>&1
    
    if ($ingressIP -and -not ($ingressIP -match "error") -and $ingressIP -ne "" -and $ingressIP -ne "<pending>") {
        $ingressReady = $true
        Write-Host "  [OK] Ingress Controller is ready!" -ForegroundColor Green
        Write-Host "  External IP: $ingressIP" -ForegroundColor Green
        break
    }
    
    Start-Sleep -Seconds 10
    $waited += 10
    if ($waited % 30 -eq 0) {
        Write-Host "  Waiting... ($waited/$maxWait seconds)" -ForegroundColor Cyan
    }
}

if (-not $ingressReady) {
    Write-Host "  [WARNING] Ingress Controller IP still pending" -ForegroundColor Yellow
    Write-Host "  Check status: kubectl get svc -n ingress-nginx" -ForegroundColor Cyan
    Write-Host "  It may take 5-10 minutes for Azure to assign the IP" -ForegroundColor Yellow
}

Write-Host ""

# Step 4: Deploy Ingress rules
Write-Host "[4] Deploying Ingress rules for all services..." -ForegroundColor Yellow
kubectl apply -f k8s/ingress.yaml 2>&1 | Out-Null

if ($LASTEXITCODE -eq 0) {
    Write-Host "  [OK] Ingress rules deployed" -ForegroundColor Green
} else {
    Write-Host "  [ERROR] Failed to deploy Ingress rules" -ForegroundColor Red
    exit 1
}

Write-Host ""

# Step 5: Get Ingress IP and show access URLs
Write-Host "[5] Getting Ingress Controller IP..." -ForegroundColor Yellow
$ingressIP = kubectl get svc -n ingress-nginx ingress-nginx-controller -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>&1

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Ingress Setup Complete!" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

if ($ingressIP -and -not ($ingressIP -match "error") -and $ingressIP -ne "" -and $ingressIP -ne "<pending>") {
    Write-Host "External IP: $ingressIP" -ForegroundColor Green
    Write-Host ""
    Write-Host "Access your services:" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Option 1: Using /etc/hosts (for local testing)" -ForegroundColor Cyan
    Write-Host "  Add these lines to C:\Windows\System32\drivers\etc\hosts:" -ForegroundColor White
    Write-Host "    $ingressIP  airflow.mlops.local" -ForegroundColor Green
    Write-Host "    $ingressIP  mlflow.mlops.local" -ForegroundColor Green
    Write-Host "    $ingressIP  fraudguard.mlops.local" -ForegroundColor Green
    Write-Host "    $ingressIP  inference.mlops.local" -ForegroundColor Green
    Write-Host "    $ingressIP  flower.mlops.local" -ForegroundColor Green
    Write-Host ""
    Write-Host "  Then access:" -ForegroundColor Cyan
    Write-Host "    Airflow:    http://airflow.mlops.local" -ForegroundColor Green
    Write-Host "    MLflow:     http://mlflow.mlops.local" -ForegroundColor Green
    Write-Host "    Fraud Guard: http://fraudguard.mlops.local" -ForegroundColor Green
    Write-Host "    Inference:  http://inference.mlops.local" -ForegroundColor Green
    Write-Host "    Flower:     http://flower.mlops.local" -ForegroundColor Green
    Write-Host ""
    Write-Host "Option 2: Using path-based routing (no hosts file needed)" -ForegroundColor Cyan
    Write-Host "  Access via:" -ForegroundColor White
    Write-Host "    Airflow:    http://$ingressIP/airflow" -ForegroundColor Green
    Write-Host "    MLflow:     http://$ingressIP/mlflow" -ForegroundColor Green
    Write-Host "    Fraud Guard: http://$ingressIP/fraudguard" -ForegroundColor Green
    Write-Host "    Inference:  http://$ingressIP/inference" -ForegroundColor Green
    Write-Host "    Flower:     http://$ingressIP/flower" -ForegroundColor Green
    Write-Host ""
    Write-Host "Option 3: Configure DNS (for production)" -ForegroundColor Cyan
    Write-Host "  Point your domain names to: $ingressIP" -ForegroundColor White
    Write-Host "  Then access via your actual domain names" -ForegroundColor White
} else {
    Write-Host "Ingress Controller IP is still pending..." -ForegroundColor Yellow
    Write-Host "Check status with: kubectl get svc -n ingress-nginx" -ForegroundColor Cyan
    Write-Host "Once IP is assigned, you can access services using the methods above" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "To check Ingress status:" -ForegroundColor Cyan
Write-Host "  kubectl get ingress -n $Namespace" -ForegroundColor Green
Write-Host "  kubectl get svc -n ingress-nginx" -ForegroundColor Green
Write-Host ""
