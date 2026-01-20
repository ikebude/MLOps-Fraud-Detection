# Test Azure Endpoints Script
# This script tests all deployed endpoints and UIs to verify they're working

$ErrorActionPreference = "Continue"

# Colors for output
function Write-ColorOutput($ForegroundColor) {
    $fc = $host.UI.RawUI.ForegroundColor
    $host.UI.RawUI.ForegroundColor = $ForegroundColor
    if ($args) {
        Write-Output $args
    }
    $host.UI.RawUI.ForegroundColor = $fc
}

# Configuration
$INGRESS_IP = "4.153.190.166"
$BASE_URL = "http://$INGRESS_IP"
$NAMESPACE = "mlops"

Write-ColorOutput Green "=== Azure MLOps Endpoints Test ==="
Write-Output ""
Write-ColorOutput Cyan "Testing endpoints at: $BASE_URL"
Write-Output ""

# Test results
$testResults = @()

function Test-Endpoint {
    param(
        [string]$Name,
        [string]$Url,
        [string]$Method = "GET",
        [hashtable]$Headers = @{},
        [string]$Body = $null,
        [int]$ExpectedStatus = 200
    )
    
    Write-Output "Testing: $Name"
    Write-Output "  URL: $Url"
    
    try {
        $params = @{
            Uri = $Url
            Method = $Method
            Headers = $Headers
            TimeoutSec = 30
            UseBasicParsing = $true
            ErrorAction = "Stop"
        }
        
        if ($Body) {
            $params.Body = $Body
            $params.ContentType = "application/json"
        }
        
        $response = Invoke-WebRequest @params
        $status = $response.StatusCode
        
        if ($status -eq $ExpectedStatus -or ($ExpectedStatus -eq 200 -and $status -lt 400)) {
            Write-ColorOutput Green "  ✓ Status: $status - SUCCESS"
            $testResults += @{
                Name = $Name
                Status = "SUCCESS"
                StatusCode = $status
                Message = "Working correctly"
            }
            return $true
        } else {
            Write-ColorOutput Yellow "  ⚠ Status: $status - Unexpected status code"
            $testResults += @{
                Name = $Name
                Status = "WARNING"
                StatusCode = $status
                Message = "Unexpected status code"
            }
            return $false
        }
    } catch {
        $statusCode = 0
        if ($_.Exception.Response) {
            $statusCode = $_.Exception.Response.StatusCode.value__
        }
        $errorMsg = $_.Exception.Message
        Write-ColorOutput Red "  ✗ FAILED - Status: $statusCode"
        Write-ColorOutput Red "    Error: $errorMsg"
        $testResults += @{
            Name = $Name
            Status = "FAILED"
            StatusCode = $statusCode
            Message = $errorMsg
        }
        return $false
    }
    Write-Output ""
}

# Test 1: Airflow UI
Write-ColorOutput Yellow "=== Testing Airflow UI ==="
Test-Endpoint -Name "Airflow UI" -Url "$BASE_URL/airflow" -ExpectedStatus 200
Test-Endpoint -Name "Airflow Health" -Url "$BASE_URL/airflow/api/v2/monitor/health" -ExpectedStatus 200

# Test 2: MLflow UI
Write-ColorOutput Yellow "=== Testing MLflow UI ==="
Test-Endpoint -Name "MLflow UI" -Url "$BASE_URL/mlflow" -ExpectedStatus 200
Test-Endpoint -Name "MLflow Health" -Url "$BASE_URL/mlflow/health" -ExpectedStatus 200

# Test 3: Fraud Guard UI
Write-ColorOutput Yellow "=== Testing Fraud Guard UI ==="
Test-Endpoint -Name "Fraud Guard UI" -Url "$BASE_URL/fraudguard" -ExpectedStatus 200
Test-Endpoint -Name "Fraud Guard API Health" -Url "$BASE_URL/fraudguard/api/health" -ExpectedStatus 200
Test-Endpoint -Name "Fraud Guard API Data" -Url "$BASE_URL/fraudguard/api/data" -ExpectedStatus 200

# Test 4: Inference API
Write-ColorOutput Yellow "=== Testing Inference API ==="
Test-Endpoint -Name "Inference Health" -Url "$BASE_URL/inference/health" -ExpectedStatus 200
Test-Endpoint -Name "Inference Stats" -Url "$BASE_URL/inference/inference/stats" -ExpectedStatus 200
Test-Endpoint -Name "Inference Results" -Url "$BASE_URL/inference/inference/results" -ExpectedStatus 200

# Test 5: Flower UI
Write-ColorOutput Yellow "=== Testing Flower UI ==="
Test-Endpoint -Name "Flower UI" -Url "$BASE_URL/flower" -ExpectedStatus 200

