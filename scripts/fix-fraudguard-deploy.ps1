# Fix and Redeploy FraudGuard with Better Error Handling
$ErrorActionPreference = "Stop"

Write-Host "=== Fixing and Redeploying FraudGuard ===" -ForegroundColor Green
Write-Host ""

$ACR_REGISTRY = "mlopsacr12345.azurecr.io"
$IMAGE_NAME = "${ACR_REGISTRY}/fraud-detection/fraudguard:latest"
$NAMESPACE = "mlops"
$ScriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptPath

Write-Host "Project root: $ProjectRoot" -ForegroundColor Cyan
Set-Location $ProjectRoot

# Step 1: Build new image
Write-Host "Step 1: Building FraudGuard image with fixes..." -ForegroundColor Yellow
$FraudGuardPath = Join-Path $ProjectRoot "fraudguard"
Set-Location $FraudGuardPath
docker build -t $IMAGE_NAME .
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Build failed" -ForegroundColor Red
    exit 1
}
Write-Host "Build successful!" -ForegroundColor Green

# Step 2: Push to ACR
Write-Host "Step 2: Pushing image to ACR..." -ForegroundColor Yellow
docker push $IMAGE_NAME
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Push failed" -ForegroundColor Red
    exit 1
}
Write-Host "Push successful!" -ForegroundColor Green

# Step 3: Restart deployment
Write-Host "Step 3: Restarting FraudGuard deployment..." -ForegroundColor Yellow
kubectl rollout restart deployment/fraudguard -n $NAMESPACE
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Restart failed" -ForegroundColor Red
    exit 1
}

# Step 4: Wait for rollout
Write-Host "Step 4: Waiting for rollout to complete..." -ForegroundColor Yellow
kubectl rollout status deployment/fraudguard -n $NAMESPACE --timeout=300s
if ($LASTEXITCODE -eq 0) {
    Write-Host "SUCCESS: FraudGuard redeployed!" -ForegroundColor Green
} else {
    Write-Host "WARNING: Rollout may still be in progress" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== Next Steps ===" -ForegroundColor Cyan
Write-Host "1. Wait 30 seconds for pod to be ready" -ForegroundColor White
Write-Host "2. Clear browser cache (Ctrl+Shift+Delete)" -ForegroundColor White
Write-Host "3. Hard refresh FraudGuard page (Ctrl+Shift+R)" -ForegroundColor White
Write-Host "4. Open browser console (F12) to see debug logs" -ForegroundColor White
Write-Host ""
Write-Host "FraudGuard URL: http://4.153.190.166/fraudguard" -ForegroundColor Yellow

Set-Location $ProjectRoot
