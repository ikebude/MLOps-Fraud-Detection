# Health Check Script for MLOps Fraud Detection
# Monitors all services and provides detailed status

$ErrorActionPreference = "Stop"

function Write-ColorOutput($ForegroundColor) {
    $fc = $host.UI.RawUI.ForegroundColor
    $host.UI.RawUI.ForegroundColor = $ForegroundColor
    if ($args) {
        Write-Output $args
    }
    $host.UI.RawUI.ForegroundColor = $fc
}

function Test-ServiceHealth {
    param(
        [string]$ServiceName,
        [string]$Namespace,
        [string]$Path = "/health"
    )
    
    try {
        $pod = kubectl get pods -n $Namespace -l app=$ServiceName -o jsonpath='{.items[0].metadata.name}' 2>$null
        if ($pod) {
            $response = kubectl exec $pod -n $Namespace -- curl -s -w "%{http_code}" -o /dev/null http://localhost:$Port$Path 2>$null
            if ($response -eq "200") {
                return "Healthy"
            } else {
                return "Unhealthy ($response)"
            }
        } else {
            return "Not Found"
        }
    } catch {
        return "Error"
    }
}

Write-ColorOutput Green "=== MLOPS FRAUD DETECTION HEALTH CHECK ==="
Write-Output "Checking all services..."
Write-Output ""

$NAMESPACE = "mlops"

# Overall cluster status
Write-ColorOutput Yellow "📊 Cluster Status:"
try {
    $nodes = kubectl get nodes -o json | ConvertFrom-Json
    $readyNodes = ($nodes.items | Where-Object { $_.status.conditions[0].type -eq "Ready" -and $_.status.conditions[0].status -eq "True" }).Count
    Write-Output "  Nodes: $readyNodes/$($nodes.items.Count) Ready"
} catch {
    Write-ColorOutput Red "  [ERROR] Cannot connect to cluster"
}

# Pod status
Write-ColorOutput Yellow "`n🚀 Pod Status:"
$pods = kubectl get pods -n $NAMESPACE -o wide
Write-Output $pods

# Detailed pod analysis
$podData = kubectl get pods -n $NAMESPACE -o json | ConvertFrom-Json
$totalPods = $podData.items.Count
$runningPods = ($podData.items | Where-Object { $_.status.phase -eq "Running" }).Count
$readyPods = ($podData.items | Where-Object { $_.status.containerStatuses[0].ready -eq $true }).Count
$crashLoopPods = ($podData.items | Where-Object { $_.status.containerStatuses[0].restartCount -gt 5 }).Count

Write-ColorOutput Cyan "`n📈 Pod Summary:"
Write-Output "  Total: $totalPods"
Write-Output "  Running: $runningPods"
Write-Output "  Ready: $readyPods"
Write-Output "  CrashLoop: $crashLoopPods"

# Service status
Write-ColorOutput Yellow "`n🌐 Service Status:"
$services = kubectl get svc -n $NAMESPACE
Write-Output $services

# Ingress status
Write-ColorOutput Yellow "`n🔗 Ingress Status:"
$ingress = kubectl get ingress -n $NAMESPACE
Write-Output $ingress

$ingressIP = (kubectl get svc -n ingress-nginx -o jsonpath='{.items[0].status.loadBalancer.ingress[0].ip}' 2>$null)
if ($ingressIP) {
    Write-ColorOutput Green "  External IP: $ingressIP"
    Write-Output ""
    Write-ColorOutput Cyan "🌍 Access URLs:"
    Write-Output "  FraudGuard: http://fraudguard.$ingressIP.nip.io"
    Write-Output "  Airflow:    http://airflow.$ingressIP.nip.io"
    Write-Output "  MLflow:     http://mlflow.$ingressIP.nip.io"
    Write-Output "  Inference:  http://inference.$ingressIP.nip.io"
    Write-Output "  Flower:     http://flower.$ingressIP.nip.io"
}

# Resource usage
Write-ColorOutput Yellow "`n💾 Resource Usage:"
try {
    $resourceUsage = kubectl top pods -n $NAMESPACE 2>$null
    if ($resourceUsage) {
        Write-Output $resourceUsage
    } else {
        Write-ColorOutput Yellow "  Metrics API not available (install metrics-server)"
    }
} catch {
    Write-ColorOutput Yellow "  Resource metrics not available"
}

# Health recommendations
Write-ColorOutput Yellow "`n🔍 Health Analysis:"

if ($crashLoopPods -gt 0) {
    Write-ColorOutput Red "  ⚠️  Found $crashLoopPods pods in CrashLoopBackOff"
    Write-Output "     Run: .\scripts\quick-cleanup.ps1"
}

if ($readyPods -lt $totalPods) {
    Write-ColorOutput Yellow "  ⚠️  Some pods are not ready"
    Write-Output "     Check logs: kubectl logs <pod-name> -n $NAMESPACE"
}

if ($readyPods -eq $totalPods -and $crashLoopPods -eq 0) {
    Write-ColorOutput Green "  ✅ All services are healthy!"
}

# Recent events
Write-ColorOutput Yellow "`n📋 Recent Events (last 5 minutes):"
$events = kubectl get events -n $NAMESPACE --sort-by='.lastTimestamp' -o custom-columns=LAST_SEEN:.lastTimestamp,TYPE:.type,REASON:.reason,OBJECT:.involvedObject.name,MESSAGE:.message | Select-Object -First 10
Write-Output $events

Write-ColorOutput Green "`n=== HEALTH CHECK COMPLETE ==="
