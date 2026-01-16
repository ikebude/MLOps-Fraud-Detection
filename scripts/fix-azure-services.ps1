# Fix Script for Azure AKS Services
# This script attempts to fix common issues with the deployment

param(
    [string]$Namespace = "mlops"
)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Azure AKS Service Fix Script" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check if acr-secret exists and create if missing
Write-Host "[1] Checking ACR Secret..." -ForegroundColor Cyan
$acrSecret = kubectl get secret acr-secret -n $Namespace 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "  ⚠ ACR secret missing. Creating..." -ForegroundColor Yellow
    
    # Get ACR credentials
    $acrName = "mlopsacr12345"
    Write-Host "  Getting ACR credentials..." -ForegroundColor Yellow
    $acrCreds = az acr credential show --name $acrName 2>&1
    
    if ($LASTEXITCODE -eq 0) {
        $username = $acrName
        $password = (az acr credential show --name $acrName --query "passwords[0].value" -o tsv)
        
        kubectl create secret docker-registry acr-secret `
            --docker-server="$acrName.azurecr.io" `
            --docker-username=$username `
            --docker-password=$password `
            -n $Namespace 2>&1 | Out-Null
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  ✓ ACR secret created" -ForegroundColor Green
        } else {
            Write-Host "  ✗ Failed to create ACR secret" -ForegroundColor Red
        }
    } else {
        Write-Host "  ✗ Could not get ACR credentials. Please create manually:" -ForegroundColor Red
        Write-Host "    kubectl create secret docker-registry acr-secret --docker-server=mlopsacr12345.azurecr.io --docker-username=mlopsacr12345 --docker-password=<password> -n $Namespace" -ForegroundColor Yellow
    }
} else {
    Write-Host "  ✓ ACR secret exists" -ForegroundColor Green
}
Write-Host ""

# Restart services that might be stuck
Write-Host "[2] Restarting services..." -ForegroundColor Cyan
$services = @("airflow-webserver", "airflow-scheduler", "mlflow", "inference", "fraudguard", "flower")

foreach ($svc in $services) {
    Write-Host "  Restarting $svc..." -ForegroundColor Yellow
    kubectl rollout restart deployment/$svc -n $Namespace 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "    ✓ Restarted" -ForegroundColor Green
    } else {
        Write-Host "    ⚠ Service may not exist or already restarting" -ForegroundColor Yellow
    }
}
Write-Host ""

# Wait for services to be ready
Write-Host "[3] Waiting for services to be ready (this may take a few minutes)..." -ForegroundColor Cyan
Write-Host "  This will wait up to 5 minutes for each service..." -ForegroundColor Yellow

foreach ($svc in $services) {
    Write-Host "  Waiting for $svc..." -ForegroundColor Yellow
    kubectl wait --for=condition=available --timeout=300s deployment/$svc -n $Namespace 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "    ✓ $svc is ready" -ForegroundColor Green
    } else {
        Write-Host "    ⚠ $svc may still be starting. Check with: kubectl get pods -n $Namespace" -ForegroundColor Yellow
    }
}
Write-Host ""

# Check service IPs
Write-Host "[4] Checking service IPs..." -ForegroundColor Cyan
kubectl get svc -n $Namespace
Write-Host ""

# Provide recommendations
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Next Steps" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "1. If LoadBalancer IPs are still pending:" -ForegroundColor Yellow
Write-Host "   - Check Azure quota: Azure Portal → Subscriptions → Usage + quotas" -ForegroundColor Cyan
Write-Host "   - Use port-forwarding for immediate access:" -ForegroundColor Cyan
Write-Host "     .\scripts\quick-access-port-forward.ps1" -ForegroundColor Green
Write-Host ""
Write-Host "2. Check pod logs if services aren't working:" -ForegroundColor Yellow
Write-Host "   kubectl logs -f deployment/airflow-webserver -n $Namespace" -ForegroundColor Green
Write-Host "   kubectl logs -f deployment/mlflow -n $Namespace" -ForegroundColor Green
Write-Host ""
Write-Host "3. Run diagnostics:" -ForegroundColor Yellow
Write-Host "   .\scripts\diagnose-azure-issues.ps1" -ForegroundColor Green
Write-Host ""
