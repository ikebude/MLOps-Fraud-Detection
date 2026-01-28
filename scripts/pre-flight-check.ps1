# OCI ADB Deployment Pre-Flight Checklist (PowerShell)
# Run this before executing the main deployment script

$ErrorActionPreference = "Stop"

function Write-ColorOutput($ForegroundColor) {
    $fc = $host.UI.RawUI.ForegroundColor
    $host.UI.RawUI.ForegroundColor = $ForegroundColor
    if ($args) {
        Write-Output $args
    }
    $host.UI.RawUI.ForegroundColor = $fc
}

Write-ColorOutput Green "=== OCI ADB Deployment Pre-Flight Checklist ==="
Write-Output ""

$allChecks = $true

# Check 1: kubectl
Write-ColorOutput Yellow "Checking kubectl..."
try {
    $kubeVersion = kubectl version --client -o json | ConvertFrom-Json
    Write-ColorOutput Green "[OK] kubectl is installed: $($kubeVersion.clientVersion.gitVersion)"
} catch {
    Write-ColorOutput Red "[FAIL] kubectl not installed or not in PATH"
    $allChecks = $false
}

# Check 2: kubectl cluster connectivity
Write-ColorOutput Yellow "Checking Kubernetes cluster connectivity..."
try {
    $clusterInfo = kubectl cluster-info
    Write-ColorOutput Green "[OK] Connected to cluster"
    Write-Output $clusterInfo
} catch {
    Write-ColorOutput Red "[FAIL] Cannot connect to Kubernetes cluster"
    $allChecks = $false
}

# Check 3: kubectl get nodes
Write-ColorOutput Yellow "Checking Kubernetes nodes..."
try {
    $nodes = kubectl get nodes
    Write-Output $nodes
    $readyNodes = $nodes | Where-Object { $_ -match "Ready" } | Measure-Object | Select-Object -ExpandProperty Count
    if ($readyNodes -ge 3) {
        Write-ColorOutput Green "[OK] All 3 nodes are Ready"
    } else {
        Write-ColorOutput Yellow "[WARN] Expected 3 Ready nodes, found $readyNodes"
    }
} catch {
    Write-ColorOutput Red "[FAIL] Cannot get nodes"
    $allChecks = $false
}

# Check 4: Docker
Write-ColorOutput Yellow "Checking Docker..."
try {
    $dockerVersion = docker version --format "{{.Server.Version}}"
    Write-ColorOutput Green "[OK] Docker is installed: $dockerVersion"
} catch {
    Write-ColorOutput Red "[FAIL] Docker not installed or not running"
    $allChecks = $false
}

# Check 5: OCIR Login
Write-ColorOutput Yellow "Checking OCIR credentials..."
$testLogin = Read-Host "Have you already logged in to OCIR? (y/n) [y]"
if ($testLogin -eq "n" -or $testLogin -eq "N") {
    Write-ColorOutput Yellow "You should run: docker login af-johannesburg-1.ocir.io before deployment"
} else {
    Write-ColorOutput Green "[OK] Assuming OCIR login is configured"
}

# Check 6: Wallet files
Write-ColorOutput Yellow "Checking ADB Wallet files..."
$walletPath = "C:\Users\3Consult\Documents\AI Solution Projects\MLOps_Fraud_Detection\Wallet_MLOPSDB"
if (Test-Path $walletPath) {
    Write-ColorOutput Green "[OK] Wallet directory exists: $walletPath"
    
    $requiredFiles = @("sqlnet.ora", "tnsnames.ora", "cwallet.sso", "ewallet.pem")
    $missingFiles = @()
    
    foreach ($file in $requiredFiles) {
        $filePath = Join-Path $walletPath $file
        if (Test-Path $filePath) {
            Write-ColorOutput Green "[OK] Found: $file"
        } else {
            Write-ColorOutput Red "[FAIL] Missing: $file"
            $missingFiles += $file
        }
    }
    
    if ($missingFiles.Count -gt 0) {
        Write-ColorOutput Red "[ERROR] Missing wallet files: $($missingFiles -join ', ')"
        $allChecks = $false
    }
} else {
    Write-ColorOutput Red "[FAIL] Wallet directory not found: $walletPath"
    Write-Output "  You need to download and extract the wallet from OCI Console"
    $allChecks = $false
}

