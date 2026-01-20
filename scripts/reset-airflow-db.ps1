# Reset Airflow Database to Create Default User
$ErrorActionPreference = "Continue"

$NAMESPACE = "mlops"
$podName = kubectl get pods -n $NAMESPACE -l app=airflow-webserver -o jsonpath='{.items[0].metadata.name}' 2>&1

Write-Host "=== Resetting Airflow Database ===" -ForegroundColor Yellow
Write-Host ""
Write-Host "WARNING: This will DELETE all DAG run history!" -ForegroundColor Red
Write-Host "But it will create the default user: airflow / airflow" -ForegroundColor Yellow
Write-Host ""

$confirm = Read-Host "Do you want to proceed? (yes/no)"

if ($confirm -ne "yes") {
    Write-Host "Cancelled." -ForegroundColor Yellow
    exit 0
}

Write-Host ""
Write-Host "Resetting Airflow database..." -ForegroundColor Yellow
Write-Host "This may take 1-2 minutes..." -ForegroundColor Cyan

$result = kubectl exec -n $NAMESPACE $podName -c airflow-webserver -- airflow db reset --yes 2>&1

Write-Host $result

if ($LASTEXITCODE -eq 0 -or $result -match "Database reset") {
    Write-Host ""
    Write-Host "=== SUCCESS ===" -ForegroundColor Green
    Write-Host ""
    Write-Host "Database reset complete!" -ForegroundColor Green
    Write-Host "Default user has been created." -ForegroundColor Green
    Write-Host ""
    Write-Host "Airflow Login Credentials:" -ForegroundColor Cyan
    Write-Host "  URL: http://4.153.190.166/airflow" -ForegroundColor Yellow
    Write-Host "  Username: airflow" -ForegroundColor Yellow
    Write-Host "  Password: airflow" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Wait 30 seconds for Airflow to restart, then try logging in." -ForegroundColor Cyan
} else {
    Write-Host ""
    Write-Host "Database reset may have failed or is still in progress." -ForegroundColor Yellow
    Write-Host "Check pod logs:" -ForegroundColor Cyan
    Write-Host "  kubectl logs -n $NAMESPACE $podName -c airflow-webserver --tail=50" -ForegroundColor White
}
