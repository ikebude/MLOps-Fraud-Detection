# Fix Airflow Database Initialization
# This script initializes the Airflow database manually

param(
    [string]$Namespace = "mlops"
)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Fixing Airflow Database" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Get the airflow webserver pod
Write-Host "[1] Finding Airflow webserver pod..." -ForegroundColor Cyan
$jsonPath = '{.items[0].metadata.name}'
$podName = kubectl get pods -n $Namespace -l app=airflow-webserver -o jsonpath=$jsonPath 2>&1

if (-not $podName -or $podName -match "error") {
    Write-Host "  [ERROR] Could not find Airflow webserver pod" -ForegroundColor Red
    exit 1
}

Write-Host "  [OK] Found pod: $podName" -ForegroundColor Green
Write-Host ""

# Wait for pod to be ready (or at least running)
Write-Host "[2] Waiting for pod to be ready..." -ForegroundColor Cyan
$maxWait = 60
$waited = 0
$statusPath = '{.status.phase}'
while ($waited -lt $maxWait) {
    $phase = kubectl get pod $podName -n $Namespace -o jsonpath=$statusPath 2>&1
    if ($phase -eq "Running") {
        Write-Host "  [OK] Pod is running" -ForegroundColor Green
        break
    }
    Start-Sleep -Seconds 2
    $waited += 2
    Write-Host "  Waiting... ($waited/$maxWait seconds)" -ForegroundColor Yellow
}

if ($waited -ge $maxWait) {
    Write-Host "  [WARNING] Pod may not be fully ready, but proceeding..." -ForegroundColor Yellow
}
Write-Host ""

# Get container name (might be different if pod is crashing)
Write-Host "[3] Getting container name..." -ForegroundColor Cyan
$containerName = kubectl get pod $podName -n $Namespace -o jsonpath='{.spec.containers[0].name}' 2>&1

if (-not $containerName -or $containerName -match "error") {
    Write-Host "  [WARNING] Could not get container name, trying default 'airflow-webserver'" -ForegroundColor Yellow
    $containerName = "airflow-webserver"
} else {
    Write-Host "  [OK] Container name: $containerName" -ForegroundColor Green
}
Write-Host ""

# Check if container is actually running
$containerStatus = kubectl get pod $podName -n $Namespace -o jsonpath="{.status.containerStatuses[?(@.name=='$containerName')].ready}" 2>&1

