# Setup script for local development (PowerShell)
# This script prepares the environment for local development on Windows

$ErrorActionPreference = "Stop"

# Colors for output
function Write-ColorOutput($ForegroundColor) {
    $fc = $host.UI.RawUI.ForegroundColor
    $host.UI.RawUI.ForegroundColor = $ForegroundColor
    if ($args) {
        Write-Output $args
    }
    $host.UI.RawUI.ForegroundColor = $fc
}

Write-ColorOutput Green "Setting up local development environment..."

# Check if .env file exists
if (-not (Test-Path "src\.env")) {
    Write-ColorOutput Yellow "Creating .env file..."
    if (Test-Path "src\.env.example") {
        Copy-Item "src\.env.example" "src\.env"
        Write-ColorOutput Green ".env file created. Please update it with your values."
    } else {
        Write-ColorOutput Yellow "src\.env.example not found. Creating basic .env file..."
        $envContent = @"
# Airflow Configuration
AIRFLOW_UID=50000
POSTGRES_USER=airflow
POSTGRES_PASSWORD=airflow
POSTGRES_DB=airflow
POSTGRES_HOST=postgres
POSTGRES_PORT=5432

# MLflow Configuration
MLFLOW_TRACKING_URI=http://mlflow-server:5500
MLFLOW_S3_ENDPOINT_URL=http://minio:9000

# MinIO Configuration
MINIO_USERNAME=minioadmin
MINIO_PASSWORD=minioadmin
AWS_ACCESS_KEY_ID=minioadmin
AWS_SECRET_ACCESS_KEY=minioadmin

# Fraud Detection API
FRAUD_API_URL=
FRAUD_API_MAX_RECORDS=100000

# Inference Service
INFERENCE_PORT=8000
INFERENCE_SERVICE_URL=http://inference:8000

# Moniguard
FLASK_DEBUG=False
"@
        Set-Content -Path "src\.env" -Value $envContent
        Write-ColorOutput Green ".env file created."
    }
} else {
    Write-ColorOutput Green ".env file already exists."
}

# Create necessary directories
Write-ColorOutput Yellow "Creating necessary directories..."
New-Item -ItemType Directory -Force -Path "src\models" | Out-Null
New-Item -ItemType Directory -Force -Path "src\logs" | Out-Null
New-Item -ItemType Directory -Force -Path "src\state" | Out-Null
New-Item -ItemType Directory -Force -Path "src\config" | Out-Null
New-Item -ItemType Directory -Force -Path "Moniguard\data" | Out-Null
New-Item -ItemType Directory -Force -Path "Moniguard\static" | Out-Null

# Check Docker
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-ColorOutput Red "Docker is not installed. Please install Docker Desktop."
    exit 1
}

# Check Docker Compose
$dockerComposeAvailable = $false
if (Get-Command docker-compose -ErrorAction SilentlyContinue) {
    $dockerComposeAvailable = $true
} elseif (docker compose version 2>&1 | Out-Null) {
    if ($LASTEXITCODE -eq 0) {
        $dockerComposeAvailable = $true
    }
}

if (-not $dockerComposeAvailable) {
    Write-ColorOutput Red "Docker Compose is not installed. Please install Docker Compose."
    exit 1
}

Write-ColorOutput Green "Local setup complete!"
Write-ColorOutput Yellow "Next steps:"
Write-Output "  1. (Optional) Review src\.env"
Write-Output "  2. make build   # or: cd src; docker compose build"
Write-Output "  3. make up     # or: cd src; docker compose up -d"
Write-Output "  4. make init-db   # first time only"
Write-Output "  5. Airflow: http://localhost:8080 (airflow/airflow) – enable fraud_detection_training DAG"
Write-Output "  6. Moniguard: http://localhost:5000""





