#!/usr/bin/env pwsh
<#
.SYNOPSIS
    MLOps Fraud Detection - Service Port-Forwarding Setup
    
.DESCRIPTION
    Sets up Kubernetes port-forwarding for all services, making them accessible
    through the ingress IP at path-based URLs:
    
    - http://84.8.135.74/mlflow/
    - http://84.8.135.74/fraudguard/
    - http://84.8.135.74/airflow/
    - http://84.8.135.74/inference/
    - http://84.8.135.74/flower/
    
.NOTES
    This script runs port-forward jobs in the background. To stop them:
    Get-Job | Stop-Job
#>

param()

$ErrorActionPreference = "Stop"

Write-Host "`n🚀 MLOps Fraud Detection - Service Port-Forwarding Setup" -ForegroundColor Cyan
Write-Host "=" * 60

# Define services
$services = @(
    @{ name = "mlflow"; service = "mlflow"; port = 5000; localPort = 5001 },
    @{ name = "fraudguard"; service = "fraudguard"; port = 5000; localPort = 5002 },
    @{ name = "airflow"; service = "airflow-webserver"; port = 8080; localPort = 8001 },
    @{ name = "inference"; service = "inference"; port = 8000; localPort = 8002 },
    @{ name = "flower"; service = "flower"; port = 5555; localPort = 5556 }
)

Write-Host "`n📋 Starting port-forward jobs...\n"

# Start port-forward jobs
foreach ($svc in $services) {
    Write-Host "  • $($svc.name) ... " -NoNewline
    $job = Start-Job -Name "pf-$($svc.name)" -ScriptBlock {
        param($service, $port, $localPort)
        kubectl port-forward svc/$service $localPort`:$port -n mlops --address=127.0.0.1
    } -ArgumentList $svc.service, $svc.port, $svc.localPort
    
    Start-Sleep 1
    Write-Host "✓" -ForegroundColor Green
}

Write-Host "`n✅ All port-forward jobs started successfully!" -ForegroundColor Green

Write-Host "`n📍 Service URLs:
────────────────────────────────────────────────────
  MLflow:        http://127.0.0.1:5001
  FraudGuard:    http://127.0.0.1:5002
  Airflow:       http://127.0.0.1:8001/airflow  (login: airflow/airflow)
  Inference:     http://127.0.0.1:8002
  Flower:        http://127.0.0.1:5556
────────────────────────────────────────────────────
"

Write-Host "🔧 Manage Jobs:
────────────────────────────────────────────────────
  List jobs:     Get-Job
  Stop all:      Get-Job | Stop-Job
  Stop one:      Stop-Job -Name 'pf-mlflow'
────────────────────────────────────────────────────
"

Write-Host "⏳ Port-forward jobs are running. Press Ctrl+C to stop.\n"

# Keep script running
while ($true) { Start-Sleep 10 }
