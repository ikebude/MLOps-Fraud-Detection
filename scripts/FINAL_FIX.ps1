# FINAL FIX SCRIPT - Airflow Credentials and FraudGuard Data
$ErrorActionPreference = "Continue"

$NAMESPACE = "mlops"
$BASE_URL = "http://4.153.190.166"

Write-Host "========================================" -ForegroundColor Green
Write-Host "FINAL FIX - Airflow & FraudGuard" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""

# ============================================
# PART 1: FIX AIRFLOW CREDENTIALS
# ============================================
Write-Host "PART 1: Fixing Airflow Credentials" -ForegroundColor Yellow
Write-Host "----------------------------------------" -ForegroundColor Yellow

$podName = kubectl get pods -n $NAMESPACE -l app=airflow-webserver -o jsonpath='{.items[0].metadata.name}' 2>&1

if ($podName -and -not ($podName -match "error")) {
    Write-Host "Airflow pod: $podName" -ForegroundColor Cyan
    
    # Try to initialize database and create default user
    Write-Host "Initializing Airflow database..." -ForegroundColor Yellow
    $initResult = kubectl exec -n $NAMESPACE $podName -c airflow-webserver -- airflow db init 2>&1
    
    # The default user should be created automatically in Airflow 2.9+
    # But let's try to ensure it exists
    Write-Host "Checking if default user exists..." -ForegroundColor Yellow
    
    # In Airflow 2.9+, the default user is created during db init
    # If it doesn't exist, we need to create it via the API or Python
    Write-Host ""
    Write-Host "SOLUTION: Airflow 2.9+ uses different user management" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Try these steps:" -ForegroundColor Yellow
    Write-Host "1. The default user should be: airflow / airflow" -ForegroundColor White
    Write-Host "2. If login fails, try resetting via:" -ForegroundColor White
    Write-Host "   kubectl exec -n $NAMESPACE $podName -c airflow-webserver -- airflow db reset --yes" -ForegroundColor Cyan
    Write-Host "   (WARNING: This will reset the database!)" -ForegroundColor Red
    Write-Host ""
    Write-Host "3. OR create user via Python:" -ForegroundColor White
    Write-Host "   kubectl exec -it -n $NAMESPACE $podName -c airflow-webserver -- python" -ForegroundColor Cyan
    Write-Host "   Then run Python code to create user" -ForegroundColor Cyan
} else {
    Write-Host "ERROR: Could not find Airflow pod" -ForegroundColor Red
}

Write-Host ""
Write-Host ""

# ============================================
# PART 2: FIX FRAUDGUARD DATA
# ============================================
Write-Host "PART 2: Fixing FraudGuard Data Population" -ForegroundColor Yellow
Write-Host "----------------------------------------" -ForegroundColor Yellow

# Step 1: Verify inference has data
Write-Host "Step 1: Checking inference service..." -ForegroundColor Cyan
$inferencePod = kubectl get pods -n $NAMESPACE -l app=inference -o jsonpath='{.items[0].metadata.name}' 2>&1

if ($inferencePod -and -not ($inferencePod -match "error")) {
    Write-Host "Inference pod: $inferencePod" -ForegroundColor Cyan
    
    # Check stats
    $statsJson = kubectl exec -n $NAMESPACE $inferencePod -- curl -s http://localhost:8000/inference/stats 2>&1
    
    if ($statsJson -match "total_records") {
        try {
            $stats = $statsJson | ConvertFrom-Json
            Write-Host "  Total Records: $($stats.total_records)" -ForegroundColor Green
            Write-Host "  Fraud Rate: $($stats.fraud_rate)%" -ForegroundColor Green
            
            if ($stats.total_records -eq 0) {
                Write-Host ""
                Write-Host "  WARNING: No data in inference. Running inference now..." -ForegroundColor Yellow
                kubectl exec -n $NAMESPACE $inferencePod -- curl -s -X POST http://localhost:8000/inference/run -H "Content-Type: application/json" -d '{\"max_records\": 100}' | Out-Null
                Write-Host "  Inference triggered. Waiting 15 seconds..." -ForegroundColor Yellow
                Start-Sleep -Seconds 15
            }
        } catch {
            Write-Host "  Could not parse stats, but endpoint is accessible" -ForegroundColor Yellow
        }
    } else {
        Write-Host "  WARNING: Inference stats endpoint not accessible" -ForegroundColor Yellow
        Write-Host "  Response: $($statsJson.Substring(0, [Math]::Min(200, $statsJson.Length)))" -ForegroundColor Yellow
    }
} else {
    Write-Host "ERROR: Could not find Inference pod" -ForegroundColor Red
}

