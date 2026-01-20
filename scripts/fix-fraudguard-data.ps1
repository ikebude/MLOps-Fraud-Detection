# Fix FraudGuard Data Population Issue
# This script checks and fixes the connection between FraudGuard and Inference service

$ErrorActionPreference = "Continue"

Write-Host "=== Fixing FraudGuard Data Population ===" -ForegroundColor Green
Write-Host ""

$NAMESPACE = "mlops"

# Step 1: Check FraudGuard pod logs
Write-Host "Step 1: Checking FraudGuard logs..." -ForegroundColor Yellow
$fraudguardPod = kubectl get pods -n $NAMESPACE -l app=fraudguard -o jsonpath='{.items[0].metadata.name}' 2>&1

if ($fraudguardPod -and -not ($fraudguardPod -match "error")) {
    Write-Host "FraudGuard pod: $fraudguardPod" -ForegroundColor Cyan
    Write-Host "Recent logs:" -ForegroundColor Yellow
    kubectl logs -n $NAMESPACE $fraudguardPod --tail=20 2>&1 | Select-Object -Last 10
} else {
    Write-Host "Could not find FraudGuard pod" -ForegroundColor Red
}

Write-Host ""

# Step 2: Check Inference service connectivity
Write-Host "Step 2: Testing Inference service connectivity..." -ForegroundColor Yellow

# Test from within cluster (what FraudGuard sees)
Write-Host "Testing internal inference service URL (http://inference:8000)..." -ForegroundColor Cyan
$inferencePod = kubectl get pods -n $NAMESPACE -l app=inference -o jsonpath='{.items[0].metadata.name}' 2>&1

if ($inferencePod -and -not ($inferencePod -match "error")) {
    Write-Host "Inference pod: $inferencePod" -ForegroundColor Cyan
    
    # Test health endpoint
    Write-Host "Testing health endpoint..." -ForegroundColor Yellow
    $healthTest = kubectl exec -n $NAMESPACE $inferencePod -- curl -s http://localhost:8000/health 2>&1
    if ($healthTest -match "healthy") {
        Write-Host "  ✓ Inference service is healthy" -ForegroundColor Green
    } else {
        Write-Host "  ✗ Inference service health check failed" -ForegroundColor Red
        Write-Host "    Response: $healthTest" -ForegroundColor Yellow
    }
    
    # Test stats endpoint
    Write-Host "Testing stats endpoint..." -ForegroundColor Yellow
    $statsTest = kubectl exec -n $NAMESPACE $inferencePod -- curl -s http://localhost:8000/inference/stats 2>&1
    if ($statsTest -match "total_records" -or $statsTest -match "status") {
        Write-Host "  ✓ Stats endpoint is accessible" -ForegroundColor Green
        try {
            $statsJson = $statsTest | ConvertFrom-Json
            Write-Host "    Total Records: $($statsJson.total_records)" -ForegroundColor Cyan
            Write-Host "    Fraud Rate: $($statsJson.fraud_rate)%" -ForegroundColor Cyan
        } catch {
            Write-Host "    (Could not parse JSON)" -ForegroundColor Yellow
        }
    } else {
        Write-Host "  ⚠ Stats endpoint returned: $statsTest" -ForegroundColor Yellow
        Write-Host "    This might mean inference hasn't been run yet" -ForegroundColor Yellow
    }
} else {
    Write-Host "Could not find Inference pod" -ForegroundColor Red
}

Write-Host ""

# Step 3: Check FraudGuard environment variables
Write-Host "Step 3: Checking FraudGuard configuration..." -ForegroundColor Yellow
if ($fraudguardPod -and -not ($fraudguardPod -match "error")) {
    Write-Host "FraudGuard environment variables:" -ForegroundColor Cyan
    kubectl exec -n $NAMESPACE $fraudguardPod -- env | Select-String "INFERENCE" 2>&1
}

Write-Host ""

