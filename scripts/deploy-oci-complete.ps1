# Complete OCI OKE Deployment Script (PowerShell)
# Builds & pushes images to OCIR, creates K8s secrets at deploy-time, and applies manifests.

$ErrorActionPreference = "Stop"

function Write-ColorOutput($ForegroundColor) {
    $fc = $host.UI.RawUI.ForegroundColor
    $host.UI.RawUI.ForegroundColor = $ForegroundColor
    if ($args) {
        Write-Output $args
    }
    $host.UI.RawUI.ForegroundColor = $fc
}

function Require-Command([string]$CommandName) {
    if (-not (Get-Command $CommandName -ErrorAction SilentlyContinue)) {
        Write-ColorOutput Red "[ERROR] '$CommandName' not found in PATH. Please install it and retry."
        exit 1
    }
}

function To-PlainText([System.Security.SecureString]$Secure) {
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Secure)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) | Out-Null
    }
}

function UrlEncode([string]$Value) {
    return [uri]::EscapeDataString($Value)
}

# Tools
Require-Command "docker"
Require-Command "kubectl"

$ScriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptPath
Set-Location $ProjectRoot

Write-ColorOutput Green "=== OCI OKE MLOps Fraud Detection Deployment ==="

# OCI/OCIR config
$OCI_REGION = if ($env:OCI_REGION) { $env:OCI_REGION } else { "af-johannesburg-1" }
$OCIR_NAMESPACE = if ($env:OCIR_NAMESPACE) { $env:OCIR_NAMESPACE } else { "axjkxzqfxgqu" }
$OCIR_REPO_BASE = "${OCI_REGION}.ocir.io/${OCIR_NAMESPACE}"
$IMAGE_PREFIX = "fraud-detection"
$NAMESPACE = "mlops"

Write-Output "OCIR repo base: $OCIR_REPO_BASE"
Write-Output "Namespace: $NAMESPACE"

# Optional: configure kubeconfig from OCI
$configureKube = Read-Host "Configure kubeconfig via OCI CLI now? (requires oci CLI + cluster OCID) [y/N]"
if ($configureKube -eq "y" -or $configureKube -eq "Y") {
    Require-Command "oci"
    $clusterOcid = Read-Host "OKE Cluster OCID"
    $kubeFile = Join-Path $env:USERPROFILE ".kube\\config"
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $kubeFile) | Out-Null

    Write-ColorOutput Yellow "Configuring kubeconfig..."
    oci ce cluster create-kubeconfig --cluster-id $clusterOcid --file $kubeFile --region $OCI_REGION --token-version 2.0.0 --kube-endpoint PUBLIC_ENDPOINT
    if ($LASTEXITCODE -ne 0) {
        Write-ColorOutput Red "[ERROR] Failed to create kubeconfig via OCI CLI"
        exit 1
    }
}

# Credentials (never committed)
$ocirUsername = Read-Host "OCIR Username (your OCI username/email)"
$ocirAuthTokenSecure = Read-Host "OCIR Auth Token (input hidden)" -AsSecureString
$ocirAuthToken = To-PlainText $ocirAuthTokenSecure

$pgPasswordSecure = Read-Host "Postgres password for in-cluster postgres user (input hidden)" -AsSecureString
$pgPassword = To-PlainText $pgPasswordSecure
$pgPasswordEnc = UrlEncode $pgPassword

$osAccessKey = Read-Host "OCI Object Storage S3 Access Key ID"
$osSecretKeySecure = Read-Host "OCI Object Storage S3 Secret Access Key (input hidden)" -AsSecureString
$osSecretKey = To-PlainText $osSecretKeySecure

# Login to OCIR
Write-ColorOutput Yellow "Logging in to OCIR..."
$ocirDockerUser = "${OCIR_NAMESPACE}/${ocirUsername}"
docker login "${OCI_REGION}.ocir.io" -u $ocirDockerUser -p $ocirAuthToken
if ($LASTEXITCODE -ne 0) {
    Write-ColorOutput Red "[ERROR] Docker login to OCIR failed"
    exit 1
}

# Build & push images
Write-ColorOutput Yellow "Building and pushing images to OCIR..."

Write-Output "Building Airflow..."
docker build -f src/airflow/Dockerfile -t "${OCIR_REPO_BASE}/${IMAGE_PREFIX}/airflow:latest" .
if ($LASTEXITCODE -ne 0) { throw "Failed to build Airflow image" }
docker push "${OCIR_REPO_BASE}/${IMAGE_PREFIX}/airflow:latest"
if ($LASTEXITCODE -ne 0) { throw "Failed to push Airflow image" }

Write-Output "Building MLflow..."
docker build -f src/mlflow/Dockerfile -t "${OCIR_REPO_BASE}/${IMAGE_PREFIX}/mlflow:latest" .
if ($LASTEXITCODE -ne 0) { throw "Failed to build MLflow image" }
docker push "${OCIR_REPO_BASE}/${IMAGE_PREFIX}/mlflow:latest"
if ($LASTEXITCODE -ne 0) { throw "Failed to push MLflow image" }

