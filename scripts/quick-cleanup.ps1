# Quick Cleanup Script - Remove problematic pods only
# Use this when you want to clean up just the problematic services

$ErrorActionPreference = "Stop"

function Write-ColorOutput($ForegroundColor) {
    $fc = $host.UI.RawUI.ForegroundColor
    $host.UI.RawUI.ForegroundColor = $ForegroundColor
    if ($args) {
        Write-Output $args
    }
    $host.UI.RawUI.ForegroundColor = $fc
}

Write-ColorOutput Green "=== QUICK CLEANUP: Problematic Services ==="
Write-Output "This will only remove problematic services (like Flower)"
Write-Output ""

$NAMESPACE = "mlops"

# Check current status
Write-ColorOutput Yellow "Current pod status:"
kubectl get pods -n $NAMESPACE

# Remove only problematic services
Write-ColorOutput Yellow "`nCleaning up problematic services..."

# Remove Flower (the main problematic service)
Write-Output "Removing Flower deployment..."
kubectl delete deployment flower -n $NAMESPACE --ignore-not-found
kubectl delete service flower -n $NAMESPACE --ignore-not-found

# Remove any crashlooping pods
$crashLoopPods = kubectl get pods -n $NAMESPACE -o jsonpath='{.items[?(@.status.containerStatuses[0].restartCount>5)].metadata.name}'
if ($crashLoopPods) {
    Write-Output "Removing crashlooping pods: $crashLoopPods"
    kubectl delete pod $crashLoopPods -n $NAMESPACE --ignore-not-found
}

# Clean up evicted pods
$evictedPods = kubectl get pods -n $NAMESPACE -o jsonpath='{.items[?(@.status.phase=="Evicted")].metadata.name}'
if ($evictedPods) {
    Write-Output "Removing evicted pods: $evictedPods"
    kubectl delete pod $evictedPods -n $NAMESPACE --ignore-not-found
}

Write-ColorOutput Green "`n=== QUICK CLEANUP COMPLETE ==="

# Redeploy Flower with fixed configuration
Write-ColorOutput Yellow "Redeploying Flower with fixed configuration..."
kubectl apply -f k8s/flower.yaml

Write-Output "Waiting for Flower to be ready..."
kubectl rollout status deployment/flower -n $NAMESPACE --timeout=120s

Write-ColorOutput Green "`n=== CLEANUP & REDEPLOY COMPLETE ==="
kubectl get pods -n $NAMESPACE
