# Get Airflow Credentials
$NAMESPACE = "mlops"
$podName = kubectl get pods -n $NAMESPACE -l app=airflow-webserver -o jsonpath='{.items[0].metadata.name}' 2>&1

Write-Host "=== Airflow Credentials ===" -ForegroundColor Green
Write-Host ""

if (-not $podName -or $podName -match "error") {
    Write-Host "ERROR: Could not find Airflow pod" -ForegroundColor Red
    exit 1
}

Write-Host "Airflow pod: $podName" -ForegroundColor Cyan
Write-Host ""

# Create/reset user
$script = @'
from airflow import settings
from airflow.providers.fab.auth_manager.models import User, Role
try:
    from flask_bcrypt import generate_password_hash
except ImportError:
    from werkzeug.security import generate_password_hash

session = settings.Session()

# Get or create Admin role
admin_role = session.query(Role).filter(Role.name == 'Admin').first()
if not admin_role:
    admin_role = Role(name='Admin')
    session.add(admin_role)

# Check if user exists
user = session.query(User).filter(User.username == 'airflow').first()

if user:
    print('Updating existing user...')
    user.password = generate_password_hash('airflow')
    user.active = True
    if admin_role not in user.roles:
        user.roles.append(admin_role)
else:
    print('Creating new user...')
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
    print('SUCCESS')
except Exception as e:
    print('ERROR: ' + str(e))
    session.rollback()
'@

Write-Host "Setting up Airflow user..." -ForegroundColor Yellow
$result = kubectl exec -n $NAMESPACE $podName -c airflow-webserver -- python3 -c $script 2>&1

Write-Host $result

if ($result -match "SUCCESS") {
    Write-Host ""
    Write-Host "=== CREDENTIALS ===" -ForegroundColor Green
    Write-Host ""
    Write-Host "URL: http://4.153.190.166/airflow" -ForegroundColor Yellow
    Write-Host "Username: airflow" -ForegroundColor Yellow
    Write-Host "Password: airflow" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "You can now login!" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "If that did not work, try database reset:" -ForegroundColor Yellow
    Write-Host "kubectl exec -n $NAMESPACE $podName -c airflow-webserver -- airflow db reset --yes" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "WARNING: Database reset will delete all DAG run history!" -ForegroundColor Red
}
