# Diagnostic Script for Azure AKS Deployment Issues
# This script checks all components and identifies problems

param(
    [string]$Namespace = "mlops"
)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Azure AKS Deployment Diagnostics" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Colors
$GREEN = "Green"
$RED = "Red"
$YELLOW = "Yellow"
$CYAN = "Cyan"

# Check kubectl connectivity
Write-Host "[1] Checking kubectl connectivity..." -ForegroundColor $CYAN
try {
    $clusterInfo = kubectl cluster-info 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  [OK] kubectl is connected to cluster" -ForegroundColor $GREEN
    } else {
        Write-Host "  [ERROR] kubectl is not connected. Run: az aks get-credentials --resource-group mlops_fraud_analytics --name mlops-aks-cluster" -ForegroundColor $RED
        exit 1
    }
} catch {
    Write-Host "  [ERROR] kubectl not found or not configured" -ForegroundColor $RED
    exit 1
}
Write-Host ""

# Check namespace
Write-Host "[2] Checking namespace..." -ForegroundColor $CYAN
$ns = kubectl get namespace $Namespace 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "  [OK] Namespace '$Namespace' exists" -ForegroundColor $GREEN
} else {
    Write-Host "  [ERROR] Namespace '$Namespace' not found" -ForegroundColor $RED
    Write-Host "    Run: kubectl apply -f k8s/secrets.yaml" -ForegroundColor $YELLOW
}
Write-Host ""

# Check ConfigMaps
Write-Host "[3] Checking ConfigMaps..." -ForegroundColor $CYAN
$configMaps = @("airflow-config", "airflow-dags", "inference-config", "mlflow-config")
foreach ($cm in $configMaps) {
    $result = kubectl get configmap $cm -n $Namespace 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  [OK] ConfigMap '$cm' exists" -ForegroundColor $GREEN
    } else {
        Write-Host "  [ERROR] ConfigMap '$cm' missing" -ForegroundColor $RED
    }
}
Write-Host ""

# Check Secrets
Write-Host "[4] Checking Secrets..." -ForegroundColor $CYAN
$secrets = @("acr-secret", "storage-credentials", "postgres-credentials")
foreach ($secret in $secrets) {
    $result = kubectl get secret $secret -n $Namespace 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  [OK] Secret '$secret' exists" -ForegroundColor $GREEN
    } else {
        Write-Host "  [ERROR] Secret '$secret' missing" -ForegroundColor $RED
        if ($secret -eq "acr-secret") {
            $acrCmd = "    Create with: kubectl create secret docker-registry acr-secret --docker-server=mlopsacr12345.azurecr.io --docker-username=mlopsacr12345 --docker-password=<password> -n " + $Namespace
            Write-Host $acrCmd -ForegroundColor $YELLOW
        }
    }
}
Write-Host ""

# Check Pods
Write-Host "[5] Checking Pod Status..." -ForegroundColor $CYAN
$pods = kubectl get pods -n $Namespace -o json | ConvertFrom-Json
if ($pods.items.Count -eq 0) {
    Write-Host "  [ERROR] No pods found in namespace '$Namespace'" -ForegroundColor $RED
    Write-Host "    Deploy services: kubectl apply -f k8s/" -ForegroundColor $YELLOW
} else {
    Write-Host "  Found $($pods.items.Count) pod(s):" -ForegroundColor $CYAN
    foreach ($pod in $pods.items) {
        $status = $pod.status.phase
        $ready = ""
        if ($pod.status.containerStatuses) {
            $readyCount = ($pod.status.containerStatuses | Where-Object { $_.ready -eq $true }).Count
            $totalCount = $pod.status.containerStatuses.Count
            $ready = " ($readyCount/$totalCount ready)"
        }
        
        $color = if ($status -eq "Running") { $GREEN } elseif ($status -eq "Pending") { $YELLOW } else { $RED }
        Write-Host "    $($pod.metadata.name): $status$ready" -ForegroundColor $color
        
        # Check for errors
        if ($pod.status.containerStatuses) {
            foreach ($container in $pod.status.containerStatuses) {
                if ($container.state.waiting) {
                    Write-Host "      [WARNING] Waiting: $($container.state.waiting.reason) - $($container.state.waiting.message)" -ForegroundColor $YELLOW
                }
                if ($container.state.terminated) {
                    Write-Host "      [ERROR] Terminated: $($container.state.terminated.reason) - $($container.state.terminated.message)" -ForegroundColor $RED
                }
                if ($container.restartCount -gt 3) {
                    Write-Host "      [WARNING] High restart count: $($container.restartCount)" -ForegroundColor $YELLOW
                }
            }
        }
    }
}
Write-Host ""