if ($containerStatus -ne "true") {
    Write-Host "  [WARNING] Container is not ready. Pod may be in CrashLoopBackOff." -ForegroundColor Yellow
    Write-Host "  Trying to use init container or create a temporary pod..." -ForegroundColor Yellow
    Write-Host ""
    
    # Try using init container approach - create a job to initialize DB
    Write-Host "[4] Creating temporary job to initialize database..." -ForegroundColor Cyan
    
    $jobYaml = @"
apiVersion: batch/v1
kind: Job
metadata:
  name: airflow-db-init-$(Get-Date -Format 'yyyyMMddHHmmss')
  namespace: $Namespace
spec:
  template:
    spec:
      imagePullSecrets:
      - name: acr-secret
      containers:
      - name: init-db
        image: mlopsacr12345.azurecr.io/fraud-detection/airflow:latest
        command: ["sh", "-c"]
        args:
        - |
          airflow db check || airflow db init || airflow db upgrade
          airflow db check
        env:
        - name: AIRFLOW__DATABASE__SQL_ALCHEMY_CONN
          valueFrom:
            configMapKeyRef:
              name: airflow-config
              key: AIRFLOW__CORE__SQL_ALCHEMY_CONN
        - name: AIRFLOW__CORE__EXECUTOR
          valueFrom:
            configMapKeyRef:
              name: airflow-config
              key: AIRFLOW__CORE__EXECUTOR
      restartPolicy: Never
"@
    
    $jobYaml | kubectl apply -f - 2>&1 | Out-Null
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  [OK] Job created, waiting for completion..." -ForegroundColor Green
        Start-Sleep -Seconds 5
        
        # Wait for job to complete
        $jobName = kubectl get jobs -n $Namespace -o jsonpath='{.items[-1].metadata.name}' 2>&1
        Write-Host "  Job name: $jobName" -ForegroundColor Cyan
        
        $maxWait = 120
        $waited = 0
        while ($waited -lt $maxWait) {
            # Check if job succeeded
            $jobSucceeded = kubectl get job $jobName -n $Namespace -o jsonpath='{.status.succeeded}' 2>&1
            $jobFailed = kubectl get job $jobName -n $Namespace -o jsonpath='{.status.failed}' 2>&1
            $jobComplete = kubectl get job $jobName -n $Namespace -o jsonpath='{.status.conditions[?(@.type=="Complete")].status}' 2>&1
            
            if ($jobSucceeded -eq "1" -or $jobComplete -eq "True") {
                Write-Host "  [OK] Database initialization job completed successfully" -ForegroundColor Green
                
                # Get logs
                $jobPod = kubectl get pods -n $Namespace -l job-name=$jobName -o jsonpath='{.items[0].metadata.name}' 2>&1
                if ($jobPod -and -not ($jobPod -match "error")) {
                    Write-Host "  Job logs:" -ForegroundColor Cyan
                    kubectl logs $jobPod -n $Namespace 2>&1 | Select-Object -Last 15
                }
                
                # Clean up job
                kubectl delete job $jobName -n $Namespace 2>&1 | Out-Null
                break
            }
            
            if ($jobFailed -eq "1" -or ($jobFailed -match "^[1-9]")) {
                Write-Host "  [ERROR] Job failed" -ForegroundColor Red
                $jobPod = kubectl get pods -n $Namespace -l job-name=$jobName -o jsonpath='{.items[0].metadata.name}' 2>&1
                if ($jobPod -and -not ($jobPod -match "error")) {
                    Write-Host "  Job logs:" -ForegroundColor Cyan
                    kubectl logs $jobPod -n $Namespace 2>&1
                }
                kubectl delete job $jobName -n $Namespace 2>&1 | Out-Null
                exit 1
            }
            
            Start-Sleep -Seconds 5
            $waited += 5
            if ($waited % 15 -eq 0) {
                Write-Host "  Waiting... ($waited/$maxWait seconds)" -ForegroundColor Yellow
            }
        }
        
        if ($waited -ge $maxWait) {
            Write-Host "  [ERROR] Job timed out" -ForegroundColor Red
            exit 1
        }
    } else {
        Write-Host "  [ERROR] Failed to create job" -ForegroundColor Red
        exit 1
    }
} else {
    # Container is running, try direct exec
    Write-Host "[4] Initializing Airflow database..." -ForegroundColor Cyan
    Write-Host "  This may take a minute..." -ForegroundColor Yellow

    $initResult = kubectl exec -n $Namespace $podName -c $containerName -- airflow db init 2>&1

    if ($LASTEXITCODE -eq 0) {
        Write-Host "  [OK] Database initialized successfully" -ForegroundColor Green
    } else {
        Write-Host "  [WARNING] Database initialization returned exit code: $LASTEXITCODE" -ForegroundColor Yellow
        Write-Host "  Output: $initResult" -ForegroundColor Yellow
        
        # Try db upgrade instead
        Write-Host ""
        Write-Host "[5] Trying database upgrade instead..." -ForegroundColor Cyan
        $upgradeResult = kubectl exec -n $Namespace $podName -c $containerName -- airflow db upgrade 2>&1
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  [OK] Database upgraded successfully" -ForegroundColor Green
        } else {
            Write-Host "  [ERROR] Database upgrade also failed" -ForegroundColor Red
            Write-Host "  Output: $upgradeResult" -ForegroundColor Red
            Write-Host ""
            Write-Host "  Check database connection:" -ForegroundColor Yellow
            Write-Host "    kubectl get configmap airflow-config -n $Namespace -o yaml" -ForegroundColor Cyan
            exit 1
        }
    }
    Write-Host ""

    # Verify database
    Write-Host "[5] Verifying database connection..." -ForegroundColor Cyan
    $checkResult = kubectl exec -n $Namespace $podName -c $containerName -- airflow db check 2>&1

    if ($LASTEXITCODE -eq 0) {
        Write-Host "  [OK] Database connection verified" -ForegroundColor Green
    } else {
        Write-Host "  [WARNING] Database check failed" -ForegroundColor Yellow
        Write-Host "  Output: $checkResult" -ForegroundColor Yellow
    }
    Write-Host ""
}

# Restart the deployments to pick up the changes
Write-Host "[6] Restarting Airflow deployments..." -ForegroundColor Cyan
kubectl rollout restart deployment/airflow-webserver -n $Namespace 2>&1 | Out-Null

if ($LASTEXITCODE -eq 0) {
    Write-Host "  [OK] Webserver deployment restarted" -ForegroundColor Green
} else {
    Write-Host "  [ERROR] Failed to restart webserver deployment" -ForegroundColor Red
}

kubectl rollout restart deployment/airflow-scheduler -n $Namespace 2>&1 | Out-Null

if ($LASTEXITCODE -eq 0) {
    Write-Host "  [OK] Scheduler deployment restarted" -ForegroundColor Green
} else {
    Write-Host "  [ERROR] Failed to restart scheduler deployment" -ForegroundColor Red
}
Write-Host ""

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Next Steps" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "1. Wait for the pod to restart (check with):" -ForegroundColor Yellow
Write-Host "   kubectl get pods -n $Namespace -l app=airflow-webserver" -ForegroundColor Cyan
Write-Host ""
Write-Host "2. Check if pod is ready:" -ForegroundColor Yellow
Write-Host "   kubectl wait --for=condition=Ready --timeout=300s pod/$podName -n $Namespace" -ForegroundColor Cyan
Write-Host ""
Write-Host "3. Access Airflow UI via port-forwarding:" -ForegroundColor Yellow
Write-Host "   kubectl port-forward -n $Namespace svc/airflow-webserver 8080:8080" -ForegroundColor Cyan
Write-Host "   Then open: http://localhost:8080" -ForegroundColor Cyan
Write-Host "   Default credentials: airflow / airflow" -ForegroundColor Cyan
Write-Host ""
