# Fix Airflow Credentials Script
# This script creates/resets the Airflow admin user

$ErrorActionPreference = "Stop"

Write-Host "=== Fixing Airflow Credentials ===" -ForegroundColor Green
Write-Host ""

$NAMESPACE = "mlops"
$USERNAME = "airflow"
$PASSWORD = "airflow"
$EMAIL = "admin@example.com"

# Check if pod is running
Write-Host "Checking Airflow webserver pod..." -ForegroundColor Yellow
$podName = kubectl get pods -n $NAMESPACE -l app=airflow-webserver -o jsonpath='{.items[0].metadata.name}' 2>&1

if (-not $podName -or $podName -match "error") {
    Write-Host "ERROR: Could not find Airflow webserver pod" -ForegroundColor Red
    Write-Host "Please check if Airflow is deployed: kubectl get pods -n $NAMESPACE" -ForegroundColor Yellow
    exit 1
}

Write-Host "Found pod: $podName" -ForegroundColor Green
Write-Host ""

# Try to reset password first (works if user exists)
Write-Host "Attempting to reset password for existing user..." -ForegroundColor Yellow
$resetCmd = "airflow users reset-password --username $USERNAME --password $PASSWORD"
$resetResult = kubectl exec -n $NAMESPACE $podName -c airflow-webserver -- sh -c $resetCmd 2>&1

if ($LASTEXITCODE -eq 0 -and $resetResult -match "password" -or $resetResult -match "reset" -or $resetResult -match "Success") {
    Write-Host "SUCCESS: Password reset!" -ForegroundColor Green
    $success = $true
} else {
    # If reset failed, try to create the user
    Write-Host "User might not exist. Creating new user..." -ForegroundColor Yellow
    Write-Host "  Username: $USERNAME" -ForegroundColor Cyan
    Write-Host "  Password: $PASSWORD" -ForegroundColor Cyan
    Write-Host ""

    $createUserCmd = "airflow users create --username $USERNAME --firstname Admin --lastname User --role Admin --email $EMAIL --password $PASSWORD"
    $result = kubectl exec -n $NAMESPACE $podName -c airflow-webserver -- sh -c $createUserCmd 2>&1

    if ($LASTEXITCODE -eq 0 -or $result -match "created" -or $result -match "Success") {
        Write-Host "SUCCESS: Airflow user created!" -ForegroundColor Green
        $success = $true
    } else {
        Write-Host "WARNING: Command output: $result" -ForegroundColor Yellow
        Write-Host "Trying alternative method..." -ForegroundColor Yellow
        
        # Try with --use-random-password flag and then reset
        $createCmd2 = "airflow users create --username $USERNAME --firstname Admin --lastname User --role Admin --email $EMAIL --use-random-password"
        $result2 = kubectl exec -n $NAMESPACE $podName -c airflow-webserver -- sh -c $createCmd2 2>&1
        
        if ($LASTEXITCODE -eq 0) {
            # Now reset the password
            $resetResult2 = kubectl exec -n $NAMESPACE $podName -c airflow-webserver -- sh -c $resetCmd 2>&1
            if ($LASTEXITCODE -eq 0) {
                Write-Host "SUCCESS: User created and password set!" -ForegroundColor Green
                $success = $true
            } else {
                Write-Host "ERROR: Could not set password" -ForegroundColor Red
                $success = $false
            }
        } else {
            Write-Host "ERROR: Could not create user" -ForegroundColor Red
            $success = $false
        }
    }
}

if ($success) {
    Write-Host ""
    Write-Host "=== SUCCESS ===" -ForegroundColor Green
    Write-Host ""
    Write-Host "Login credentials:" -ForegroundColor Cyan
    Write-Host "  URL: http://4.153.190.166/airflow" -ForegroundColor Yellow
    Write-Host "  Username: $USERNAME" -ForegroundColor Yellow
    Write-Host "  Password: $PASSWORD" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "You can now login to Airflow!" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "=== TROUBLESHOOTING ===" -ForegroundColor Yellow
    Write-Host "If login still doesn't work, try:" -ForegroundColor Yellow
    Write-Host "1. Check Airflow logs: kubectl logs -n $NAMESPACE $podName -c airflow-webserver" -ForegroundColor Cyan
    Write-Host "2. Verify database connection" -ForegroundColor Cyan
    Write-Host "3. Try accessing via port-forward: kubectl port-forward -n $NAMESPACE svc/airflow-webserver 8080:8080" -ForegroundColor Cyan
}

Write-Host ""
Write-Host "=== Done ===" -ForegroundColor Green
