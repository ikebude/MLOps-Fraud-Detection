# Fix FraudGuard Dashboard Issues
# This script rebuilds and redeploys FraudGuard with all the fixes

$ErrorActionPreference = "Continue"

Write-Host "=== Fixing FraudGuard Dashboard ===" -ForegroundColor Green
Write-Host ""

$ACR_NAME = "mlopsacr12345"
$NAMESPACE = "mlops"
$IMAGE_NAME = "fraudguard"
$IMAGE_TAG = "latest"
$FULL_IMAGE = "${ACR_NAME}.azurecr.io/fraud-detection/${IMAGE_NAME}:${IMAGE_TAG}"

Write-Host "Step 1: Logging into ACR..." -ForegroundColor Yellow
az acr login --name $ACR_NAME
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Failed to login to ACR" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Step 2: Building FraudGuard Docker image..." -ForegroundColor Yellow
# Build from fraudguard directory with correct context
Push-Location fraudguard
docker build -t $FULL_IMAGE -f Dockerfile .
$buildResult = $LASTEXITCODE
Pop-Location
if ($buildResult -ne 0) {
    Write-Host "ERROR: Docker build failed" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Step 3: Pushing image to ACR..." -ForegroundColor Yellow
docker push $FULL_IMAGE
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Docker push failed" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Step 4: Restarting FraudGuard deployment..." -ForegroundColor Yellow
kubectl rollout restart deployment/fraudguard -n $NAMESPACE
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Failed to restart deployment" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Step 5: Waiting for rollout to complete..." -ForegroundColor Yellow
kubectl rollout status deployment/fraudguard -n $NAMESPACE --timeout=5m
if ($LASTEXITCODE -ne 0) {
    Write-Host "WARNING: Rollout status check failed or timed out" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== SUCCESS ===" -ForegroundColor Green
Write-Host ""
Write-Host "FraudGuard has been rebuilt and redeployed with the following fixes:" -ForegroundColor Cyan
Write-Host "  ✅ Fixed drift status calculation (better logic)" -ForegroundColor Green
Write-Host "  ✅ Fixed total transactions (now shows actual count)" -ForegroundColor Green
Write-Host "  ✅ Fixed transaction volume and fraud trends charts" -ForegroundColor Green
Write-Host "  ✅ Fixed model accuracy (shows precision, not just whole numbers)" -ForegroundColor Green
Write-Host "  ✅ Fixed model name (shows MLflow run name like 'skittish lynx 401')" -ForegroundColor Green
Write-Host "  ✅ Improved loading performance (optimized API calls)" -ForegroundColor Green
Write-Host "  ✅ Added inference stats for presentation" -ForegroundColor Green
Write-Host ""
Write-Host "Access FraudGuard at: http://4.153.190.166/fraudguard/" -ForegroundColor Yellow
Write-Host ""
Write-Host "Wait 1-2 minutes for the service to fully start, then refresh your browser!" -ForegroundColor Cyan
