#!/usr/bin/env pwsh
# Post-Deployment Verification Script
# Run this after deployment to verify everything is healthy

Write-Host "===============================================" -ForegroundColor Cyan
Write-Host "  POST-DEPLOYMENT VERIFICATION SCRIPT" -ForegroundColor Cyan
Write-Host "===============================================`n" -ForegroundColor Cyan

# Function to check pod status
function Check-PodStatus {
    Write-Host "`n[1] Checking Pod Status..." -ForegroundColor Yellow
    $pods = kubectl -n mlops get pods -o json | ConvertFrom-Json
    
    $running = 0
    $notReady = 0
    
    foreach ($pod in $pods.items) {
        $name = $pod.metadata.name
        $status = $pod.status.phase
        
        if ($status -eq "Running") {
            $readyCount = ($pod.status.conditions | Where-Object {$_.type -eq "Ready"}).status
            if ($readyCount -eq "True") {
                Write-Host "  ✅ $name - Running and Ready" -ForegroundColor Green
                $running++
            } else {
                Write-Host "  ⚠️  $name - Running but NOT Ready" -ForegroundColor Yellow
                $notReady++
            }
        } else {
            Write-Host "  ❌ $name - Status: $status" -ForegroundColor Red
        }
    }
    
    Write-Host "`n  Summary: $running Running/Ready, $notReady Not Ready" -ForegroundColor Cyan
}

# Function to check service connectivity
function Check-Services {
    Write-Host "`n[2] Checking Service Connectivity..." -ForegroundColor Yellow
    
    $services = @("mlflow:5000", "flower:5555", "inference:8000", "fraudguard:5000", "airflow-webserver:8080", "postgres:5432", "redis:6379")
    
    foreach ($svc in $services) {
        $parts = $svc -split ":"
        $name = $parts[0]
        $port = $parts[1]
        
        # Get any running pod for testing
        $testPod = kubectl -n mlops get pod -l app=mlflow -o jsonpath='{.items[0].metadata.name}' 2>/dev/null
        
        if ($testPod) {
            try {
                $result = kubectl -n mlops exec $testPod -- nc -zv $name $port 2>&1 | Out-String
                if ($result -match "succeeded" -or $result -match "open") {
                    Write-Host "  ✅ $name:$port - Connected" -ForegroundColor Green
                } else {
                    Write-Host "  ⚠️  $name:$port - Check DNS" -ForegroundColor Yellow
                }
            } catch {
                Write-Host "  ⚠️  $name:$port - Cannot verify" -ForegroundColor Yellow
            }
        }
    }
}

# Function to check health endpoints
function Check-HealthEndpoints {
    Write-Host "`n[3] Checking Health Endpoints..." -ForegroundColor Yellow
    
    $endpoints = @(
        @{Pod="mlflow"; Port="5000"; Path="/"; Name="MLFlow"},
        @{Pod="flower"; Port="5555"; Path="/"; Name="Flower"},
        @{Pod="inference"; Port="8000"; Path="/health"; Name="Inference"},
        @{Pod="fraudguard"; Port="5000"; Path="/api/health"; Name="FraudGuard"},
        @{Pod="airflow-webserver"; Port="8080"; Path="/"; Name="Airflow"}
    )
    
    foreach ($ep in $endpoints) {
        $podId = kubectl -n mlops get pod -l app=$($ep.Pod) -o jsonpath='{.items[0].metadata.name}' 2>/dev/null
        
        if ($podId) {
            try {
                $health = kubectl -n mlops exec $podId -- curl -s -o /dev/null -w "%{http_code}" "http://localhost:$($ep.Port)$($ep.Path)" 2>/dev/null
                
                if ($health -eq "200") {
                    Write-Host "  ✅ $($ep.Name) ($health)" -ForegroundColor Green
                } else {
                    Write-Host "  ⚠️  $($ep.Name) (HTTP $health)" -ForegroundColor Yellow
                }
            } catch {
                Write-Host "  ❌ $($ep.Name) - Cannot reach" -ForegroundColor Red
            }
        }
    }
}