# Test 6: Check Kubernetes Services
Write-ColorOutput Yellow "=== Checking Kubernetes Services ==="
Write-Output "Checking pod status..."
try {
    $pods = kubectl get pods -n $NAMESPACE -o json | ConvertFrom-Json
    Write-Output ""
    Write-ColorOutput Cyan "Pod Status:"
    foreach ($pod in $pods.items) {
        $status = $pod.status.phase
        $ready = ($pod.status.containerStatuses | Where-Object { $_.ready -eq $true }).Count
        $total = $pod.status.containerStatuses.Count
        $name = $pod.metadata.name
        
        if ($status -eq "Running" -and $ready -eq $total) {
            Write-ColorOutput Green "  ✓ $name - $status ($ready/$total ready)"
        } elseif ($status -eq "Running") {
            Write-ColorOutput Yellow "  ⚠ $name - $status ($ready/$total ready)"
        } else {
            Write-ColorOutput Red "  ✗ $name - $status ($ready/$total ready)"
        }
    }
} catch {
    Write-ColorOutput Red "  ✗ Failed to check pod status: $_"
}

Write-Output ""
Write-ColorOutput Cyan "Service Status:"
try {
    $services = kubectl get svc -n $NAMESPACE -o json | ConvertFrom-Json
    foreach ($service in $services.items) {
        $name = $service.metadata.name
        $type = $service.spec.type
        $ports = ($service.spec.ports | ForEach-Object { "$($_.port)" }) -join ","
        Write-Output "  $name - Type: $type, Ports: $ports"
    }
} catch {
    Write-ColorOutput Red "  ✗ Failed to check service status: $_"
}

# Test 7: Check MLflow Models
Write-ColorOutput Yellow "=== Checking MLflow Models ==="
Write-Output "Attempting to check MLflow for registered models..."
try {
    # Try to access MLflow API
    $mlflowModelsUrl = "$BASE_URL/mlflow/api/2.0/mlflow/registered-models/search"
    $response = Invoke-WebRequest -Uri $mlflowModelsUrl -Method POST -ContentType "application/json" -Body '{"max_results": 10}' -UseBasicParsing -ErrorAction SilentlyContinue
    if ($response.StatusCode -eq 200) {
        $models = $response.Content | ConvertFrom-Json
        if ($models.registered_models -and $models.registered_models.Count -gt 0) {
            Write-ColorOutput Green "  ✓ Found $($models.registered_models.Count) registered model(s)"
            foreach ($model in $models.registered_models) {
                Write-Output "    - $($model.name) (Latest Version: $($model.latest_versions[0].version))"
            }
        } else {
            Write-ColorOutput Yellow "  ⚠ No registered models found in MLflow"
        }
    }
} catch {
    Write-ColorOutput Yellow "  ⚠ Could not check MLflow models: $_"
}

# Test 8: Check Fraud API
Write-ColorOutput Yellow "=== Checking Fraud API ==="
$FRAUD_API_URL = "https://3consult-ng.com/fraud_api.php"
Write-Output "Testing external Fraud API: $FRAUD_API_URL"
try {
    $queryParams = @{
        offset = 0
        limit = 10
    }
    $uri = [System.UriBuilder]::new($FRAUD_API_URL)
    $uri.Query = ($queryParams.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" }) -join '&'
    $response = Invoke-WebRequest -Uri $uri.Uri -Method GET -UseBasicParsing -TimeoutSec 30 -ErrorAction Stop
    if ($response.StatusCode -eq 200) {
        $data = $response.Content | ConvertFrom-Json
        $recordCount = 0
        if ($data -is [array]) {
            $recordCount = $data.Count
        } elseif ($data.data -is [array]) {
            $recordCount = $data.data.Count
        } elseif ($data.transactions -is [array]) {
            $recordCount = $data.transactions.Count
        }
        
        if ($recordCount -gt 0) {
            Write-ColorOutput Green "  ✓ Fraud API is accessible and has data"
            Write-Output "    Sample records available: $recordCount"
        } else {
            Write-ColorOutput Yellow "  ⚠ Fraud API accessible but no records found in response"
        }
    }
} catch {
    Write-ColorOutput Red "  ✗ Fraud API test failed: $_"
}

# Summary
Write-Output ""
Write-ColorOutput Green "=== Test Summary ==="
Write-Output ""
$successCount = ($testResults | Where-Object { $_.Status -eq "SUCCESS" }).Count
$warningCount = ($testResults | Where-Object { $_.Status -eq "WARNING" }).Count
$failedCount = ($testResults | Where-Object { $_.Status -eq "FAILED" }).Count

Write-Output "Total Tests: $($testResults.Count)"
Write-ColorOutput Green "  Success: $successCount"
Write-ColorOutput Yellow "  Warnings: $warningCount"
Write-ColorOutput Red "  Failed: $failedCount"
Write-Output ""

if ($failedCount -eq 0) {
    Write-ColorOutput Green "✓ All critical endpoints are working!"
} else {
    Write-ColorOutput Red "✗ Some endpoints failed. Please check the errors above."
}

Write-Output ""
Write-ColorOutput Cyan "=== Access Information ==="
Write-Output ""
Write-Output "Airflow UI:"
Write-Output "  URL: $BASE_URL/airflow"
Write-Output "  Username: airflow"
Write-Output "  Password: airflow"
Write-Output ""
Write-Output "MLflow UI:"
Write-Output "  URL: $BASE_URL/mlflow"
Write-Output ""
Write-Output "Fraud Guard UI:"
Write-Output "  URL: $BASE_URL/fraudguard"
Write-Output ""
Write-Output "Inference API:"
Write-Output "  URL: $BASE_URL/inference"
Write-Output ""
Write-Output "Flower UI:"
Write-Output "  URL: $BASE_URL/flower"
Write-Output ""
