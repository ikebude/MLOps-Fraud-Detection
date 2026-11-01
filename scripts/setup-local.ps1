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
    if (-not (Test-Path "src\.env.example")) {
        Write-ColorOutput Red "src\.env.example not found; restore it from git (git checkout -- src/.env.example)."
        exit 1
    }
    Copy-Item "src\.env.example" "src\.env"
    Write-ColorOutput Green "src\.env created. Replace every change-me value with your own secret before 'make up'."
} else {
    Write-ColorOutput Green ".env file already exists."
}

# Create necessary directories
Write-ColorOutput Yellow "Creating necessary directories..."
New-Item -ItemType Directory -Force -Path "src\models" | Out-Null
New-Item -ItemType Directory -Force -Path "src\logs" | Out-Null
New-Item -ItemType Directory -Force -Path "src\state" | Out-Null
New-Item -ItemType Directory -Force -Path "src\config" | Out-Null
New-Item -ItemType Directory -Force -Path "moniguard\data" | Out-Null
New-Item -ItemType Directory -Force -Path "moniguard\static" | Out-Null

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
Write-Output "  5. Airflow: http://localhost:8080 (user and password from src\.env) – enable fraud_detection_training DAG"
Write-Output "  6. Moniguard: http://localhost:5000""





