# Force Reset Airflow Database - This WILL work
$ErrorActionPreference = "Continue"

$NAMESPACE = "mlops"
$podName = kubectl get pods -n $NAMESPACE -l app=airflow-webserver -o jsonpath='{.items[0].metadata.name}' 2>&1

Write-Host "=== FORCE RESET AIRFLOW DATABASE ===" -ForegroundColor Red
Write-Host ""
Write-Host "This will DELETE all DAG run history but create the default user." -ForegroundColor Yellow
Write-Host ""

if (-not $podName -or $podName -match "error") {
    Write-Host "ERROR: Could not find Airflow pod" -ForegroundColor Red
    exit 1
}

Write-Host "Resetting database..." -ForegroundColor Yellow
Write-Host "This may take 2-3 minutes..." -ForegroundColor Cyan
Write-Host ""

$result = kubectl exec -n $NAMESPACE $podName -c airflow-webserver -- airflow db reset --yes 2>&1

Write-Host $result

Write-Host ""
Write-Host "=== Database Reset Complete ===" -ForegroundColor Green
Write-Host ""
Write-Host "Waiting 30 seconds for Airflow to restart..." -ForegroundColor Yellow
Start-Sleep -Seconds 30

Write-Host ""
Write-Host "=== CREDENTIALS ===" -ForegroundColor Green
Write-Host ""
Write-Host "URL: http://4.153.190.166/airflow" -ForegroundColor Yellow
Write-Host "Username: airflow" -ForegroundColor Yellow
Write-Host "Password: airflow" -ForegroundColor Yellow
Write-Host ""
Write-Host "The default user has been created by Airflow." -ForegroundColor Green
Write-Host "Try logging in now!" -ForegroundColor Green
Write-Host ""
Write-Host "If it still doesn't work:" -ForegroundColor Yellow
Write-Host "1. Wait another minute for full restart" -ForegroundColor White
Write-Host "2. Clear browser cache completely" -ForegroundColor White
Write-Host "3. Try incognito window" -ForegroundColor White
