# Script to add more nodes AND upgrade to larger VM size
# This gives you the best of both worlds!

param(
    [int]$NodeCount = 2,
    [string]$VmSize = "Standard_D4s_v3"
)

Write-Host "=== AKS Cluster Scale + Upgrade ===" -ForegroundColor Green
Write-Host ""
Write-Host "This will:" -ForegroundColor Yellow
Write-Host "  1. Create a new node pool with larger VMs ($VmSize)" -ForegroundColor White
Write-Host "  2. Add $NodeCount nodes to the new pool" -ForegroundColor White
Write-Host "  3. Move pods to the new nodes" -ForegroundColor White
Write-Host "  4. Optionally delete the old small node pool" -ForegroundColor White
Write-Host ""

# Show VM size specs
$vmSpecs = @{
    "Standard_D2s_v3" = "2 vCPU, 8GB RAM"
    "Standard_D4s_v3" = "4 vCPU, 16GB RAM"
    "Standard_D8s_v3" = "8 vCPU, 32GB RAM"
    "Standard_D16s_v3" = "16 vCPU, 64GB RAM"
}

Write-Host "VM Size: $VmSize" -ForegroundColor Cyan
if ($vmSpecs.ContainsKey($VmSize)) {
    Write-Host "  Specs: $($vmSpecs[$VmSize])" -ForegroundColor White
}
Write-Host ""

Write-Host "Result:" -ForegroundColor Cyan
$totalCpu = switch ($VmSize) {
    "Standard_D2s_v3" { $NodeCount * 2 }
    "Standard_D4s_v3" { $NodeCount * 4 }
    "Standard_D8s_v3" { $NodeCount * 8 }
    "Standard_D16s_v3" { $NodeCount * 16 }
    default { $NodeCount * 4 }
}

$totalRam = switch ($VmSize) {
    "Standard_D2s_v3" { $NodeCount * 8 }
    "Standard_D4s_v3" { $NodeCount * 16 }
    "Standard_D8s_v3" { $NodeCount * 32 }
    "Standard_D16s_v3" { $NodeCount * 64 }
    default { $NodeCount * 16 }
}

Write-Host "  Total CPU: $totalCpu cores" -ForegroundColor White
Write-Host "  Total RAM: $totalRam GB" -ForegroundColor White
Write-Host ""

$confirm = Read-Host "Continue? (y/n)"
if ($confirm -ne "y" -and $confirm -ne "Y") {
    Write-Host "Cancelled." -ForegroundColor Yellow
    exit 0
}

Write-Host ""
Write-Host "Step 1: Creating new node pool with $VmSize..." -ForegroundColor Yellow
az aks nodepool add `
  --resource-group mlops_fraud_analytics `
  --cluster-name mlops-aks-cluster `
  --name np2 `
  --node-count $NodeCount `
  --node-vm-size $VmSize `
  --mode System

if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Failed to create new node pool" -ForegroundColor Red
    exit 1
}

Write-Host "[OK] New node pool created with $NodeCount nodes" -ForegroundColor Green
Write-Host ""
Write-Host "Step 2: Waiting for nodes to be ready..." -ForegroundColor Yellow
Write-Host "  (This may take 3-5 minutes)" -ForegroundColor White

# Wait for nodes
$maxWait = 300  # 5 minutes
$elapsed = 0
while ($elapsed -lt $maxWait) {
    $nodes = kubectl get nodes --no-headers 2>$null
    $readyNodes = ($nodes | Select-String "Ready").Count
    if ($readyNodes -ge ($NodeCount + 1)) {  # +1 for old node
        Write-Host "[OK] All nodes are ready!" -ForegroundColor Green
        break
    }
    Write-Host "  Waiting... ($readyNodes nodes ready)" -ForegroundColor Yellow
    Start-Sleep -Seconds 10
    $elapsed += 10
}

Write-Host ""
Write-Host "Step 3: Pods will automatically move to new nodes" -ForegroundColor Yellow
Write-Host "  Checking pod status..." -ForegroundColor White
Start-Sleep -Seconds 10
kubectl get pods -n mlops

Write-Host ""
Write-Host "Step 4: Delete old node pool? (optional)" -ForegroundColor Yellow
Write-Host "  This will remove the old small nodes to save costs." -ForegroundColor White
$deleteOld = Read-Host "Delete old nodepool1? (y/n)"

if ($deleteOld -eq "y" -or $deleteOld -eq "Y") {
    Write-Host "Deleting old node pool..." -ForegroundColor Yellow
    az aks nodepool delete `
      --resource-group mlops_fraud_analytics `
      --cluster-name mlops-aks-cluster `
      --name nodepool1
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[OK] Old node pool deleted" -ForegroundColor Green
    } else {
        Write-Host "[WARNING] Failed to delete old node pool. You can delete it manually later." -ForegroundColor Yellow
    }
} else {
    Write-Host "Keeping old node pool. You can delete it later with:" -ForegroundColor Yellow
    Write-Host "  az aks nodepool delete --resource-group mlops_fraud_analytics --cluster-name mlops-aks-cluster --name nodepool1" -ForegroundColor White
}

Write-Host ""
Write-Host "=== Upgrade Complete! ===" -ForegroundColor Green
Write-Host ""
Write-Host "New cluster capacity:" -ForegroundColor Cyan
Write-Host "  Nodes: $NodeCount" -ForegroundColor White
Write-Host "  VM Size: $VmSize" -ForegroundColor White
Write-Host "  Total CPU: $totalCpu cores" -ForegroundColor White
Write-Host "  Total RAM: $totalRam GB" -ForegroundColor White
Write-Host ""
Write-Host "Check status:" -ForegroundColor Yellow
Write-Host "  kubectl get nodes" -ForegroundColor White
Write-Host "  kubectl get pods -n mlops" -ForegroundColor White
Write-Host "  kubectl top nodes" -ForegroundColor White