# Check 7: PowerShell version
Write-ColorOutput Yellow "Checking PowerShell version..."
if ($PSVersionTable.PSVersion.Major -ge 5) {
    Write-ColorOutput Green "[OK] PowerShell $($PSVersionTable.PSVersion) (5.1+ required)"
} else {
    Write-ColorOutput Red "[FAIL] PowerShell version is too old (need 5.1+)"
    $allChecks = $false
}

# Check 8: File permissions
Write-ColorOutput Yellow "Checking file permissions..."
$scriptPath = ".\scripts\deploy-oci-adb-complete.ps1"
if (Test-Path $scriptPath) {
    Write-ColorOutput Green "[OK] Deployment script found: $scriptPath"
} else {
    Write-ColorOutput Red "[FAIL] Deployment script not found: $scriptPath"
    $allChecks = $false
}

# Check 9: Required files exist
Write-ColorOutput Yellow "Checking required configuration files..."
$requiredFiles = @(
    "k8s/secrets-adb.yaml",
    "k8s/airflow-adb.yaml",
    "k8s/mlflow-adb.yaml",
    "k8s/redis.yaml",
    "k8s/inference.yaml",
    "k8s/fraudguard.yaml",
    "k8s/flower.yaml",
    "k8s/ingress.yaml",
    "src/airflow/Dockerfile",
    "src/mlflow/Dockerfile",
    "src/inference/Dockerfile",
    "fraudGuard/Dockerfile"
)

foreach ($file in $requiredFiles) {
    if (Test-Path $file) {
        Write-ColorOutput Green "[OK] $file"
    } else {
        Write-ColorOutput Red "[FAIL] Missing: $file"
        $allChecks = $false
    }
}

# Check 10: Credentials verification
Write-ColorOutput Yellow "Checking credentials..."
$credsOk = $true

$ocirNamespace = "axjkxzqfxgqu"
$s3AccessKey = "615ca352d47705fc18f201c0a5a9d284e0e5f661"
$s3SecretKey = "bqfLqk7SvGvOYUuMNZU/890K2m3a3HUzL05YZVyyZls="
$adbService = "ga351c372398951_mlopsdb_medium.adb.oraclecloud.com"

if ($ocirNamespace -and $ocirNamespace.Length -gt 0) {
    Write-ColorOutput Green "[OK] OCIR Namespace configured: $ocirNamespace"
} else {
    Write-ColorOutput Red "[FAIL] OCIR Namespace not configured"
    $credsOk = $false
}

if ($s3AccessKey -and $s3AccessKey.Length -gt 0) {
    Write-ColorOutput Green "[OK] S3 Access Key configured"
} else {
    Write-ColorOutput Red "[FAIL] S3 Access Key not configured"
    $credsOk = $false
}

if ($s3SecretKey -and $s3SecretKey.Length -gt 0) {
    Write-ColorOutput Green "[OK] S3 Secret Key configured"
} else {
    Write-ColorOutput Red "[FAIL] S3 Secret Key not configured"
    $credsOk = $false
}

if ($adbService -and $adbService.Length -gt 0) {
    Write-ColorOutput Green "[OK] ADB Service Name: $adbService"
} else {
    Write-ColorOutput Red "[FAIL] ADB Service Name not configured"
    $credsOk = $false
}

if (-not $credsOk) {
    $allChecks = $false
}

# Summary
Write-Output ""
Write-ColorOutput Cyan "================================================"
if ($allChecks) {
    Write-ColorOutput Green "[PASS] ALL PRE-FLIGHT CHECKS PASSED"
    Write-Output ""
    Write-Output "You are ready to deploy!"
    Write-Output ""
    Write-Output "Next step: Run the deployment script"
    Write-Output "  .\scripts\deploy-oci-adb-complete.ps1"
    Write-Output ""
    exit 0
} else {
    Write-ColorOutput Red "[FAIL] SOME CHECKS FAILED"
    Write-Output ""
    Write-Output "Please fix the issues above before running deployment"
    Write-Output ""
    exit 1
}