# Step 4: Test FraudGuard API from within cluster
Write-Host "Step 4: Testing FraudGuard API endpoints..." -ForegroundColor Yellow
if ($fraudguardPod -and -not ($fraudguardPod -match "error")) {
    Write-Host "Testing /api/health..." -ForegroundColor Cyan
    $health = kubectl exec -n $NAMESPACE $fraudguardPod -- curl -s http://localhost:5000/api/health 2>&1
    Write-Host "  Response: $health" -ForegroundColor $(if ($health -match "ok" -or $health -match "healthy") { "Green" } else { "Yellow" })
    
    Write-Host "Testing /api/data..." -ForegroundColor Cyan
    $data = kubectl exec -n $NAMESPACE $fraudguardPod -- curl -s http://localhost:5000/api/data 2>&1
    if ($data -match "total_transactions" -or $data -match "metrics") {
        Write-Host "  ✓ Data endpoint is working" -ForegroundColor Green
        try {
            $dataJson = $data | ConvertFrom-Json
            Write-Host "    Total Transactions: $($dataJson.metrics.total_transactions)" -ForegroundColor Cyan
        } catch {
            Write-Host "    (Response received but could not parse)" -ForegroundColor Yellow
        }
    } else {
        Write-Host "  ⚠ Data endpoint response: $($data.Substring(0, [Math]::Min(200, $data.Length)))" -ForegroundColor Yellow
    }
}

Write-Host ""

# Step 5: Run inference if needed
Write-Host "Step 5: Checking if inference needs to be run..." -ForegroundColor Yellow
Write-Host "To populate FraudGuard, inference needs to be run first." -ForegroundColor Cyan
Write-Host ""
Write-Host "Option 1: Run inference via API" -ForegroundColor Yellow
Write-Host "  Invoke-WebRequest -Uri 'http://4.153.190.166/inference/inference/run' -Method POST -ContentType 'application/json' -Body '{\"max_records\": 100}'" -ForegroundColor Cyan
Write-Host ""
Write-Host "Option 2: Use FraudGuard UI" -ForegroundColor Yellow
Write-Host "  1. Go to http://4.153.190.166/fraudguard" -ForegroundColor Cyan
Write-Host "  2. Click 'Refresh Model' button" -ForegroundColor Cyan
Write-Host "  3. Or navigate to Settings and trigger inference" -ForegroundColor Cyan
Write-Host ""

# Step 6: Check service connectivity
Write-Host "Step 6: Verifying service connectivity..." -ForegroundColor Yellow
Write-Host "FraudGuard should connect to: http://inference:8000" -ForegroundColor Cyan
Write-Host "Testing from FraudGuard pod..." -ForegroundColor Cyan

if ($fraudguardPod -and -not ($fraudguardPod -match "error")) {
    $connectivityTest = kubectl exec -n $NAMESPACE $fraudguardPod -- curl -s -m 5 http://inference:8000/health 2>&1
    if ($connectivityTest -match "healthy" -or $connectivityTest -match "status") {
        Write-Host "  ✓ FraudGuard can reach Inference service" -ForegroundColor Green
    } else {
        Write-Host "  ✗ FraudGuard cannot reach Inference service" -ForegroundColor Red
        Write-Host "    Response: $connectivityTest" -ForegroundColor Yellow
        Write-Host "    This might be a network or service configuration issue" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "=== Summary ===" -ForegroundColor Green
Write-Host ""
Write-Host "To fix FraudGuard data population:" -ForegroundColor Yellow
Write-Host "1. Ensure Inference service is running (✓ checked above)" -ForegroundColor Cyan
Write-Host "2. Run inference to generate data:" -ForegroundColor Cyan
Write-Host "   - Via API: POST to http://4.153.190.166/inference/inference/run" -ForegroundColor White
Write-Host "   - Via UI: Click 'Refresh Model' in FraudGuard" -ForegroundColor White
Write-Host "3. Refresh FraudGuard UI after inference completes" -ForegroundColor Cyan
Write-Host ""
Write-Host "If issues persist, check:" -ForegroundColor Yellow
Write-Host "  - kubectl logs -n $NAMESPACE deployment/fraudguard" -ForegroundColor White
Write-Host "  - kubectl logs -n $NAMESPACE deployment/inference" -ForegroundColor White
Write-Host "  - kubectl get svc -n $NAMESPACE" -ForegroundColor White
