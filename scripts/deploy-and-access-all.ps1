# Complete Deployment and Access Script
# This script deploys everything and sets up easy access to all UIs

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Complete MLOps Deployment & Access Setup" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Step 1: Run the deployment
Write-Host "[1] Running complete deployment..." -ForegroundColor Yellow
Write-Host ""
& ".\scripts\deploy-azure-complete.ps1"

if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Deployment failed!" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Setting up UI Access" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Step 2: Wait for all pods to be ready
Write-Host "[2] Waiting for all services to be ready..." -ForegroundColor Yellow
$namespace = "mlops"

$services = @("airflow-webserver", "mlflow", "fraudguard", "inference", "flower", "redis")
foreach ($svc in $services) {
    Write-Host "  Waiting for $svc..." -ForegroundColor Cyan
    kubectl wait --for=condition=available --timeout=300s deployment/$svc -n $namespace 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "    [OK] $svc is ready" -ForegroundColor Green
    } else {
        Write-Host "    [WARNING] $svc may still be starting" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "[3] All services are ready!" -ForegroundColor Green
Write-Host ""

# Step 3: Show access information
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Access Your UIs" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Option 1: Use Port Forwarding (Recommended)" -ForegroundColor Yellow
Write-Host "  Run this script to set up all port forwards:" -ForegroundColor Cyan
Write-Host "    .\scripts\quick-access-port-forward.ps1" -ForegroundColor Green
Write-Host ""
Write-Host "Option 2: Manual Port Forwarding" -ForegroundColor Yellow
Write-Host "  Run these in separate PowerShell windows:" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Airflow:    kubectl port-forward -n $namespace svc/airflow-webserver 8080:8080" -ForegroundColor Green
Write-Host "              Access at: http://localhost:8080 (airflow/airflow)" -ForegroundColor White
Write-Host ""
Write-Host "  MLflow:     kubectl port-forward -n $namespace svc/mlflow 5000:5000" -ForegroundColor Green
Write-Host "              Access at: http://localhost:5000" -ForegroundColor White
Write-Host ""
Write-Host "  Fraud Guard: kubectl port-forward -n $namespace svc/fraudguard 5001:5000" -ForegroundColor Green
Write-Host "              Access at: http://localhost:5001" -ForegroundColor White
Write-Host ""
Write-Host "  Inference:  kubectl port-forward -n $namespace svc/inference 8000:8000" -ForegroundColor Green
Write-Host "              Access at: http://localhost:8000" -ForegroundColor White
Write-Host ""
Write-Host "  Flower:     kubectl port-forward -n $namespace svc/flower 5555:5555" -ForegroundColor Green
Write-Host "              Access at: http://localhost:5555" -ForegroundColor White
Write-Host ""

# Step 4: Check LoadBalancer IPs
Write-Host "[4] Checking LoadBalancer IPs..." -ForegroundColor Yellow
kubectl get svc -n $namespace | Select-String -Pattern "LoadBalancer|NAME"
Write-Host ""

$startPortForward = Read-Host "Start port forwarding for all services now? (Y/N)"
if ($startPortForward -eq "Y" -or $startPortForward -eq "y") {
    Write-Host ""
    Write-Host "Starting port forwarding..." -ForegroundColor Cyan
    & ".\scripts\quick-access-port-forward.ps1"
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "Deployment Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
