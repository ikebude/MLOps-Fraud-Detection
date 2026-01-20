# Get Admin User Password from Logs or Reset It
$NAMESPACE = "mlops"
$podName = kubectl get pods -n $NAMESPACE -l app=airflow-webserver -o jsonpath='{.items[0].metadata.name}' 2>&1

Write-Host "=== Admin User Credentials ===" -ForegroundColor Green
Write-Host ""

# Check logs for generated password
Write-Host "Checking pod logs for admin password..." -ForegroundColor Yellow
$allLogs = kubectl logs -n $NAMESPACE $podName -c airflow-webserver 2>&1
$passwordLine = $allLogs | Select-String -Pattern "Password for user.*admin" -CaseSensitive:$false

if ($passwordLine) {
    Write-Host "Found password in logs!" -ForegroundColor Green
    Write-Host $passwordLine -ForegroundColor Cyan
    
    # Extract password
    if ($passwordLine -match "Password for user 'admin':\s*(\S+)") {
        $password = $matches[1]
        Write-Host ""
        Write-Host "=== CREDENTIALS ===" -ForegroundColor Green
        Write-Host ""
        Write-Host "URL: http://4.153.190.166/airflow" -ForegroundColor Yellow
        Write-Host "Username: admin" -ForegroundColor Yellow
        Write-Host "Password: $password" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "This is the admin user with generated password!" -ForegroundColor Green
    }
} else {
    Write-Host "Password not found in current logs. Generating new password for admin user..." -ForegroundColor Yellow
    Write-Host ""
    
    # Generate new password and update admin user
    $script = @'
from airflow import settings
from airflow.providers.fab.auth_manager.models import User, Role
from werkzeug.security import generate_password_hash
import secrets
import string

session = settings.Session()

# Generate password
alphabet = string.ascii_letters + string.digits
password = ''.join(secrets.choice(alphabet) for i in range(12))

# Get or create Admin role
admin_role = session.query(Role).filter(Role.name == 'Admin').first()
if not admin_role:
    admin_role = Role(name='Admin')
    session.add(admin_role)
    session.commit()

# Get admin user (try admin first, then airflow)
user = session.query(User).filter(User.username == 'admin').first()
if not user:
    user = session.query(User).filter(User.username == 'airflow').first()
    if user:
        # Rename airflow to admin
        user.username = 'admin'
        user.email = 'admin@example.com'

if user:
    user.password = generate_password_hash(password)
    user.active = True
    if admin_role not in user.roles:
        user.roles.append(admin_role)
    session.commit()
    print('SUCCESS')
    print('USERNAME: admin')
    print('PASSWORD: ' + password)
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
    session.commit()
    print('SUCCESS')
    print('USERNAME: admin')
    print('PASSWORD: ' + password)
'@

    $result = kubectl exec -n $NAMESPACE $podName -c airflow-webserver -- python3 -c $script 2>&1
    
    Write-Host $result
    
    if ($result -match "SUCCESS") {
        $passwordLine = $result | Select-String -Pattern "PASSWORD:"
        if ($passwordLine) {
            $password = ($passwordLine -split "PASSWORD: ")[1].Trim()
            Write-Host ""
            Write-Host "=== CREDENTIALS ===" -ForegroundColor Green
            Write-Host ""
            Write-Host "URL: http://4.153.190.166/airflow" -ForegroundColor Yellow
            Write-Host "Username: admin" -ForegroundColor Yellow
            Write-Host "Password: $password" -ForegroundColor Yellow
        }
    }
}
