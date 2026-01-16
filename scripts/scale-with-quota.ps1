# Script to scale AKS considering quota limits
# This version checks quota and suggests alternatives

Write-Host "=== AKS Scaling (Quota-Aware) ===" -ForegroundColor Green
Write-Host ""

# Check current quota
Write-Host "Checking Azure quota..." -ForegroundColor Yellow
$quota = az vm list-usage --location eastus2 --query "[?contains(name.value, 'standardDSv3Family')].{Current:currentValue, Limit:limit}" -o json 2>&1 | ConvertFrom-Json

if ($quota) {
    $available = $quota.Limit - $quota.Current
    Write-Host "  Available vCPU quota: $available" -ForegroundColor Cyan
    Write-Host ""
} else {
    Write-Host "  Could not check quota, proceeding with caution..." -ForegroundColor Yellow
    $available = 0
}

Write-Host "Current cluster:" -ForegroundColor Yellow
Write-Host "  1 node × Standard_D2s_v3 (2 vCPU) = 2 vCPU in use" -ForegroundColor White
Write-Host ""

Write-Host "Scaling options:" -ForegroundColor Cyan
Write-Host ""
Write-Host "  [1] Add 1 more node (Standard_D2s_v3)" -ForegroundColor White
Write-Host "      Result: 2 nodes × 2 vCPU = 4 vCPU total" -ForegroundColor Gray
Write-Host "      Needs: 2 vCPU quota" -ForegroundColor Gray
Write-Host ""
Write-Host "  [2] Upgrade existing node to Standard_D4s_v3" -ForegroundColor White
Write-Host "      Result: 1 node × 4 vCPU = 4 vCPU total" -ForegroundColor Gray
Write-Host "      Needs: 2 vCPU quota (replaces existing 2 vCPU)" -ForegroundColor Gray
Write-Host ""
Write-Host "  [3] Request quota increase (then scale to 2×D4s_v3)" -ForegroundColor White
Write-Host "      Result: 2 nodes × 4 vCPU = 8 vCPU total" -ForegroundColor Gray
Write-Host "      Needs: Request quota increase first" -ForegroundColor Gray
Write-Host ""

$choice = Read-Host "Select option (1-3)"

switch ($choice) {
    "1" {
        Write-Host ""
        Write-Host "Adding 1 more Standard_D2s_v3 node..." -ForegroundColor Yellow
        az aks scale `
          --resource-group mlops_fraud_analytics `
          --name mlops-aks-cluster `
          --node-count 2
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host "[OK] Added 1 more node!" -ForegroundColor Green
            Write-Host "  Total: 2 nodes × 2 vCPU = 4 vCPU" -ForegroundColor White
            Write-Host "  Total: 2 nodes × 8GB = 16GB RAM" -ForegroundColor White
        }
    }
    "2" {
        Write-Host ""
        Write-Host "Upgrading to Standard_D4s_v3..." -ForegroundColor Yellow
        Write-Host "  Creating new node pool..." -ForegroundColor White
        
        az aks nodepool add `
          --resource-group mlops_fraud_analytics `
          --cluster-name mlops-aks-cluster `
          --name np2 `
          --node-count 1 `
          --node-vm-size Standard_D4s_v3 `
          --mode System
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host "[OK] New node pool created" -ForegroundColor Green
            Write-Host "  Waiting for node to be ready..." -ForegroundColor Yellow
            Start-Sleep -Seconds 30
            
            Write-Host "  Deleting old node pool..." -ForegroundColor Yellow
            az aks nodepool delete `
              --resource-group mlops_fraud_analytics `
              --cluster-name mlops-aks-cluster `
              --name nodepool1
            
            Write-Host "[OK] Upgrade complete!" -ForegroundColor Green
            Write-Host "  Total: 1 node × 4 vCPU = 4 vCPU" -ForegroundColor White
            Write-Host "  Total: 1 node × 16GB = 16GB RAM" -ForegroundColor White
        }
    }
    "3" {
        Write-Host ""
        Write-Host "To request quota increase:" -ForegroundColor Yellow
        Write-Host "  1. Go to: https://portal.azure.com" -ForegroundColor White
        Write-Host "  2. Search for 'Subscriptions' → Your subscription" -ForegroundColor White
        Write-Host "  3. Click 'Usage + quotas'" -ForegroundColor White
        Write-Host "  4. Search for 'standardDSv3Family'" -ForegroundColor White
        Write-Host "  5. Click 'Request increase'" -ForegroundColor White
        Write-Host "  6. Request at least 8 more vCPU" -ForegroundColor White
        Write-Host ""
        Write-Host "Or use Azure CLI:" -ForegroundColor Yellow
        Write-Host "  az vm list-usage --location eastus2 -o table" -ForegroundColor White
        Write-Host "  # Then request increase via portal" -ForegroundColor Gray
        Write-Host ""
        Write-Host "After quota is increased, run:" -ForegroundColor Yellow
        Write-Host "  .\scripts\scale-and-upgrade-aks.ps1 -NodeCount 2 -VmSize Standard_D4s_v3" -ForegroundColor White
    }
    default {
        Write-Host "Invalid choice" -ForegroundColor Red
    }
}
