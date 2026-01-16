# Quick cleanup script - removes all deployments (optional)

Write-Host "This will delete all deployments in the mlops namespace" -ForegroundColor Yellow
Write-Host "This is optional - the deploy script will update existing resources" -ForegroundColor Yellow
Write-Host ""

$confirm = Read-Host "Delete all deployments? (y/n)"
if ($confirm -ne "y" -and $confirm -ne "Y") {
    Write-Host "Skipped. Existing resources will be updated." -ForegroundColor Green
    exit 0
}

Write-Host "Deleting deployments..." -ForegroundColor Yellow
kubectl delete deployment --all -n mlops
kubectl delete service --all -n mlops
kubectl delete configmap --all -n mlops

Write-Host "[OK] Cleanup complete" -ForegroundColor Green
Write-Host "Now run: .\scripts\deploy-azure-complete.ps1" -ForegroundColor Cyan
