# Initialize Airflow Database and Create User
$ErrorActionPreference = "Continue"

$NAMESPACE = "mlops"
$podName = kubectl get pods -n $NAMESPACE -l app=airflow-webserver -o jsonpath='{.items[0].metadata.name}' 2>&1

Write-Host "=== Initializing Airflow Database ===" -ForegroundColor Green
Write-Host ""

if (-not $podName -or $podName -match "error") {
    Write-Host "ERROR: Could not find Airflow pod" -ForegroundColor Red
    exit 1
}

Write-Host "Airflow pod: $podName" -ForegroundColor Cyan
Write-Host ""

# Step 1: Initialize database
Write-Host "Step 1: Initializing database..." -ForegroundColor Yellow
$initResult = kubectl exec -n $NAMESPACE $podName -c airflow-webserver -- airflow db init 2>&1

if ($LASTEXITCODE -eq 0) {
    Write-Host "Database initialized successfully" -ForegroundColor Green
} else {
    Write-Host "Database initialization output:" -ForegroundColor Yellow
    Write-Host $initResult
}

Write-Host ""

# Step 2: Create user using Airflow's built-in method
Write-Host "Step 2: Creating default user..." -ForegroundColor Yellow

# In Airflow 2.9+, we can use the standalone command or create via Python
# Let's try using the database directly after init
$createUserScript = @'
from airflow import settings
from airflow.providers.fab.auth_manager.models import User, Role
from werkzeug.security import generate_password_hash

session = settings.Session()

# Ensure Admin role exists
admin_role = session.query(Role).filter(Role.name == 'Admin').first()
if not admin_role:
    admin_role = Role(name='Admin', permissions=[])
    session.add(admin_role)
    session.commit()

# Check if user exists
user = session.query(User).filter(User.username == 'airflow').first()

if user:
    # Update existing
    user.password = generate_password_hash('airflow')
    user.active = True
    if admin_role not in user.roles:
        user.roles.append(admin_role)
    print('Updated existing user')
else:
    # Create new
    user = User()
    user.username = 'airflow'
    user.email = 'admin@example.com'
    user.first_name = 'Admin'
    user.last_name = 'User'
    user.active = True
    user.password = generate_password_hash('airflow')
    user.roles = [admin_role]
    session.add(user)
    print('Created new user')

try:
    session.commit()
    print('SUCCESS')
except Exception as e:
    print('ERROR: ' + str(e))
    session.rollback()
'@

$createResult = kubectl exec -n $NAMESPACE $podName -c airflow-webserver -- python3 -c $createUserScript 2>&1

Write-Host $createResult

if ($createResult -match "SUCCESS") {
    Write-Host ""
    Write-Host "=== SUCCESS ===" -ForegroundColor Green
    Write-Host ""
    Write-Host "Airflow Login Credentials:" -ForegroundColor Cyan
    Write-Host "  URL: http://4.153.190.166/airflow" -ForegroundColor Yellow
    Write-Host "  Username: airflow" -ForegroundColor Yellow
    Write-Host "  Password: airflow" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Wait 30 seconds, then try logging in!" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "=== Trying Database Reset ===" -ForegroundColor Yellow
    Write-Host "This will delete DAG history but ensure user is created..." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Run manually:" -ForegroundColor Cyan
    Write-Host "  kubectl exec -n $NAMESPACE $podName -c airflow-webserver -- airflow db reset --yes" -ForegroundColor White
}
