# Quick Endpoint Test Script
$ErrorActionPreference = "Continue"

$INGRESS_IP = "4.153.190.166"
$BASE_URL = "http://$INGRESS_IP"
$NAMESPACE = "mlops"

Write-Host "=== Testing Azure MLOps Endpoints ===" -ForegroundColor Green
Write-Host "Base URL: $BASE_URL" -ForegroundColor Cyan
Write-Host ""

# Test endpoints
$endpoints = @(
    @{Name="Airflow UI"; Url="$BASE_URL/airflow"},
    @{Name="MLflow UI"; Url="$BASE_URL/mlflow"},
    @{Name="Fraud Guard UI"; Url="$BASE_URL/fraudguard"},
    @{Name="Inference Health"; Url="$BASE_URL/inference/health"},
    @{Name="Flower UI"; Url="$BASE_URL/flower"}
)

foreach ($endpoint in $endpoints) {
    Write-Host "Testing: $($endpoint.Name)" -ForegroundColor Yellow
    Write-Host "  URL: $($endpoint.Url)"
    try {
        $response = Invoke-WebRequest -Uri $endpoint.Url -UseBasicParsing -TimeoutSec 10 -ErrorAction Stop
        Write-Host "  Status: $($response.StatusCode) - SUCCESS" -ForegroundColor Green
    } catch {
        $statusCode = 0
        if ($_.Exception.Response) {
            $statusCode = $_.Exception.Response.StatusCode.value__
        }
        Write-Host "  Status: $statusCode - FAILED" -ForegroundColor Red
        Write-Host "  Error: $($_.Exception.Message)" -ForegroundColor Red
    }
    Write-Host ""
}

# Check Kubernetes pods
Write-Host "=== Kubernetes Pod Status ===" -ForegroundColor Yellow
try {
    $pods = kubectl get pods -n $NAMESPACE 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host $pods
    } else {
        Write-Host "Could not check pods. Make sure kubectl is configured." -ForegroundColor Yellow
    }
} catch {
    Write-Host "Could not check pods: $_" -ForegroundColor Red
}

Write-Host ""
Write-Host "=== Access Information ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Airflow UI: $BASE_URL/airflow"
Write-Host "  Username: airflow"
Write-Host "  Password: airflow"
Write-Host ""
Write-Host "MLflow UI: $BASE_URL/mlflow"
Write-Host "Fraud Guard UI: $BASE_URL/fraudguard"
Write-Host "Inference API: $BASE_URL/inference"
Write-Host "Flower UI: $BASE_URL/flower"
