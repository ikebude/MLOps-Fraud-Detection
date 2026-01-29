# make.ps1 — Windows replacement for Makefile (use: .\make.ps1 <target>)
# Run from project root: MLOps_Fraud_Detection

param([Parameter(Position = 0)][string]$Target = "help")

$ErrorActionPreference = "Stop"
$Src = Join-Path $PSScriptRoot "src"

function Invoke-InSrc {
    param([scriptblock]$Cmd)
    Push-Location $Src
    try { & $Cmd } finally { Pop-Location }
}

switch ($Target) {
    "help" {
        @"
Usage: .\make.ps1 <target>

Targets:
  setup        Run local setup (PowerShell)
  build        Build all Docker images
  build-fast   Build images without cache
  up           Start all services
  up-flower    Start all services + Flower (Celery UI)
  up-logs      Start services and stream logs
  down         Stop all services
  down-volumes Stop and remove volumes
  clean        Stop, remove volumes, and remove images
  logs         Stream logs
  logs-service <name>   Stream logs for one service (e.g. inference)
  ps           Container status
  restart      Restart all services
  restart-service <name> Restart one service
  init-db      Initialize Airflow DB (first run)
  train        Trigger fraud_detection_training DAG
  inference    POST /inference/run (1000 records)
  results      GET /inference/results
  stats        GET /inference/stats
  test         Health checks

Examples:
  .\make.ps1 build
  .\make.ps1 up
  .\make.ps1 test
"@ | Write-Host
    }
    "setup"   { & (Join-Path $PSScriptRoot "scripts\setup-local.ps1") }
    "build"   { Invoke-InSrc { docker compose build } }
    "build-fast" { Invoke-InSrc { docker compose build --no-cache } }
    "up"      { Invoke-InSrc { docker compose up -d } }
    "up-flower" { Invoke-InSrc { docker compose --profile flower up -d } }
    "up-logs" { Invoke-InSrc { docker compose up } }
    "down"    { Invoke-InSrc { docker compose down } }
    "down-volumes" { Invoke-InSrc { docker compose down -v } }
    "clean"   { Invoke-InSrc { docker compose down -v --rmi all } }
    "logs"    { Invoke-InSrc { docker compose logs -f } }
    "logs-service" {
        $svc = $args[0]; if (-not $svc) { Write-Host "Usage: .\make.ps1 logs-service <service>"; exit 1 }
        Invoke-InSrc { docker compose logs -f $svc }
    }
    "ps"      { Invoke-InSrc { docker compose ps } }
    "restart" { Invoke-InSrc { docker compose restart } }
    "restart-service" {
        $svc = $args[0]; if (-not $svc) { Write-Host "Usage: .\make.ps1 restart-service <service>"; exit 1 }
        Invoke-InSrc { docker compose restart $svc }
    }
    "init-db" { Invoke-InSrc { docker compose up airflow-init } }
    "train"   {
        Write-Host "Triggering fraud_detection_training DAG..."
        Invoke-InSrc { docker compose exec airflow-webserver airflow dags trigger fraud_detection_training }
    }
    "inference" {
        Invoke-RestMethod -Uri "http://localhost:8000/inference/run" -Method POST `
            -ContentType "application/json" -Body '{"max_records": 1000}'
    }
    "results"  { (Invoke-RestMethod "http://localhost:8000/inference/results") | ConvertTo-Json -Depth 10 }
    "stats"    { (Invoke-RestMethod "http://localhost:8000/inference/stats") | ConvertTo-Json -Depth 10 }
    "test"     {
        Write-Host "Testing service health..."
        $checks = @(
            @{ N = "FraudGuard"; U = "http://localhost:5000/api/health" },
            @{ N = "Inference";  U = "http://localhost:8000/health" },
            @{ N = "MLflow";     U = "http://localhost:5500/health" },
            @{ N = "Airflow";    U = "http://localhost:8080/health" }
        )
        foreach ($c in $checks) {
            try {
                $r = Invoke-RestMethod -Uri $c.U -TimeoutSec 5
                Write-Host "$($c.N): OK" -ForegroundColor Green
            } catch { Write-Host "$($c.N): Not responding" -ForegroundColor Yellow }
        }
        try { Invoke-WebRequest -Uri "http://localhost:9000/minio/health/live" -UseBasicParsing -TimeoutSec 3 | Out-Null; Write-Host "MinIO: OK" -ForegroundColor Green }
        catch { Write-Host "MinIO: Not responding (optional)" -ForegroundColor Gray }
        try { Invoke-WebRequest -Uri "http://localhost:5555/" -UseBasicParsing -TimeoutSec 3 | Out-Null; Write-Host "Flower: OK" -ForegroundColor Green }
        catch { Write-Host "Flower: Not responding (.\make.ps1 up-flower to enable)" -ForegroundColor Gray }
    }
    default    { Write-Host "Unknown target: $Target. Run .\make.ps1 help"; exit 1 }
}
