# Check MLflow Models and Fraud API
$ErrorActionPreference = "Continue"

Write-Host "=== Checking MLflow Models ===" -ForegroundColor Yellow
$BASE_URL = "http://4.153.190.166"

# Check MLflow with trailing slash
try {
    $response = Invoke-WebRequest -Uri "$BASE_URL/mlflow/" -UseBasicParsing -TimeoutSec 10
    Write-Host "MLflow UI: Accessible (Status: $($response.StatusCode))" -ForegroundColor Green
} catch {
    Write-Host "MLflow UI: May need trailing slash or has redirect" -ForegroundColor Yellow
}

# Check MLflow API for models
try {
    $mlflowApiUrl = "$BASE_URL/mlflow/api/2.0/mlflow/registered-models/search"
    $body = '{"max_results": 10}'
    $response = Invoke-WebRequest -Uri $mlflowApiUrl -Method POST -ContentType "application/json" -Body $body -UseBasicParsing -TimeoutSec 10
    if ($response.StatusCode -eq 200) {
        $models = $response.Content | ConvertFrom-Json
        if ($models.registered_models -and $models.registered_models.Count -gt 0) {
            Write-Host "Found $($models.registered_models.Count) registered model(s):" -ForegroundColor Green
            foreach ($model in $models.registered_models) {
                $latestVersion = $model.latest_versions[0]
                Write-Host "  - $($model.name) (Version $($latestVersion.version), Stage: $($latestVersion.current_stage))" -ForegroundColor Cyan
            }
        } else {
            Write-Host "No registered models found in MLflow" -ForegroundColor Yellow
            Write-Host "  You may need to run the Airflow training DAG first" -ForegroundColor Yellow
        }
    }
} catch {
    Write-Host "Could not check MLflow models: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host ""
Write-Host "=== Checking Fraud API ===" -ForegroundColor Yellow
$FRAUD_API_URL = "https://3consult-ng.com/fraud_api.php"

try {
    $uri = [System.UriBuilder]::new($FRAUD_API_URL)
    $queryParts = @()
    $queryParts += "offset=0"
    $queryParts += "limit=10"
    $uri.Query = $queryParts -join '&'
    
    $response = Invoke-WebRequest -Uri $uri.Uri -UseBasicParsing -TimeoutSec 30
    if ($response.StatusCode -eq 200) {
        $data = $response.Content | ConvertFrom-Json
        $recordCount = 0
        
        if ($data -is [array]) {
            $recordCount = $data.Count
        } elseif ($data.PSObject.Properties['data'] -and $data.data -is [array]) {
            $recordCount = $data.data.Count
        } elseif ($data.PSObject.Properties['transactions'] -and $data.transactions -is [array]) {
            $recordCount = $data.transactions.Count
        }
        
        if ($recordCount -gt 0) {
            Write-Host "Fraud API: Accessible with $recordCount sample records" -ForegroundColor Green
            Write-Host "  The inference service can read from this API" -ForegroundColor Green
        } else {
            Write-Host "Fraud API: Accessible but no records found in sample response" -ForegroundColor Yellow
        }
    }
} catch {
    Write-Host "Fraud API Error: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host ""
Write-Host "=== Checking Inference Service ===" -ForegroundColor Yellow
try {
    $statsUrl = "$BASE_URL/inference/inference/stats"
    $response = Invoke-WebRequest -Uri $statsUrl -UseBasicParsing -TimeoutSec 10
    if ($response.StatusCode -eq 200) {
        $stats = $response.Content | ConvertFrom-Json
        Write-Host "Inference Service Stats:" -ForegroundColor Green
        Write-Host "  Total Records Processed: $($stats.total_records)" -ForegroundColor Cyan
        Write-Host "  Fraud Detections: $($stats.fraud_detections)" -ForegroundColor Cyan
        Write-Host "  Fraud Rate: $($stats.fraud_rate)%" -ForegroundColor Cyan
    }
} catch {
    Write-Host "Could not get inference stats: $($_.Exception.Message)" -ForegroundColor Yellow
}