# Check Services
Write-Host "[6] Checking Services and LoadBalancer IPs..." -ForegroundColor $CYAN
$services = kubectl get svc -n $Namespace -o json | ConvertFrom-Json
if ($services.items.Count -eq 0) {
    Write-Host "  [ERROR] No services found" -ForegroundColor $RED
} else {
    Write-Host "  Service Status:" -ForegroundColor $CYAN
    foreach ($svc in $services.items) {
        $name = $svc.metadata.name
        $type = $svc.spec.type
        $externalIP = "None"
        
        if ($svc.status.loadBalancer.ingress) {
            $externalIP = $svc.status.loadBalancer.ingress[0].ip
        } elseif ($svc.spec.type -eq "LoadBalancer") {
            $externalIP = "<pending>"
        } elseif ($svc.spec.clusterIP) {
            $externalIP = $svc.spec.clusterIP
        }
        
        $port = $svc.spec.ports[0].port
        $color = if ($externalIP -and $externalIP -ne "<pending>" -and $externalIP -ne "None") { $GREEN } elseif ($externalIP -eq "<pending>") { $YELLOW } else { $CYAN }
        
        Write-Host "    $name ($type):" -ForegroundColor $CYAN
        Write-Host "      IP: $externalIP" -ForegroundColor $color
        Write-Host "      Port: $port" -ForegroundColor $CYAN
        
        if ($externalIP -eq "<pending>" -and $type -eq "LoadBalancer") {
            Write-Host "      [WARNING] LoadBalancer IP pending - this may take 5-10 minutes" -ForegroundColor $YELLOW
            Write-Host "      [WARNING] Check Azure quota for public IP addresses" -ForegroundColor $YELLOW
            Write-Host "      [TIP] Use port-forwarding for immediate access:" -ForegroundColor $CYAN
            $pfCmd = "         kubectl port-forward -n $Namespace svc/$name $port`:$port"
            Write-Host $pfCmd -ForegroundColor $YELLOW
        }
    }
}
Write-Host ""

# Check specific service issues
Write-Host "[7] Checking Airflow Configuration..." -ForegroundColor $CYAN
$jsonPath = '{.items[0].metadata.name}'
$airflowPod = kubectl get pods -n $Namespace -l app=airflow-webserver -o jsonpath=$jsonPath 2>&1
if ($airflowPod -and -not ($airflowPod -match "error")) {
    Write-Host "  [OK] Airflow webserver pod found: $airflowPod" -ForegroundColor $GREEN
    
    # Check if pod is ready
    $statusPath = '{.status.phase}'
    $podStatus = kubectl get pod $airflowPod -n $Namespace -o jsonpath=$statusPath 2>&1
    if ($podStatus -eq "Running") {
        Write-Host "  [OK] Pod is running" -ForegroundColor $GREEN
        
        # Check logs for errors
        Write-Host "  Checking recent logs for errors..." -ForegroundColor $CYAN
        $logs = kubectl logs $airflowPod -n $Namespace --tail=20 2>&1
        if ($logs -match "error|Error|ERROR|failed|Failed|FAILED") {
            Write-Host "  [WARNING] Found errors in logs:" -ForegroundColor $YELLOW
            $logs | Select-String -Pattern "error|Error|ERROR|failed|Failed|FAILED" | ForEach-Object {
                Write-Host "    $_" -ForegroundColor $YELLOW
            }
        } else {
            Write-Host "  [OK] No obvious errors in recent logs" -ForegroundColor $GREEN
        }
    } else {
        Write-Host "  [ERROR] Pod status: $podStatus" -ForegroundColor $RED
    }
} else {
    Write-Host "  [ERROR] Airflow webserver pod not found" -ForegroundColor $RED
}
Write-Host ""

