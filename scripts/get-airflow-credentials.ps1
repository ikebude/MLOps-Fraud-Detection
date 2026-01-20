# Get or Reset Airflow Credentials
$ErrorActionPreference = "Continue"

$NAMESPACE = "mlops"
$podName = kubectl get pods -n $NAMESPACE -l app=airflow-webserver -o jsonpath='{.items[0].metadata.name}' 2>&1

Write-Host "=== Airflow Credentials ===" -ForegroundColor Green
Write-Host ""

if (-not $podName -or $podName -match "error") {
    Write-Host "ERROR: Could not find Airflow webserver pod" -ForegroundColor Red
    exit 1
}

Write-Host "Found Airflow pod: $podName" -ForegroundColor Cyan
Write-Host ""

# Try to check if user exists and get info
Write-Host "Checking for existing Airflow user..." -ForegroundColor Yellow

$checkUserScript = @'
from airflow import settings
from airflow.providers.fab.auth_manager.models import User
import sys

try:
    session = settings.Session()
    user = session.query(User).filter(User.username == 'airflow').first()
    if user:
        print(f"User exists: {user.username}")
        print(f"Email: {user.email}")
        print(f"Active: {user.active}")
        print(f"Roles: {[r.name for r in user.roles]}")
        sys.exit(0)
    else:
        print("User 'airflow' does not exist")
        sys.exit(1)
except Exception as e:
    print(f"Error: {e}")
    sys.exit(2)
'@

$result = kubectl exec -n $NAMESPACE $podName -c airflow-webserver -- python3 -c $checkUserScript 2>&1

if ($LASTEXITCODE -eq 0 -and $result -match "User exists") {
    Write-Host "✓ User 'airflow' exists" -ForegroundColor Green
    Write-Host $result -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Default credentials should be:" -ForegroundColor Yellow
    Write-Host "  Username: airflow" -ForegroundColor White
    Write-Host "  Password: airflow" -ForegroundColor White
    Write-Host ""
    Write-Host "If login fails, try resetting the password..." -ForegroundColor Yellow
} else {
    Write-Host "User 'airflow' does not exist or error occurred" -ForegroundColor Yellow
    Write-Host "Creating user..." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== Reset/Create User ===" -ForegroundColor Green
Write-Host ""

# Create/reset user script
$createUserScript = @'
from airflow import settings
from airflow.providers.fab.auth_manager.models import User, Role
from flask_bcrypt import generate_password_hash
import sys

session = settings.Session()

# Get or create Admin role
admin_role = session.query(Role).filter(Role.name == 'Admin').first()
if not admin_role:
    admin_role = Role(name='Admin')
    session.add(admin_role)

# Check if user exists
user = session.query(User).filter(User.username == 'airflow').first()

if user:
    print("Updating existing user...")
    user.password = generate_password_hash('airflow')
    user.active = True
    if admin_role not in user.roles:
        user.roles.append(admin_role)
else:
    print("Creating new user...")
    user = User()
    user.username = 'airflow'
    user.email = 'admin@example.com'
    user.first_name = 'Admin'
    user.last_name = 'User'
    user.active = True
    user.password = generate_password_hash('airflow')
    user.roles = [admin_role]
    session.add(user)

try:
    session.commit()
    print("SUCCESS: User created/updated!")
    print("Username: airflow")
    print("Password: airflow")
    sys.exit(0)
except Exception as e:
    print(f"ERROR: {e}")
    session.rollback()
    sys.exit(1)
'@

Write-Host "Creating/updating Airflow user..." -ForegroundColor Yellow
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
    Write-Host "You can now login!" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "=== ALTERNATIVE METHOD ===" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "If the above did not work, try database reset:" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "WARNING: This will DELETE all DAG run history!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Command:" -ForegroundColor Cyan
    Write-Host "  kubectl exec -n $NAMESPACE $podName -c airflow-webserver -- airflow db reset --yes" -ForegroundColor White
    Write-Host ""
    Write-Host "After reset, default credentials:" -ForegroundColor Yellow
    Write-Host "  Username: airflow" -ForegroundColor White
    Write-Host "  Password: airflow" -ForegroundColor White
}
