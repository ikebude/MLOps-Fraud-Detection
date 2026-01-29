# Fresh Deployment Script for MLOps Fraud Detection
# Gracefully tears down existing deployment and redeploys fresh

$ErrorActionPreference = "Stop"

function Write-ColorOutput($ForegroundColor) {
    $fc = $host.UI.RawUI.ForegroundColor
    $host.UI.RawUI.ForegroundColor = $ForegroundColor
    if ($args) {
        Write-Output $args
    }
    $host.UI.RawUI.ForegroundColor = $fc
}

Write-ColorOutput Green "=== FRESH DEPLOYMENT: MLOps Fraud Detection ==="
Write-Output "This will gracefully tear down and redeploy your entire stack"
Write-Output ""

# Configuration
$NAMESPACE = "mlops"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path | Split-Path -Parent
Set-Location $ProjectRoot

# Step 1: Backup current state (optional but recommended)
$backup = Read-Host "Backup current deployment state? (y/N)"
if ($backup -eq "y" -or $backup -eq "Y") {
    Write-ColorOutput Yellow "Creating backup of current deployment..."
    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $backupDir = "backup-$timestamp"
    New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
    
    # Backup Kubernetes resources
    kubectl get all -n $NAMESPACE -o yaml > "$backupDir/k8s-backup.yaml"
    kubectl get configmaps -n $NAMESPACE -o yaml >> "$backupDir/k8s-backup.yaml"
    kubectl get secrets -n $NAMESPACE -o yaml >> "$backupDir/k8s-backup.yaml"
    
    Write-ColorOutput Green "[OK] Backup saved to $backupDir"
}

# Step 2: Graceful teardown
Write-ColorOutput Yellow "`nStep 1: Gracefully tearing down existing deployment..."

# Stop Airflow DAGs first to prevent incomplete tasks
Write-Output "Pausing Airflow DAGs..."
try {
    kubectl exec deployment/airflow-webserver -n $NAMESPACE -- airflow dags pause -d fraud_detection_training 2>$null
    Write-ColorOutput Green "[OK] Airflow DAGs paused"
} catch {
    Write-ColorOutput Yellow "[WARN] Could not pause DAGs (may not exist yet)"
}

# Scale down critical services gracefully
Write-Output "Scaling down services..."
kubectl scale deployment airflow-worker --replicas=0 -n $NAMESPACE
kubectl scale deployment airflow-scheduler --replicas=0 -n $NAMESPACE
kubectl scale deployment inference --replicas=0 -n $NAMESPACE
kubectl scale deployment fraudguard --replicas=0 -n $NAMESPACE
kubectl scale deployment mlflow --replicas=0 -n $NAMESPACE

Write-ColorOutput Green "[OK] Services scaled down"

# Wait for graceful shutdown
Write-Output "Waiting for graceful shutdown (30 seconds)..."
Start-Sleep 30

# Step 3: Clean up old resources
Write-ColorOutput Yellow "`nStep 2: Cleaning up old resources..."

# Remove deployments (keeping secrets and configmaps)
kubectl delete deployment --all -n $NAMESPACE --ignore-not-found
kubectl delete service --all -n $NAMESPACE --ignore-not-found
kubectl delete ingress --all -n $NAMESPACE --ignore-not-found

# Clean up old pods
kubectl delete pod --all -n $NAMESPACE --ignore-not-found

Write-ColorOutput Green "[OK] Old resources cleaned up"

# Step 4: Wait for cleanup
Write-Output "Waiting for cleanup to complete..."
Start-Sleep 10

# Step 5: Fresh deployment
Write-ColorOutput Yellow "`nStep 3: Deploying fresh stack..."

# Deploy core services in order
Write-Output "Deploying core services..."
kubectl apply -f k8s/postgres.yaml
kubectl rollout status statefulset/postgres -n $NAMESPACE --timeout=300s

kubectl apply -f k8s/redis.yaml
kubectl rollout status deployment/redis -n $NAMESPACE --timeout=300s

Write-ColorOutput Green "[OK] Core services deployed"

# Deploy MLflow
Write-Output "Deploying MLflow..."
kubectl apply -f k8s/mlflow.yaml
kubectl rollout status deployment/mlflow -n $NAMESPACE --timeout=300s