Write-Host "[8] Checking MLflow Configuration..." -ForegroundColor $CYAN
$jsonPath = '{.items[0].metadata.name}'
$mlflowPod = kubectl get pods -n $Namespace -l app=mlflow -o jsonpath=$jsonPath 2>&1
if ($mlflowPod -and -not ($mlflowPod -match "error")) {
    Write-Host "  [OK] MLflow pod found: $mlflowPod" -ForegroundColor $GREEN
    
    $statusPath = '{.status.phase}'
    $podStatus = kubectl get pod $mlflowPod -n $Namespace -o jsonpath=$statusPath 2>&1
    if ($podStatus -eq "Running") {
        Write-Host "  [OK] Pod is running" -ForegroundColor $GREEN
        
        # Check logs
        Write-Host "  Checking recent logs..." -ForegroundColor $CYAN
        $logs = kubectl logs $mlflowPod -n $Namespace --tail=20 2>&1
        if ($logs -match "error|Error|ERROR|failed|Failed|FAILED") {
            Write-Host "  [WARNING] Found errors in logs:" -ForegroundColor $YELLOW
            $logs | Select-String -Pattern "error|Error|ERROR|failed|Failed|FAILED" | ForEach-Object {
                Write-Host "    $_" -ForegroundColor $YELLOW
            }
        }
    } else {
        Write-Host "  [ERROR] Pod status: $podStatus" -ForegroundColor $RED
    }
} else {
    Write-Host "  [ERROR] MLflow pod not found" -ForegroundColor $RED
}
Write-Host ""

# Summary and recommendations
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "SUMMARY AND RECOMMENDATIONS" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "Quick Access Solutions:" -ForegroundColor $CYAN
Write-Host "1. Use port-forwarding for immediate access:" -ForegroundColor $YELLOW
$pf1 = "   kubectl port-forward -n $Namespace svc/airflow-webserver 8080:8080"
$pf2 = "   kubectl port-forward -n $Namespace svc/mlflow 5000:5000"
$pf3 = "   kubectl port-forward -n $Namespace svc/fraudguard 5001:5000"
$pf4 = "   kubectl port-forward -n $Namespace svc/inference 8000:8000"
$pf5 = "   kubectl port-forward -n $Namespace svc/flower 5555:5555"
Write-Host $pf1 -ForegroundColor $GREEN
Write-Host $pf2 -ForegroundColor $GREEN
Write-Host $pf3 -ForegroundColor $GREEN
Write-Host $pf4 -ForegroundColor $GREEN
Write-Host $pf5 -ForegroundColor $GREEN
Write-Host ""

Write-Host "2. Check Azure Public IP Quota:" -ForegroundColor $YELLOW
Write-Host "   - Go to Azure Portal, then Subscriptions, then Your Subscription, then Usage + quotas" -ForegroundColor $CYAN
Write-Host "   - Search for Public IP addresses" -ForegroundColor $CYAN
Write-Host "   - Request quota increase if needed" -ForegroundColor $CYAN
Write-Host ""

Write-Host "3. Alternative: Use Ingress Controller (single IP for all services)" -ForegroundColor $YELLOW
Write-Host "   - More cost-effective" -ForegroundColor $CYAN
Write-Host "   - Single public IP instead of multiple LoadBalancers" -ForegroundColor $CYAN
Write-Host ""

Write-Host "4. Check Pod Logs for Detailed Errors:" -ForegroundColor $YELLOW
$logCmd1 = "   kubectl logs -f deployment/airflow-webserver -n " + $Namespace
$logCmd2 = "   kubectl logs -f deployment/mlflow -n " + $Namespace
Write-Host $logCmd1 -ForegroundColor $GREEN
Write-Host $logCmd2 -ForegroundColor $GREEN
Write-Host ""

$restartCmd1 = "   kubectl rollout restart deployment/airflow-webserver -n " + $Namespace
$restartCmd2 = "   kubectl rollout restart deployment/mlflow -n " + $Namespace
Write-Host "5. Restart Services if Needed:" -ForegroundColor $YELLOW
Write-Host $restartCmd1 -ForegroundColor $GREEN
Write-Host $restartCmd2 -ForegroundColor $GREEN
Write-Host ""
