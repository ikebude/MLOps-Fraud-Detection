# Verify MLOps Fraud Detection Deployment
# This script checks all components are running correctly

$ErrorActionPreference = "Stop"

function Write-ColorOutput($ForegroundColor) {
    $fc = $host.UI.RawUI.ForegroundColor
    $host.UI.RawUI.ForegroundColor = $ForegroundColor
    if ($args) {
        Write-Output $args
    }
    $host.UI.RawUI.ForegroundColor = $fc
}

Write-ColorOutput Green "=== MLOps Fraud Detection Deployment Verification ==="

$NAMESPACE = "mlops"

# Check namespace
Write-Host "`n1. Checking namespace..."
try {
    kubectl get namespace $NAMESPACE | Out-Null
    Write-ColorOutput Green "[OK] Namespace $NAMESPACE exists"
} catch {
    Write-ColorOutput Red "[ERROR] Namespace $NAMESPACE not found"
    exit 1
}

# Check all pods
Write-Host "`n2. Checking pod status..."
$pods = kubectl get pods -n $NAMESPACE -o json
$podItems = $pods.items | Sort-Object -Property metadata.name

$allReady = $true
foreach ($pod in $podItems) {
    $name = $pod.metadata.name
    $status = $pod.status.phase
    $ready = $pod.status.conditions | Where-Object { $_.type -eq "Ready" } | Select-Object -ExpandProperty status
    
    if ($ready -eq "True") {
        Write-ColorOutput Green "[OK] $name - Ready"
    } else {
        Write-ColorOutput Red "[ERROR] $name - $status (Not Ready)"
        $allReady = $false
        
        # Show recent events for failing pod
        Write-Host "   Recent events for $name:"
        $events = kubectl get events -n $NAMESPACE --field-selector involvedObject.name=$name --sort-by='.lastTimestamp' -o json | ConvertFrom-Json
        $recentEvents = $events.items | Select-Object -Last 3
        foreach ($event in $recentEvents) {
            Write-Host "   - $($event.type): $($event.message)"
        }
    }
}

# Check services
Write-Host "`n3. Checking services..."
$services = kubectl get svc -n $NAMESPACE -o json
foreach ($svc in $services.items) {
    $name = $svc.metadata.name
    $type = $svc.spec.type
    $port = $svc.spec.ports[0].port
    
    Write-ColorOutput Green "[OK] $name - $type:$port"
}

# Check ingress
Write-Host "`n4. Checking ingress..."
try {
    $ingress = kubectl get ingress -n $NAMESPACE -o json
    foreach ($ing in $ingress.items) {
        $name = $ing.metadata.name
        $className = $ing.spec.ingressClassName
        Write-ColorOutput Green "[OK] $name - Class: $className"
        
        # Show hosts
        foreach ($rule in $ing.spec.rules) {
            Write-Host "   Host: $($rule.host)"
        }
    }
} catch {
    Write-ColorOutput Yellow "[WARN] No ingress found or ingress controller not available"
}

# Check database connectivity
Write-Host "`n5. Checking database connectivity..."
try {
    $postgresPod = kubectl get pods -n $NAMESPACE -l app=postgres -o jsonpath='{.items[0].metadata.name}' 2>$null
    if ($postgresPod) {
        $result = kubectl exec -n $NAMESPACE $postgresPod -- pg_isready -U postgres -h localhost -p 5432 2>$null
        if ($LASTEXITCODE -eq 0) {
            Write-ColorOutput Green "[OK] PostgreSQL is ready"
        } else {
            Write-ColorOutput Red "[ERROR] PostgreSQL not ready"
        }
    } else {
        Write-ColorOutput Red "[ERROR] PostgreSQL pod not found"
    }
} catch {
    Write-ColorOutput Red "[ERROR] Cannot check PostgreSQL connectivity"
}

# Check Redis connectivity
Write-Host "`n6. Checking Redis connectivity..."
try {
    $redisPod = kubectl get pods -n $NAMESPACE -l app=redis -o jsonpath='{.items[0].metadata.name}' 2>$null
    if ($redisPod) {
        $result = kubectl exec -n $NAMESPACE $redisPod -- redis-cli ping 2>$null
        if ($result -eq "PONG") {
            Write-ColorOutput Green "[OK] Redis is ready"
        } else {
            Write-ColorOutput Red "[ERROR] Redis not responding"
        }
    } else {
        Write-ColorOutput Red "[ERROR] Redis pod not found"
    }
} catch {
    Write-ColorOutput Red "[ERROR] Cannot check Redis connectivity"
}

# Check ingress-nginx if it exists
Write-Host "`n7. Checking ingress-nginx..."
try {
    $ingressPods = kubectl get pods -n ingress-nginx -l app.kubernetes.io/name=ingress-nginx -o jsonpath='{.items[0].metadata.name}' 2>$null
    if ($ingressPods) {
        Write-ColorOutput Green "[OK] ingress-nginx controller is running"
        
        # Get external IP
        $externalIP = kubectl get svc ingress-nginx-controller -n ingress-nginx -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>$null
        if ($externalIP) {
            Write-ColorOutput Green "[OK] External IP: $externalIP"
            Write-Host "Access URLs:"
            Write-Host "  FraudGuard: http://$externalIP/fraudguard"
            Write-Host "  Airflow:   http://$externalIP/airflow"
            Write-Host "  MLflow:    http://$externalIP/mlflow"
            Write-Host "  Inference: http://$externalIP/inference"
            Write-Host "  Flower:    http://$externalIP/flower"
        } else {
            Write-ColorOutput Yellow "[WARN] No external IP assigned yet"
        }
    } else {
        Write-ColorOutput Yellow "[WARN] ingress-nginx not found. Run .\scripts\install-ingress-nginx.ps1"
    }
} catch {
    Write-ColorOutput Yellow "[WARN] Cannot check ingress-nginx"
}

# Summary
Write-Host "`n=== Summary ==="
if ($allReady) {
    Write-ColorOutput Green "[SUCCESS] All pods are running correctly"
    Write-Host "Your MLOps fraud detection solution is ready!"
} else {
    Write-ColorOutput Red "[ISSUES] Some pods are not ready"
    Write-Host "Check the errors above and run: kubectl logs -n $NAMESPACE <pod-name>"
}

Write-Host "`nUseful commands:"
Write-Host "  Watch pods:           kubectl get pods -n $NAMESPACE -w"
Write-Host "  Check logs:           kubectl logs -n $NAMESPACE <pod-name>"
Write-Host "  Port forward:         kubectl port-forward -n $NAMESPACE svc/<service-name> <local-port>:<service-port>"
Write-Host "  Get external IP:      kubectl get svc -n ingress-nginx"
