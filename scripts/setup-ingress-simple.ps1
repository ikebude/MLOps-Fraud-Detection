# Simple Ingress Setup - Uses kubectl apply (no Helm required)

param(
    [string]$Namespace = "mlops"
)

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Setting Up Ingress Controller (Simple)" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Step 1: Install NGINX Ingress Controller
Write-Host "[1] Installing NGINX Ingress Controller..." -ForegroundColor Yellow
Write-Host "  This may take 2-3 minutes..." -ForegroundColor Cyan

kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.8.2/deploy/static/provider/cloud/deploy.yaml 2>&1 | Out-Null

if ($LASTEXITCODE -ne 0) {
    Write-Host "  [ERROR] Failed to install Ingress Controller" -ForegroundColor Red
    Write-Host "  Please check your kubectl connection" -ForegroundColor Yellow
    exit 1
}

Write-Host "  [OK] Ingress Controller installation started" -ForegroundColor Green
Write-Host ""

# Step 2: Wait for Ingress Controller
Write-Host "[2] Waiting for Ingress Controller to be ready..." -ForegroundColor Yellow
$maxWait = 180
$waited = 0

while ($waited -lt $maxWait) {
    $ingressIP = kubectl get svc -n ingress-nginx ingress-nginx-controller -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>&1
    
    if ($ingressIP -and -not ($ingressIP -match "error") -and $ingressIP -ne "" -and $ingressIP -ne "<pending>") {
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

if ($waited -ge $maxWait) {
    Write-Host "  [WARNING] IP still pending. Check with: kubectl get svc -n ingress-nginx" -ForegroundColor Yellow
}

Write-Host ""

# Step 3: Deploy Ingress rules
Write-Host "[3] Deploying Ingress rules..." -ForegroundColor Yellow
kubectl apply -f k8s/ingress.yaml 2>&1 | Out-Null

if ($LASTEXITCODE -eq 0) {
    Write-Host "  [OK] Ingress rules deployed" -ForegroundColor Green
} else {
    Write-Host "  [ERROR] Failed to deploy Ingress rules" -ForegroundColor Red
    exit 1
}

Write-Host ""

# Step 4: Show results
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Setup Complete!" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$ingressIP = kubectl get svc -n ingress-nginx ingress-nginx-controller -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>&1

if ($ingressIP -and -not ($ingressIP -match "error") -and $ingressIP -ne "" -and $ingressIP -ne "<pending>") {
    Write-Host "External IP: $ingressIP" -ForegroundColor Green
    Write-Host ""
    Write-Host "Access your services at:" -ForegroundColor Yellow
    Write-Host "  Airflow:    http://$ingressIP/airflow" -ForegroundColor Green
    Write-Host "  MLflow:     http://$ingressIP/mlflow" -ForegroundColor Green
    Write-Host "  Fraud Guard: http://$ingressIP/fraudguard" -ForegroundColor Green
    Write-Host "  Inference:  http://$ingressIP/inference" -ForegroundColor Green
    Write-Host "  Flower:     http://$ingressIP/flower" -ForegroundColor Green
} else {
    Write-Host "IP is still pending. Check status:" -ForegroundColor Yellow
    Write-Host "  kubectl get svc -n ingress-nginx" -ForegroundColor Cyan
}

Write-Host ""
