# Quick Access Script - Port Forwarding for All Services
# This script sets up port forwarding for all services so you can access them immediately

param(
    [string]$Namespace = "mlops"
)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Quick Access via Port Forwarding" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "This script will set up port forwarding for all services." -ForegroundColor Yellow
Write-Host "Each service will run in a separate PowerShell window." -ForegroundColor Yellow
Write-Host ""
Write-Host "Press Ctrl+C in each window to stop port forwarding." -ForegroundColor Yellow
Write-Host ""

$services = @(
    @{Name="airflow-webserver"; LocalPort=8080; ServicePort=8080; Description="Airflow Web UI"},
    @{Name="mlflow"; LocalPort=5000; ServicePort=5000; Description="MLflow UI"},
    @{Name="fraudguard"; LocalPort=5001; ServicePort=5000; Description="Fraud Guard UI"},
    @{Name="inference"; LocalPort=8000; ServicePort=8000; Description="Inference API"},
    @{Name="flower"; LocalPort=5555; ServicePort=5555; Description="Flower (Celery Monitor)"}
)

Write-Host "Setting up port forwarding for the following services:" -ForegroundColor Cyan
foreach ($svc in $services) {
    if ($svc.LocalPort -eq $svc.ServicePort) {
        Write-Host "  - $($svc.Description): http://localhost:$($svc.LocalPort)" -ForegroundColor Green
    } else {
        Write-Host "  - $($svc.Description): http://localhost:$($svc.LocalPort) (service port: $($svc.ServicePort))" -ForegroundColor Green
    }
}
Write-Host ""

$start = Read-Host "Start port forwarding? (Y/N)"
if ($start -ne "Y" -and $start -ne "y") {
    Write-Host "Cancelled." -ForegroundColor Yellow
    exit 0
}

Write-Host ""
Write-Host "Starting port forwarding..." -ForegroundColor Cyan
Write-Host ""

foreach ($svc in $services) {
    Write-Host "Starting $($svc.Description)..." -ForegroundColor Yellow
    
    # Check if service exists
    $svcCheck = kubectl get svc $svc.Name -n $Namespace 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  ⚠ Service '$($svc.Name)' not found. Skipping." -ForegroundColor Yellow
        continue
    }
    
    # Start port forwarding in new window
    $scriptBlock = {
        param($svcName, $localPort, $servicePort, $namespace, $description)
        Write-Host "========================================" -ForegroundColor Cyan
        Write-Host "$description" -ForegroundColor Cyan
        Write-Host "========================================" -ForegroundColor Cyan
        Write-Host "Service: $svcName" -ForegroundColor Yellow
        Write-Host "Access at: http://localhost:$localPort" -ForegroundColor Green
        if ($localPort -ne $servicePort) {
            Write-Host "Service port: $servicePort" -ForegroundColor Cyan
        }
        Write-Host ""
        Write-Host "Press Ctrl+C to stop..." -ForegroundColor Yellow
        Write-Host ""
        kubectl port-forward -n $namespace svc/$svcName ${localPort}:${servicePort}
    }
    
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "& { $($scriptBlock.ToString()) } -svcName '$($svc.Name)' -localPort $($svc.LocalPort) -servicePort $($svc.ServicePort) -namespace '$Namespace' -description '$($svc.Description)'"
    
    Start-Sleep -Seconds 2
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "Port forwarding started!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Access your services at:" -ForegroundColor Cyan
foreach ($svc in $services) {
    Write-Host "  $($svc.Description): http://localhost:$($svc.LocalPort)" -ForegroundColor Green
}
Write-Host ""
Write-Host "Note: Each service is running in a separate PowerShell window." -ForegroundColor Yellow
Write-Host "Close the windows or press Ctrl+C to stop port forwarding." -ForegroundColor Yellow
Write-Host ""
