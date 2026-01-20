# Verify Airflow Login and Test
$ErrorActionPreference = "Continue"

Write-Host "=== Airflow Login Verification ===" -ForegroundColor Green
Write-Host ""

Write-Host "Credentials:" -ForegroundColor Cyan
Write-Host "  URL: http://4.153.190.166/airflow" -ForegroundColor Yellow
Write-Host "  Username: airflow" -ForegroundColor Yellow
Write-Host "  Password: airflow" -ForegroundColor Yellow
Write-Host ""

Write-Host "=== Troubleshooting Steps ===" -ForegroundColor Yellow
Write-Host ""

Write-Host "1. Clear browser cache and cookies:" -ForegroundColor Cyan
Write-Host "   - Press Ctrl+Shift+Delete" -ForegroundColor White
Write-Host "   - Clear cookies and cached files" -ForegroundColor White
Write-Host ""

Write-Host "2. Try incognito/private window:" -ForegroundColor Cyan
Write-Host "   - Open new incognito window" -ForegroundColor White
Write-Host "   - Go to http://4.153.190.166/airflow" -ForegroundColor White
Write-Host ""

Write-Host "3. Check if Airflow is ready:" -ForegroundColor Cyan
$health = Invoke-WebRequest -Uri "http://4.153.190.166/airflow/api/v2/monitor/health" -UseBasicParsing -ErrorAction SilentlyContinue
if ($health.StatusCode -eq 200) {
    Write-Host "   Airflow is running and healthy" -ForegroundColor Green
} else {
    Write-Host "   Airflow health check failed" -ForegroundColor Red
}
Write-Host ""

Write-Host "4. If login still fails, try database reset:" -ForegroundColor Cyan
Write-Host "   This will delete DAG history but guarantee the user works" -ForegroundColor Yellow
Write-Host ""
Write-Host "   Run:" -ForegroundColor White
Write-Host "   kubectl exec -n mlops deployment/airflow-webserver -c airflow-webserver -- airflow db reset --yes" -ForegroundColor Cyan
Write-Host ""

Write-Host "5. After database reset, wait 2 minutes for Airflow to restart" -ForegroundColor Cyan
Write-Host "   Then try logging in with: airflow / airflow" -ForegroundColor White