# Function to check data persistence
function Check-Persistence {
    Write-Host "`n[4] Checking Data Persistence..." -ForegroundColor Yellow
    
    # Check Postgres
    try {
        $pgPod = kubectl -n mlops get pod -l app=postgres -o jsonpath='{.items[0].metadata.name}' 2>/dev/null
        if ($pgPod) {
            $pgReady = kubectl -n mlops exec $pgPod -- pg_isready -U postgres 2>&1 | Out-String
            if ($pgReady -match "accepting connections") {
                Write-Host "  ✅ PostgreSQL - Data persisted (PVC)" -ForegroundColor Green
            } else {
                Write-Host "  ⚠️  PostgreSQL - Connection check failed" -ForegroundColor Yellow
            }
        }
    } catch {
        Write-Host "  ⚠️  PostgreSQL - Cannot verify" -ForegroundColor Yellow
    }
    
    # Check Redis
    try {
        $redisPod = kubectl -n mlops get pod -l app=redis -o jsonpath='{.items[0].metadata.name}' 2>/dev/null
        if ($redisPod) {
            $redisReady = kubectl -n mlops exec $redisPod -- redis-cli ping 2>&1 | Out-String
            if ($redisReady -match "PONG") {
                Write-Host "  ✅ Redis - Data persisted (PVC + AOF)" -ForegroundColor Green
            } else {
                Write-Host "  ⚠️  Redis - Connection check failed" -ForegroundColor Yellow
            }
        }
    } catch {
        Write-Host "  ⚠️  Redis - Cannot verify" -ForegroundColor Yellow
    }
}

# Function to check probe status
function Check-Probes {
    Write-Host "`n[5] Checking Probe Configuration..." -ForegroundColor Yellow
    
    $deployments = @("mlflow", "flower", "inference", "fraudguard")
    
    foreach ($dep in $deployments) {
        $podId = kubectl -n mlops get pod -l app=$dep -o jsonpath='{.items[0].metadata.name}' 2>/dev/null
        
        if ($podId) {
            $restart = kubectl -n mlops get pod $podId -o jsonpath='{.status.containerStatuses[0].restartCount}' 2>/dev/null
            $age = kubectl -n mlops get pod $podId -o jsonpath='{.metadata.creationTimestamp}' 2>/dev/null
            
            if ($restart -eq 0) {
                Write-Host "  ✅ $dep - No restarts (probes working)" -ForegroundColor Green
            } else {
                Write-Host "  ⚠️  $dep - Restarted $restart times (check logs)" -ForegroundColor Yellow
            }
        }
    }
}

# Function to show summary
function Show-Summary {
    Write-Host "`n===============================================" -ForegroundColor Cyan
    Write-Host "  VERIFICATION SUMMARY" -ForegroundColor Cyan
    Write-Host "===============================================`n" -ForegroundColor Cyan
    
    $allPods = kubectl -n mlops get pods --no-headers 2>/dev/null | wc -l
    $runningPods = kubectl -n mlops get pods --field-selector=status.phase=Running --no-headers 2>/dev/null | wc -l
    
    Write-Host "Total Pods: $allPods"
    Write-Host "Running Pods: $runningPods"
    
    if ($allPods -eq $runningPods) {
        Write-Host "`n✅ All services deployed successfully!" -ForegroundColor Green
    } else {
        Write-Host "`n⚠️  Some pods not running. Check logs:" -ForegroundColor Yellow
        Write-Host "  kubectl -n mlops logs <pod-name>" -ForegroundColor Gray
    }
    
    Write-Host "`nNext Steps:"
    Write-Host "1. Port-forward to access UIs: kubectl -n mlops port-forward svc/airflow-webserver 8080:8080"
    Write-Host "2. Access via ingress URLs (if configured)"
    Write-Host "3. Test DAG execution in Airflow" -ForegroundColor Gray
}

# Run all checks
Check-PodStatus
Check-Services
Check-HealthEndpoints
Check-Persistence
Check-Probes
Show-Summary

Write-Host "`n===============================================`n" -ForegroundColor Cyan