Write-Output "Building Inference..."
docker build -f src/inference/Dockerfile -t "${OCIR_REPO_BASE}/${IMAGE_PREFIX}/inference:latest" .
if ($LASTEXITCODE -ne 0) { throw "Failed to build Inference image" }
docker push "${OCIR_REPO_BASE}/${IMAGE_PREFIX}/inference:latest"
if ($LASTEXITCODE -ne 0) { throw "Failed to push Inference image" }

$fraudguardDir = Join-Path $ProjectRoot "fraudguard"
$deployFraudGuard = $false
if (Test-Path $fraudguardDir) {
    Write-Output "Building FraudGuard..."
    docker build -f fraudguard/Dockerfile -t "${OCIR_REPO_BASE}/${IMAGE_PREFIX}/fraudguard:latest" fraudguard
    if ($LASTEXITCODE -ne 0) { throw "Failed to build FraudGuard image" }
    docker push "${OCIR_REPO_BASE}/${IMAGE_PREFIX}/fraudguard:latest"
    if ($LASTEXITCODE -ne 0) { throw "Failed to push FraudGuard image" }
    $deployFraudGuard = $true
} else {
    Write-ColorOutput Yellow "[WARN] fraudguard/ directory not found in this repo. Skipping FraudGuard build/push."
}

# Apply namespace + configmaps
Write-ColorOutput Yellow "Applying base config (namespace + configmaps)..."
kubectl apply -f k8s/secrets.yaml
if ($LASTEXITCODE -ne 0) { throw "Failed to apply k8s/secrets.yaml" }

# Create secrets
Write-ColorOutput Yellow "Creating/Updating Kubernetes secrets..."

kubectl create namespace $NAMESPACE --dry-run=client -o yaml | kubectl apply -f -

kubectl delete secret ocir-secret -n $NAMESPACE --ignore-not-found
kubectl create secret docker-registry ocir-secret `
  --docker-server="${OCI_REGION}.ocir.io" `
  --docker-username="$ocirDockerUser" `
  --docker-password="$ocirAuthToken" `
  --namespace $NAMESPACE

kubectl delete secret postgres-credentials -n $NAMESPACE --ignore-not-found
$airflowConn = "postgresql+psycopg2://postgres:${pgPasswordEnc}@postgres:5432/airflow"
$airflowResultBackend = "db+postgresql://postgres:${pgPasswordEnc}@postgres:5432/airflow"
$mlflowBackendStoreUri = "postgresql://postgres:${pgPasswordEnc}@postgres:5432/mlflow"

kubectl create secret generic postgres-credentials -n $NAMESPACE `
  --from-literal=username=postgres `
  --from-literal=password="$pgPassword" `
  --from-literal=airflow-conn="$airflowConn" `
  --from-literal=airflow-result-backend="$airflowResultBackend" `
  --from-literal=mlflow-backend-store-uri="$mlflowBackendStoreUri"

kubectl delete secret object-storage-credentials -n $NAMESPACE --ignore-not-found
kubectl create secret generic object-storage-credentials -n $NAMESPACE `
  --from-literal=aws_access_key_id="$osAccessKey" `
  --from-literal=aws_secret_access_key="$osSecretKey"

# Deploy core services
Write-ColorOutput Yellow "Deploying core services (redis, postgres)..."
kubectl apply -f k8s/redis.yaml
kubectl apply -f k8s/postgres.yaml
kubectl rollout status statefulset/postgres -n $NAMESPACE --timeout=300s

Write-ColorOutput Yellow "Deploying MLflow..."
kubectl apply -f k8s/mlflow.yaml
kubectl rollout status deployment/mlflow -n $NAMESPACE --timeout=300s

Write-ColorOutput Yellow "Deploying Airflow..."
kubectl apply -f k8s/airflow-configmap.yaml
kubectl apply -f k8s/airflow.yaml
kubectl apply -f k8s/airflow-dag-processor.yaml
kubectl rollout status deployment/airflow-webserver -n $NAMESPACE --timeout=600s
kubectl rollout status deployment/airflow-scheduler -n $NAMESPACE --timeout=600s
kubectl rollout status deployment/airflow-worker -n $NAMESPACE --timeout=600s

Write-ColorOutput Yellow "Deploying Inference + FraudGuard + Flower..."
kubectl apply -f k8s/inference-config.yaml
kubectl apply -f k8s/inference.yaml
if ($deployFraudGuard) {
    kubectl apply -f k8s/fraudguard.yaml
} else {
    Write-ColorOutput Yellow "[WARN] Skipping k8s/fraudguard.yaml because FraudGuard image was not built/pushed."
}
kubectl apply -f k8s/flower.yaml

# Ingress
$installIngress = Read-Host "Install ingress-nginx via Helm now? [y/N]"
if ($installIngress -eq "y" -or $installIngress -eq "Y") {
    Require-Command "helm"
    Write-ColorOutput Yellow "Installing ingress-nginx..."
    helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
    helm repo update
    helm upgrade --install ingress-nginx ingress-nginx/ingress-nginx --namespace ingress-nginx --create-namespace --set controller.service.type=LoadBalancer --set controller.replicaCount=2
    if ($LASTEXITCODE -ne 0) { throw "Failed to install ingress-nginx" }
}

Write-ColorOutput Yellow "Applying Ingress routes..."
kubectl apply -f k8s/ingress.yaml

Write-ColorOutput Green "[OK] Deployment applied."
Write-Output "Next: get ingress external IP via: kubectl get svc -n ingress-nginx"
