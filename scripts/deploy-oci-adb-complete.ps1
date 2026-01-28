# Complete OCI OKE Deployment Script with ADB Support (PowerShell)
# Builds & pushes images to OCIR, creates K8s secrets, handles wallet, and applies manifests

$ErrorActionPreference = "Stop"

function Write-ColorOutput($ForegroundColor) {
    $fc = $host.UI.RawUI.ForegroundColor
    $host.UI.RawUI.ForegroundColor = $ForegroundColor
    if ($args) {
        Write-Output $args
    }
    $host.UI.RawUI.ForegroundColor = $fc
}

function Assert-Command([string]$CommandName) {
    if (-not (Get-Command $CommandName -ErrorAction SilentlyContinue)) {
        Write-ColorOutput Red "[ERROR] '$CommandName' not found in PATH. Please install it and retry."
        exit 1
    }
}

function ConvertTo-PlainText([System.Security.SecureString]$Secure) {
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
Assert-Command "docker"
Assert-Command "kubectl"

$ScriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptPath
Set-Location $ProjectRoot

Write-ColorOutput Green "=== OCI OKE MLOps Fraud Detection Deployment (with ADB) ==="

# OCI/OCIR config
$OCI_REGION = "af-johannesburg-1"
$OCIR_NAMESPACE = "axjkxzqfxgqu"
$OCIR_REPO_BASE = "${OCI_REGION}.ocir.io/${OCIR_NAMESPACE}"
$IMAGE_PREFIX = "fraud-detection"
$NAMESPACE = "mlops"

Write-Output "OCIR repo base: $OCIR_REPO_BASE"
Write-Output "Namespace: $NAMESPACE"
Write-Output "Region: $OCI_REGION"

# OCI ADB Config
$ADB_HOST = "adb.af-johannesburg-1.oraclecloud.com"
$ADB_PORT = "1522"
$ADB_SERVICE = "ga351c372398951_mlopsdb_medium.adb.oraclecloud.com"
$ADB_WALLET_LOCATION = "/opt/oracle/wallet"

Write-Output "ADB Service: $ADB_SERVICE"

# Optional: configure kubeconfig from OCI
$configureKube = Read-Host "Configure kubeconfig via OCI CLI now? (requires oci CLI + cluster OCID) [y/N]"
if ($configureKube -eq "y" -or $configureKube -eq "Y") {
    Assert-Command "oci"
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

# Credentials
Write-ColorOutput Yellow "`nEntering credentials..."
$ocirUsername = Read-Host "OCIR Username (your OCI username/email)"
$ocirAuthTokenSecure = Read-Host "OCIR Auth Token (input hidden)" -AsSecureString
$ocirAuthToken = ConvertTo-PlainText $ocirAuthTokenSecure

# OCI Object Storage S3 Credentials
$osAccessKey = Read-Host "OCI Object Storage S3 Access Key ID"
$osSecretKeySecure = Read-Host "OCI Object Storage S3 Secret Access Key (input hidden)" -AsSecureString
$osSecretKey = ConvertTo-PlainText $osSecretKeySecure

# ADB Credentials
$adbMlflowPasswordSecure = Read-Host "ADB mlflow user password (input hidden)" -AsSecureString
$adbMlflowPassword = ConvertTo-PlainText $adbMlflowPasswordSecure
$adbMlflowPasswordEnc = UrlEncode $adbMlflowPassword

$adbAirflowPasswordSecure = Read-Host "ADB airflow user password (input hidden)" -AsSecureString
$adbAirflowPassword = ConvertTo-PlainText $adbAirflowPasswordSecure
$adbAirflowPasswordEnc = UrlEncode $adbAirflowPassword

# ADB Wallet Path
$walletPath = Read-Host "Path to extracted ADB Wallet directory (e.g., C:\Users\3Consult\Documents\AI Solution Projects\MLOps_Fraud_Detection\Wallet_MLOPSDB)"
if (-not (Test-Path $walletPath)) {
    Write-ColorOutput Red "[ERROR] Wallet path does not exist: $walletPath"
    exit 1
}

# Verify wallet files exist
$requiredWalletFiles = @("sqlnet.ora", "tnsnames.ora", "cwallet.sso", "ewallet.pem")
foreach ($file in $requiredWalletFiles) {
    if (-not (Test-Path (Join-Path $walletPath $file))) {
        Write-ColorOutput Red "[ERROR] Missing wallet file: $file in $walletPath"
        exit 1
    }
}
Write-ColorOutput Green "[OK] Wallet files verified"

# Login to OCIR
Write-ColorOutput Yellow "`nLogging in to OCIR..."
$ocirDockerUser = "${OCIR_NAMESPACE}/${ocirUsername}"
docker login "${OCI_REGION}.ocir.io" -u $ocirDockerUser -p $ocirAuthToken
if ($LASTEXITCODE -ne 0) {
    Write-ColorOutput Red "[ERROR] Docker login to OCIR failed"
    exit 1
}
Write-ColorOutput Green "[OK] Docker login successful"

# Build & push images
Write-ColorOutput Yellow "`nBuilding and pushing images to OCIR..."

Write-Output "Building Airflow..."
docker build -f src/airflow/Dockerfile -t "${OCIR_REPO_BASE}/${IMAGE_PREFIX}/airflow:latest" .
if ($LASTEXITCODE -ne 0) { throw "Failed to build Airflow image" }
docker push "${OCIR_REPO_BASE}/${IMAGE_PREFIX}/airflow:latest"
if ($LASTEXITCODE -ne 0) { throw "Failed to push Airflow image" }
Write-ColorOutput Green "[OK] Airflow image pushed"

Write-Output "Building MLflow..."
docker build -f src/mlflow/Dockerfile -t "${OCIR_REPO_BASE}/${IMAGE_PREFIX}/mlflow:latest" .
if ($LASTEXITCODE -ne 0) { throw "Failed to build MLflow image" }
docker push "${OCIR_REPO_BASE}/${IMAGE_PREFIX}/mlflow:latest"
if ($LASTEXITCODE -ne 0) { throw "Failed to push MLflow image" }
Write-ColorOutput Green "[OK] MLflow image pushed"

Write-Output "Building Inference..."
docker build -f src/inference/Dockerfile -t "${OCIR_REPO_BASE}/${IMAGE_PREFIX}/inference:latest" .
if ($LASTEXITCODE -ne 0) { throw "Failed to build Inference image" }
docker push "${OCIR_REPO_BASE}/${IMAGE_PREFIX}/inference:latest"
if ($LASTEXITCODE -ne 0) { throw "Failed to push Inference image" }
Write-ColorOutput Green "[OK] Inference image pushed"

$fraudguardDir = Join-Path $ProjectRoot "fraudGuard"
$deployFraudGuard = $false
if (Test-Path $fraudguardDir) {
    Write-Output "Building FraudGuard..."
    docker build -f fraudGuard/Dockerfile -t "${OCIR_REPO_BASE}/${IMAGE_PREFIX}/fraudguard:latest" .
    if ($LASTEXITCODE -ne 0) { throw "Failed to build FraudGuard image" }
    docker push "${OCIR_REPO_BASE}/${IMAGE_PREFIX}/fraudguard:latest"
    if ($LASTEXITCODE -ne 0) { throw "Failed to push FraudGuard image" }
    $deployFraudGuard = $true
    Write-ColorOutput Green "[OK] FraudGuard image pushed"
} else {
    Write-ColorOutput Yellow "[WARN] fraudGuard/ directory not found"
}

# Apply namespace + configmaps
Write-ColorOutput Yellow "`nApplying base configuration..."
kubectl apply -f k8s/secrets-adb.yaml
if ($LASTEXITCODE -ne 0) { throw "Failed to apply k8s/secrets-adb.yaml" }

# Create namespace
kubectl create namespace $NAMESPACE --dry-run=client -o yaml | kubectl apply -f -

# Create OCIR secret
Write-ColorOutput Yellow "Creating Kubernetes secrets..."
kubectl delete secret ocir-secret -n $NAMESPACE --ignore-not-found
kubectl create secret docker-registry ocir-secret `
  --docker-server="${OCI_REGION}.ocir.io" `
  --docker-username="$ocirDockerUser" `
  --docker-password="$ocirAuthToken" `
  --namespace $NAMESPACE
Write-ColorOutput Green "[OK] OCIR secret created"

# Create ADB wallet secret from files
Write-ColorOutput Yellow "Creating ADB wallet secret from files..."
kubectl delete secret adb-wallet -n $NAMESPACE --ignore-not-found

# Read and encode wallet files
$sqlnetOra = [Convert]::ToBase64String([IO.File]::ReadAllBytes((Join-Path $walletPath "sqlnet.ora")))
$tnsnamesOra = [Convert]::ToBase64String([IO.File]::ReadAllBytes((Join-Path $walletPath "tnsnames.ora")))
$cwalletSso = [Convert]::ToBase64String([IO.File]::ReadAllBytes((Join-Path $walletPath "cwallet.sso")))
$ewalletPem = [Convert]::ToBase64String([IO.File]::ReadAllBytes((Join-Path $walletPath "ewallet.pem")))

# Create wallet secret YAML
$walletSecretYaml = @"
apiVersion: v1
kind: Secret
metadata:
  name: adb-wallet
  namespace: mlops
type: Opaque
data:
  sqlnet.ora: $sqlnetOra
  tnsnames.ora: $tnsnamesOra
  cwallet.sso: $cwalletSso
  ewallet.pem: $ewalletPem
"@

# Also add keystore and truststore if they exist
if (Test-Path (Join-Path $walletPath "keystore.jks")) {
    $keystoreJks = [Convert]::ToBase64String([IO.File]::ReadAllBytes((Join-Path $walletPath "keystore.jks")))
    $walletSecretYaml += "`n  keystore.jks: $keystoreJks"
}

if (Test-Path (Join-Path $walletPath "truststore.jks")) {
    $truststoreJks = [Convert]::ToBase64String([IO.File]::ReadAllBytes((Join-Path $walletPath "truststore.jks")))
    $walletSecretYaml += "`n  truststore.jks: $truststoreJks"
}

# Apply wallet secret
$walletSecretYaml | kubectl apply -f -
if ($LASTEXITCODE -ne 0) { throw "Failed to create ADB wallet secret" }
Write-ColorOutput Green "[OK] ADB wallet secret created"

# Create ADB credentials secret
Write-ColorOutput Yellow "Creating ADB credentials secret..."
kubectl delete secret adb-credentials -n $NAMESPACE --ignore-not-found

# Build connection strings for OCI ADB
# Format: oracle://username:password@host:port/?service_name=service&thin_mode=true
$adbMlflowConn = "oracle://mlflow:${adbMlflowPasswordEnc}@${ADB_HOST}:${ADB_PORT}/?service_name=${ADB_SERVICE}&thin_mode=true&wallet_location=${ADB_WALLET_LOCATION}"
$adbAirflowConn = "oracle://airflow:${adbAirflowPasswordEnc}@${ADB_HOST}:${ADB_PORT}/?service_name=${ADB_SERVICE}&thin_mode=true&wallet_location=${ADB_WALLET_LOCATION}"
$adbAirflowResultBackend = "db+oracle://airflow:${adbAirflowPasswordEnc}@${ADB_HOST}:${ADB_PORT}/?service_name=${ADB_SERVICE}&thin_mode=true&wallet_location=${ADB_WALLET_LOCATION}"
$adbMlflowBackendStoreUri = "oracle://mlflow:${adbMlflowPasswordEnc}@${ADB_HOST}:${ADB_PORT}/?service_name=${ADB_SERVICE}&thin_mode=true&wallet_location=${ADB_WALLET_LOCATION}"

kubectl create secret generic adb-credentials -n $NAMESPACE `
  --from-literal=mlflow-conn="$adbMlflowConn" `
  --from-literal=airflow-conn="$adbAirflowConn" `
  --from-literal=airflow-result-backend="$adbAirflowResultBackend" `
  --from-literal=mlflow-backend-store-uri="$adbMlflowBackendStoreUri" `
  --from-literal=mlflow-user="mlflow" `
  --from-literal=mlflow-password="$adbMlflowPassword" `
  --from-literal=airflow-user="airflow" `
  --from-literal=airflow-password="$adbAirflowPassword"
Write-ColorOutput Green "[OK] ADB credentials secret created"

# Create Object Storage credentials secret
Write-ColorOutput Yellow "Creating Object Storage credentials secret..."
kubectl delete secret object-storage-credentials -n $NAMESPACE --ignore-not-found
kubectl create secret generic object-storage-credentials -n $NAMESPACE `
  --from-literal=aws_access_key_id="$osAccessKey" `
  --from-literal=aws_secret_access_key="$osSecretKey"
Write-ColorOutput Green "[OK] Object Storage credentials secret created"

# Deploy core services
Write-ColorOutput Yellow "`nDeploying core services..."
kubectl apply -f k8s/redis.yaml
kubectl rollout status deployment/redis -n $NAMESPACE --timeout=300s
Write-ColorOutput Green "[OK] Redis deployed"

# Deploy MLflow
Write-ColorOutput Yellow "Deploying MLflow..."
kubectl apply -f k8s/mlflow-adb.yaml
kubectl rollout status deployment/mlflow -n $NAMESPACE --timeout=300s
Write-ColorOutput Green "[OK] MLflow deployed"

# Deploy Airflow
Write-ColorOutput Yellow "Deploying Airflow..."
kubectl apply -f k8s/airflow-configmap.yaml
kubectl apply -f k8s/airflow-adb.yaml
kubectl rollout status deployment/airflow-webserver -n $NAMESPACE --timeout=600s
kubectl rollout status deployment/airflow-scheduler -n $NAMESPACE --timeout=600s
kubectl rollout status deployment/airflow-worker -n $NAMESPACE --timeout=600s
Write-ColorOutput Green "[OK] Airflow deployed"

# Deploy Inference + FraudGuard + Flower
Write-ColorOutput Yellow "Deploying Inference, FraudGuard, and Flower..."
kubectl apply -f k8s/inference-config.yaml
kubectl apply -f k8s/inference.yaml
if ($deployFraudGuard) {
    kubectl apply -f k8s/fraudguard.yaml
} else {
    Write-ColorOutput Yellow "[WARN] Skipping FraudGuard deployment"
}
kubectl apply -f k8s/flower.yaml
Write-ColorOutput Green "[OK] Inference, FraudGuard, and Flower deployed"

# Ingress
$installIngress = Read-Host "`nInstall ingress-nginx via Helm now? [y/N]"
if ($installIngress -eq "y" -or $installIngress -eq "Y") {
    Assert-Command "helm"
    Write-ColorOutput Yellow "Installing ingress-nginx..."
    helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
    helm repo update
    helm upgrade --install ingress-nginx ingress-nginx/ingress-nginx --namespace ingress-nginx --create-namespace --set controller.service.type=LoadBalancer --set controller.replicaCount=2
    if ($LASTEXITCODE -ne 0) { throw "Failed to install ingress-nginx" }
    Write-ColorOutput Green "[OK] ingress-nginx installed"
}

Write-ColorOutput Yellow "Applying Ingress routes..."
kubectl apply -f k8s/ingress.yaml
Write-ColorOutput Green "[OK] Ingress routes applied"

Write-ColorOutput Green "`n=== DEPLOYMENT COMPLETE ==="
Write-Output ""
Write-Output "Next steps:"
Write-Output "1. Wait for all pods to be ready: kubectl get pods -n mlops"
Write-Output "2. Get ingress external IP: kubectl get svc -n ingress-nginx"
Write-Output "3. Access services via: http://<ingress-ip>/fraudguard, /airflow, /mlflow, /inference, /flower"
Write-Output ""
Write-Output "Verify ADB connectivity: kubectl logs -n mlops deployment/airflow-webserver -f"
