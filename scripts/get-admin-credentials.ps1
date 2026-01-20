# Get Admin User with Generated Password (Airflow Standalone Method)
$NAMESPACE = "mlops"
$podName = kubectl get pods -n $NAMESPACE -l app=airflow-webserver -o jsonpath='{.items[0].metadata.name}' 2>&1

Write-Host "=== Getting Admin User Credentials ===" -ForegroundColor Green
Write-Host ""

if (-not $podName -or $podName -match "error") {
    Write-Host "ERROR: Could not find Airflow pod" -ForegroundColor Red
    exit 1
}

Write-Host "Airflow pod: $podName" -ForegroundColor Cyan
Write-Host ""

# Check for admin user
Write-Host "Checking for 'admin' user..." -ForegroundColor Yellow
$checkScript = @'
from airflow import settings
from airflow.providers.fab.auth_manager.models import User

session = settings.Session()
admin_user = session.query(User).filter(User.username == 'admin').first()
airflow_user = session.query(User).filter(User.username == 'airflow').first()

if admin_user:
    print('Admin user exists')
    print('Active:', admin_user.active)
elif airflow_user:
    print('Airflow user exists (not admin)')
else:
    print('No admin or airflow user found')
'@

$checkResult = kubectl exec -n $NAMESPACE $podName -c airflow-webserver -- python3 -c $checkScript 2>&1
Write-Host $checkResult
Write-Host ""

# Try to create admin user using Airflow's method
Write-Host "Creating 'admin' user (this is what Airflow standalone creates)..." -ForegroundColor Yellow

$createAdminScript = @'
from airflow import settings
from airflow.providers.fab.auth_manager.models import User, Role
from werkzeug.security import generate_password_hash
import secrets
import string

session = settings.Session()

# Get or create Admin role
admin_role = session.query(Role).filter(Role.name == 'Admin').first()
if not admin_role:
    admin_role = Role(name='Admin')
    session.add(admin_role)
    session.commit()

# Generate a random password (like Airflow standalone does)
alphabet = string.ascii_letters + string.digits
password = ''.join(secrets.choice(alphabet) for i in range(12))

# Check if admin user exists
user = session.query(User).filter(User.username == 'admin').first()

if user:
    # Update existing admin user
    user.password = generate_password_hash(password)
    user.active = True
    if admin_role not in user.roles:
        user.roles.append(admin_role)
    print('Updated admin user')
else:
    # Create new admin user
    user = User()
    user.username = 'admin'
    user.email = 'admin@example.com'
    user.first_name = 'Admin'
    user.last_name = 'User'
    user.active = True
    user.password = generate_password_hash(password)
    user.roles = [admin_role]
    session.add(user)
    print('Created admin user')

try:
    session.commit()
    print('SUCCESS')
    print('USERNAME: admin')
    print('PASSWORD: ' + password)
except Exception as e:
    print('ERROR: ' + str(e))
    session.rollback()
'@

$result = kubectl exec -n $NAMESPACE $podName -c airflow-webserver -- python3 -c $createAdminScript 2>&1

Write-Host $result

if ($result -match "SUCCESS") {
    Write-Host ""
    Write-Host "=== CREDENTIALS ===" -ForegroundColor Green
    Write-Host ""
    
    # Extract password from output
    $passwordLine = $result | Select-String -Pattern "PASSWORD:"
    if ($passwordLine) {
        $password = ($passwordLine -split "PASSWORD: ")[1].Trim()
        Write-Host "URL: http://4.153.190.166/airflow" -ForegroundColor Yellow
        Write-Host "Username: admin" -ForegroundColor Yellow
        Write-Host "Password: $password" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "This is the admin user with generated password!" -ForegroundColor Green
    } else {
        Write-Host "Could not extract password. Check output above." -ForegroundColor Yellow
    }
} else {
    Write-Host ""
    Write-Host "Failed to create admin user. Trying alternative..." -ForegroundColor Yellow
    
    # Alternative: Check pod logs for generated password
    Write-Host ""
    Write-Host "Checking pod logs for generated password..." -ForegroundColor Cyan
    $logs = kubectl logs -n $NAMESPACE $podName -c airflow-webserver --tail=200 2>&1 | Select-String -Pattern "password|admin|generated" -CaseSensitive:$false
    if ($logs) {
        Write-Host "Found in logs:" -ForegroundColor Yellow
        Write-Host $logs
    }
}
