# Quick Restart FraudGuard (to pick up any changes)
$NAMESPACE = "mlops"

Write-Host "Restarting FraudGuard deployment..." -ForegroundColor Yellow
kubectl rollout restart deployment/fraudguard -n $NAMESPACE

Write-Host "Waiting for rollout..." -ForegroundColor Yellow
kubectl rollout status deployment/fraudguard -n $NAMESPACE --timeout=120s

Write-Host ""
Write-Host "FraudGuard restarted!" -ForegroundColor Green
Write-Host "Wait 30 seconds, then:" -ForegroundColor Cyan
Write-Host "1. Hard refresh browser (Ctrl+Shift+R)" -ForegroundColor White
Write-Host "2. Check browser console (F12) for errors" -ForegroundColor White
Write-Host "3. Test API: http://4.153.190.166/fraudguard/api/data?refresh=1" -ForegroundColor White
