# Check Airflow Users and Try Alternative Fix
$NAMESPACE = "mlops"
$podName = kubectl get pods -n $NAMESPACE -l app=airflow-webserver -o jsonpath='{.items[0].metadata.name}' 2>&1

Write-Host "=== Checking Airflow Users ===" -ForegroundColor Green
Write-Host ""

if (-not $podName -or $podName -match "error") {
    Write-Host "ERROR: Could not find Airflow pod" -ForegroundColor Red
    exit 1
}

Write-Host "Airflow pod: $podName" -ForegroundColor Cyan
Write-Host ""

# Check what users exist
$checkScript = @'
from airflow import settings
from airflow.providers.fab.auth_manager.models import User

session = settings.Session()
users = session.query(User).all()

if users:
    print("Existing users:")
    for u in users:
        print(f"  - {u.username} (email: {u.email}, active: {u.active})")
else:
    print("No users found")
'@

Write-Host "Checking existing users..." -ForegroundColor Yellow
$users = kubectl exec -n $NAMESPACE $podName -c airflow-webserver -- python3 -c $checkScript 2>&1
Write-Host $users

Write-Host ""
Write-Host "=== Trying to Create/Update User ===" -ForegroundColor Yellow

# Try using Airflow's internal user creation
$createScript = @'
from airflow import settings
from airflow.providers.fab.auth_manager.models import User, Role
from werkzeug.security import generate_password_hash

session = settings.Session()

# Get Admin role
admin_role = session.query(Role).filter(Role.name == 'Admin').first()
if not admin_role:
    admin_role = Role(name='Admin')
    session.add(admin_role)
    session.commit()

# Delete existing airflow user if exists
existing = session.query(User).filter(User.username == 'airflow').first()
if existing:
    session.delete(existing)
    session.commit()

# Create new user
user = User()
user.username = 'airflow'
user.email = 'admin@example.com'
user.first_name = 'Admin'
user.last_name = 'User'
user.active = True
user.password = generate_password_hash('airflow')
user.roles = [admin_role]

session.add(user)
session.commit()

print('SUCCESS: User created')
'@

Write-Host "Creating user..." -ForegroundColor Yellow
$result = kubectl exec -n $NAMESPACE $podName -c airflow-webserver -- python3 -c $createScript 2>&1

Write-Host $result

if ($result -match "SUCCESS") {
    Write-Host ""
    Write-Host "=== CREDENTIALS ===" -ForegroundColor Green
    Write-Host ""
    Write-Host "URL: http://4.153.190.166/airflow" -ForegroundColor Yellow
    Write-Host "Username: airflow" -ForegroundColor Yellow
    Write-Host "Password: airflow" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Try logging in now!" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "=== ALTERNATIVE: Database Reset ===" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "If login still fails, you may need to reset the database:" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Run this command:" -ForegroundColor Cyan
    Write-Host "  kubectl exec -n $NAMESPACE $podName -c airflow-webserver -- airflow db reset --yes" -ForegroundColor White
    Write-Host ""
    Write-Host "This will delete DAG history but create the default user." -ForegroundColor Yellow
}
