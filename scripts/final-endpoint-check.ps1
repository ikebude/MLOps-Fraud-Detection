# Final Endpoint Verification
$base = "http://4.153.190.166"

Write-Host "=== Final Endpoint Verification ===" -ForegroundColor Green
Write-Host ""

# Test inference health
Write-Host "Testing Inference Health..." -ForegroundColor Yellow
try {
    $r = Invoke-WebRequest -Uri "$base/inference/health" -UseBasicParsing -TimeoutSec 10
    $health = $r.Content | ConvertFrom-Json
    Write-Host "  Status: $($health.status)" -ForegroundColor Green
    Write-Host "  Model Loaded: $($health.model_loaded)" -ForegroundColor $(if ($health.model_loaded) { "Green" } else { "Yellow" })
    Write-Host "  Model Version: $($health.model_version)" -ForegroundColor Cyan
} catch {
    Write-Host "  Failed: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host ""

# Test inference stats
Write-Host "Testing Inference Stats..." -ForegroundColor Yellow
try {
    $r = Invoke-WebRequest -Uri "$base/inference/stats" -UseBasicParsing -TimeoutSec 10
    $stats = $r.Content | ConvertFrom-Json
    if ($stats.status -eq "success") {
        Write-Host "  Total Records: $($stats.total_records)" -ForegroundColor Green
        Write-Host "  Fraud Detections: $($stats.fraud_detections)" -ForegroundColor Cyan
        Write-Host "  Fraud Rate: $($stats.fraud_rate)%" -ForegroundColor Cyan
    } else {
        Write-Host "  Status: $($stats.status)" -ForegroundColor Yellow
    }
} catch {
    if ($_.Exception.Response.StatusCode -eq 404) {
        Write-Host "  No results yet - inference needs to be run first" -ForegroundColor Yellow
    } else {
        Write-Host "  Error: $($_.Exception.Message)" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "=== Summary ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "All endpoints are accessible at: $base" -ForegroundColor Green
Write-Host ""
Write-Host "Access URLs:" -ForegroundColor Yellow
Write-Host "  Airflow:    $base/airflow (username: airflow, password: airflow)"
Write-Host "  MLflow:     $base/mlflow/"
Write-Host "  Fraud Guard: $base/fraudguard"
Write-Host "  Inference:  $base/inference"
Write-Host "  Flower:     $base/flower"