Write-Host ""

# Step 2: Test FraudGuard API
Write-Host "Step 2: Testing FraudGuard API..." -ForegroundColor Cyan
try {
    $fraudguardResponse = Invoke-WebRequest -Uri "$BASE_URL/fraudguard/api/data" -UseBasicParsing -TimeoutSec 10 -ErrorAction Stop
    $fraudguardData = $fraudguardResponse.Content | ConvertFrom-Json
    
    Write-Host "  FraudGuard API Response:" -ForegroundColor Green
    Write-Host "    Total Transactions: $($fraudguardData.metrics.total_transactions)" -ForegroundColor Cyan
    Write-Host "    Fraud Rate: $($fraudguardData.metrics.fraud_rate)%" -ForegroundColor Cyan
    
    if ($fraudguardData.metrics.total_transactions -eq 0) {
        Write-Host ""
        Write-Host "  ISSUE: FraudGuard API returns 0 transactions" -ForegroundColor Yellow
        Write-Host "  This means FraudGuard cannot connect to inference service" -ForegroundColor Yellow
    }
} catch {
    Write-Host "  ERROR: Could not reach FraudGuard API" -ForegroundColor Red
    Write-Host "    Error: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host ""

# Step 3: Check FraudGuard logs
Write-Host "Step 3: Checking FraudGuard logs for errors..." -ForegroundColor Cyan
$fraudguardPod = kubectl get pods -n $NAMESPACE -l app=fraudguard -o jsonpath='{.items[0].metadata.name}' 2>&1

if ($fraudguardPod -and -not ($fraudguardPod -match "error")) {
    Write-Host "Recent FraudGuard logs (last 10 lines):" -ForegroundColor Yellow
    kubectl logs -n $NAMESPACE $fraudguardPod --tail=10 2>&1 | Select-Object -Last 5
}

Write-Host ""
Write-Host ""

# ============================================
# PART 3: MANUAL FIX INSTRUCTIONS
# ============================================
Write-Host "========================================" -ForegroundColor Green
Write-Host "MANUAL FIX INSTRUCTIONS" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""

Write-Host "AIRFLOW CREDENTIALS:" -ForegroundColor Yellow
Write-Host "-------------------" -ForegroundColor Yellow
Write-Host "If login still fails, try this:" -ForegroundColor Cyan
Write-Host ""
Write-Host "1. Access Airflow pod:" -ForegroundColor White
Write-Host "   kubectl exec -it -n $NAMESPACE $podName -c airflow-webserver -- bash" -ForegroundColor Cyan
Write-Host ""
Write-Host "2. Run this Python code in the pod:" -ForegroundColor White
Write-Host @"
   python3 << 'EOF'
   from airflow import settings
   from airflow.auth.managers.fab.models import User
   from flask_bcrypt import generate_password_hash
   
   session = settings.Session()
   user = session.query(User).filter(User.username == 'airflow').first()
   
   if not user:
       user = User()
       user.username = 'airflow'
       user.email = 'admin@example.com'
       user.first_name = 'Admin'
       user.last_name = 'User'
       user.active = True
       session.add(user)
   
   user.password = generate_password_hash('airflow')
   session.commit()
   print('SUCCESS: User created/updated')
   EOF
"@ -ForegroundColor Cyan
Write-Host ""

Write-Host "FRAUDGUARD DATA:" -ForegroundColor Yellow
Write-Host "---------------" -ForegroundColor Yellow
Write-Host "If FraudGuard still shows no data:" -ForegroundColor Cyan
Write-Host ""
Write-Host "1. Trigger inference via API:" -ForegroundColor White
Write-Host "   Invoke-WebRequest -Uri '$BASE_URL/inference/inference/run' -Method POST -ContentType 'application/json' -Body '{\"max_records\": 100}'" -ForegroundColor Cyan
Write-Host ""
Write-Host "2. Wait 30 seconds, then refresh FraudGuard UI" -ForegroundColor White
Write-Host "   URL: $BASE_URL/fraudguard" -ForegroundColor Cyan
Write-Host ""
Write-Host "3. Click 'Refresh Model' button in FraudGuard UI" -ForegroundColor White
Write-Host ""
Write-Host "4. Check FraudGuard logs if still not working:" -ForegroundColor White
Write-Host "   kubectl logs -n $NAMESPACE deployment/fraudguard --tail=50" -ForegroundColor Cyan
Write-Host ""

Write-Host "========================================" -ForegroundColor Green
Write-Host "DONE" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