# Deploy Airflow
Write-Output "Deploying Airflow..."
kubectl apply -f k8s/airflow-configmap.yaml
kubectl apply -f k8s/airflow-adb.yaml
kubectl rollout status deployment/airflow-webserver -n $NAMESPACE --timeout=600s
kubectl rollout status deployment/airflow-scheduler -n $NAMESPACE --timeout=600s
kubectl rollout status deployment/airflow-worker -n $NAMESPACE --timeout=600s

# Deploy application services
Write-Output "Deploying application services..."
kubectl apply -f k8s/inference-config.yaml
kubectl apply -f k8s/inference.yaml
kubectl rollout status deployment/inference -n $NAMESPACE --timeout=300s

kubectl apply -f k8s/fraudguard.yaml
kubectl rollout status deployment/fraudguard -n $NAMESPACE --timeout=300s

kubectl apply -f k8s/flower.yaml
kubectl rollout status deployment/flower -n $NAMESPACE --timeout=300s

Write-ColorOutput Green "[OK] Application services deployed"

# Step 6: Configure ingress
Write-ColorOutput Yellow "`nStep 4: Configuring ingress..."
kubectl apply -f k8s/ingress.yaml
Write-ColorOutput Green "[OK] Ingress configured"

# Step 7: Unpause DAG and verify deployment
Write-ColorOutput Yellow "`nStep 5: Unpausing DAG and verifying deployment..."
Start-Sleep 30

# Wait for Airflow to be fully ready
Write-Output "Waiting for Airflow to be ready..."
Start-Sleep 60

# Unpause the fraud detection DAG
Write-Output "Unpausing fraud_detection DAG..."
try {
    kubectl exec deployment/airflow-webserver -n $NAMESPACE -- airflow dags unpause -d fraud_detection_training
    Write-ColorOutput Green "[OK] DAG unpaused successfully"
} catch {
    Write-ColorOutput Yellow "[WARN] Could not unpause DAG (may need to be done manually in UI)"
}

# Check DAG status
Write-Output "Checking DAG status..."
try {
    $dagStatus = kubectl exec deployment/airflow-webserver -n $NAMESPACE -- airflow dags list -d fraud_detection_training -o json 2>$null | ConvertFrom-Json
    if ($dagStatus.is_paused -eq $false) {
        Write-ColorOutput Green "[OK] DAG is active and ready"
    } else {
        Write-ColorOutput Yellow "[WARN] DAG is still paused - please unpause in Airflow UI"
    }
} catch {
    Write-ColorOutput Yellow "[WARN] Could not verify DAG status - check in Airflow UI"
}

$pods = kubectl get pods -n $NAMESPACE -o json | ConvertFrom-Json
$runningPods = ($pods.items | Where-Object { $_.status.phase -eq "Running" }).Count
$totalPods = $pods.items.Count

Write-Output "Pods: $runningPods/$totalPods running"

# Show service URLs
$ingressIP = (kubectl get svc -n ingress-nginx -o jsonpath='{.items[0].status.loadBalancer.ingress[0].ip}')
if ($ingressIP) {
    Write-ColorOutput Green "`n=== DEPLOYMENT COMPLETE ==="
    Write-Output "External IP: $ingressIP"
    Write-Output ""
    Write-Output "Access your services:"
    Write-Output "  FraudGuard: http://fraudguard.$ingressIP.nip.io"
    Write-Output "  Airflow:    http://airflow.$ingressIP.nip.io (airflow/airflow)"
    Write-Output "  MLflow:     http://mlflow.$ingressIP.nip.io"
    Write-Output "  Inference:  http://inference.$ingressIP.nip.io"
    Write-Output "  Flower:     http://flower.$ingressIP.nip.io"
    Write-Output ""
    Write-Output "Next steps:"
    Write-Output "1. Enable the fraud_detection_training DAG in Airflow"
    Write-Output "2. Test the inference API"
    Write-Output "3. Monitor the FraudGuard dashboard"
} else {
    Write-ColorOutput Yellow "[WARN] Ingress IP not yet available. Check with: kubectl get svc -n ingress-nginx"
}

Write-ColorOutput Green "`n=== FRESH DEPLOYMENT SUCCESSFUL ==="
