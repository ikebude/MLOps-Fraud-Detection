# Quick Fix for Airflow Credentials and FraudGuard Data
$ErrorActionPreference = "Continue"

$NAMESPACE = "mlops"

Write-Host "=== QUICK FIX FOR AIRFLOW AND FRAUDGUARD ===" -ForegroundColor Green
Write-Host ""

# ============================================
# FIX 1: Airflow Credentials
# ============================================
Write-Host "FIX 1: Resetting Airflow Credentials..." -ForegroundColor Yellow
$podName = kubectl get pods -n $NAMESPACE -l app=airflow-webserver -o jsonpath='{.items[0].metadata.name}' 2>&1

if ($podName -and -not ($podName -match "error")) {
    Write-Host "Found Airflow pod: $podName" -ForegroundColor Cyan
    
    # Try reset password
    Write-Host "Resetting password..." -ForegroundColor Yellow
    $result = kubectl exec -n $NAMESPACE $podName -c airflow-webserver -- airflow users reset-password --username airflow --password airflow 2>&1
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "SUCCESS: Airflow password reset!" -ForegroundColor Green
    } else {
        # Try creating user
        Write-Host "Trying to create user..." -ForegroundColor Yellow
        $createResult = kubectl exec -n $NAMESPACE $podName -c airflow-webserver -- airflow users create --username airflow --firstname Admin --lastname User --role Admin --email admin@example.com --password airflow 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host "SUCCESS: Airflow user created!" -ForegroundColor Green
        } else {
            Write-Host "WARNING: Check output manually" -ForegroundColor Yellow
            Write-Host $createResult -ForegroundColor Yellow
        }
    }
    
    Write-Host ""
    Write-Host "Airflow Login:" -ForegroundColor Cyan
    Write-Host "  URL: http://4.153.190.166/airflow" -ForegroundColor White
    Write-Host "  Username: airflow" -ForegroundColor White
    Write-Host "  Password: airflow" -ForegroundColor White
} else {
    Write-Host "ERROR: Could not find Airflow pod" -ForegroundColor Red
}

Write-Host ""
Write-Host ""

# ============================================
# FIX 2: FraudGuard Data Population
# ============================================
Write-Host "FIX 2: Checking FraudGuard Data Issue..." -ForegroundColor Yellow

# Check if inference has data
Write-Host "Checking inference service..." -ForegroundColor Cyan
$inferencePod = kubectl get pods -n $NAMESPACE -l app=inference -o jsonpath='{.items[0].metadata.name}' 2>&1

if ($inferencePod -and -not ($inferencePod -match "error")) {
    Write-Host "Testing inference stats..." -ForegroundColor Yellow
    $stats = kubectl exec -n $NAMESPACE $inferencePod -- curl -s http://localhost:8000/inference/stats 2>&1
    
    if ($stats -match "total_records" -and $stats -match '"total_records":0') {
        Write-Host "WARNING: Inference has no data. Need to run inference first!" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "Running inference now..." -ForegroundColor Cyan
        $runResult = kubectl exec -n $NAMESPACE $inferencePod -- curl -s -X POST http://localhost:8000/inference/run -H "Content-Type: application/json" -d '{\"max_records\": 100}' 2>&1
        Write-Host "Inference triggered. Waiting 10 seconds..." -ForegroundColor Yellow
        Start-Sleep -Seconds 10
        
        # Check stats again
        $stats2 = kubectl exec -n $NAMESPACE $inferencePod -- curl -s http://localhost:8000/inference/stats 2>&1
        if ($stats2 -match "total_records" -and -not ($stats2 -match '"total_records":0')) {
            Write-Host "SUCCESS: Inference data generated!" -ForegroundColor Green
        } else {
            Write-Host "Inference may still be running. Check FraudGuard UI in a moment." -ForegroundColor Yellow
        }
    } elseif ($stats -match "total_records") {
        Write-Host "SUCCESS: Inference has data!" -ForegroundColor Green
        try {
            $statsJson = $stats | ConvertFrom-Json
            Write-Host "  Total Records: $($statsJson.total_records)" -ForegroundColor Cyan
            Write-Host "  Fraud Rate: $($statsJson.fraud_rate)%" -ForegroundColor Cyan
        } catch {
            Write-Host "  Data available (could not parse JSON)" -ForegroundColor Cyan
        }
    } else {
        Write-Host "WARNING: Could not check inference stats" -ForegroundColor Yellow
        Write-Host "Response: $($stats.Substring(0, [Math]::Min(100, $stats.Length)))" -ForegroundColor Yellow
    }
} else {
    Write-Host "ERROR: Could not find Inference pod" -ForegroundColor Red
}

Write-Host ""
Write-Host ""

# ============================================
# SUMMARY
# ============================================
Write-Host "=== SUMMARY ===" -ForegroundColor Green
Write-Host ""
Write-Host "1. Airflow credentials should now work:" -ForegroundColor Cyan
Write-Host "   http://4.153.190.166/airflow (airflow/airflow)" -ForegroundColor White
Write-Host ""
Write-Host "2. FraudGuard data:" -ForegroundColor Cyan
Write-Host "   - If inference was run, refresh FraudGuard UI" -ForegroundColor White
Write-Host "   - Go to: http://4.153.190.166/fraudguard" -ForegroundColor White
Write-Host "   - Click 'Refresh Model' button if data doesn't appear" -ForegroundColor White
Write-Host ""
Write-Host "3. If FraudGuard still shows no data:" -ForegroundColor Cyan
Write-Host "   Run this command to trigger inference:" -ForegroundColor White
Write-Host "   Invoke-WebRequest -Uri 'http://4.153.190.166/inference/inference/run' -Method POST -ContentType 'application/json' -Body '{\"max_records\": 100}'" -ForegroundColor Yellow
Write-Host ""
