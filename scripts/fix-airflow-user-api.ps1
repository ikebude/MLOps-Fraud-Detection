# Fix Airflow User via API (for Airflow 2.9+)
$ErrorActionPreference = "Continue"

Write-Host "=== Fixing Airflow User via API ===" -ForegroundColor Green
Write-Host ""

$NAMESPACE = "mlops"
$podName = kubectl get pods -n $NAMESPACE -l app=airflow-webserver -o jsonpath='{.items[0].metadata.name}' 2>&1

if (-not $podName -or $podName -match "error") {
    Write-Host "ERROR: Could not find Airflow pod" -ForegroundColor Red
    exit 1
}

Write-Host "Found pod: $podName" -ForegroundColor Cyan
Write-Host ""

# Method 1: Try using Python directly in the pod
Write-Host "Method 1: Creating user via Python script..." -ForegroundColor Yellow

$pythonScript = @"
from airflow.providers.fab.auth_manager.cli_commands.user_command import create_user
from airflow.auth.managers.fab.models import User
from airflow import settings
from sqlalchemy.orm import Session

session = settings.Session()

# Check if user exists
user = session.query(User).filter(User.username == 'airflow').first()

if user:
    # Update existing user password
    from flask_bcrypt import generate_password_hash
    user.password = generate_password_hash('airflow')
    session.commit()
    print('SUCCESS: Password updated for existing user')
else:
    # Create new user
    try:
        create_user(
            username='airflow',
            first_name='Admin',
            last_name='User',
            role='Admin',
            email='admin@example.com',
            password='airflow'
        )
        print('SUCCESS: User created')
    except Exception as e:
        print(f'ERROR: {str(e)}')
"@

Write-Host "Executing Python script in Airflow pod..." -ForegroundColor Cyan
$result = kubectl exec -n $NAMESPACE $podName -c airflow-webserver -- python3 -c $pythonScript 2>&1

if ($result -match "SUCCESS") {
    Write-Host "SUCCESS: User created/updated!" -ForegroundColor Green
} else {
    Write-Host "Trying alternative method..." -ForegroundColor Yellow
    
    # Method 2: Use standalone command
    Write-Host "Method 2: Using Airflow standalone initialization..." -ForegroundColor Yellow
    Write-Host "Note: This may require restarting the pod" -ForegroundColor Yellow
    
    # Method 3: Direct database update
    Write-Host "Method 3: Trying direct database update..." -ForegroundColor Yellow
    
    $dbScript = @"
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
    user.roles = []
    session.add(user)

user.password = generate_password_hash('airflow')
session.commit()
print('SUCCESS')
"@
    
    $result2 = kubectl exec -n $NAMESPACE $podName -c airflow-webserver -- python3 -c $dbScript 2>&1
    
    if ($result2 -match "SUCCESS") {
        Write-Host "SUCCESS: User password set!" -ForegroundColor Green
    } else {
        Write-Host "WARNING: Could not set password automatically" -ForegroundColor Yellow
        Write-Host "Output: $result2" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "MANUAL FIX REQUIRED:" -ForegroundColor Red
        Write-Host "1. Access the Airflow pod: kubectl exec -it -n $NAMESPACE $podName -c airflow-webserver -- bash" -ForegroundColor Cyan
        Write-Host "2. Run: airflow db init" -ForegroundColor Cyan
        Write-Host "3. The default user should be created automatically" -ForegroundColor Cyan
    }
}

Write-Host ""
Write-Host "=== Login Information ===" -ForegroundColor Green
Write-Host "URL: http://4.153.190.166/airflow" -ForegroundColor Yellow
Write-Host "Username: airflow" -ForegroundColor Yellow
Write-Host "Password: airflow" -ForegroundColor Yellow
Write-Host ""
Write-Host "If login still fails, the database may need to be reinitialized." -ForegroundColor Yellow
Write-Host "Try: kubectl exec -n $NAMESPACE $podName -c airflow-webserver -- airflow db init" -ForegroundColor Cyan
