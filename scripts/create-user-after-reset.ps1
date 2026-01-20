# Create User After Database Reset
$NAMESPACE = "mlops"
$podName = kubectl get pods -n $NAMESPACE -l app=airflow-webserver -o jsonpath='{.items[0].metadata.name}' 2>&1

Write-Host "=== Creating Airflow User After Reset ===" -ForegroundColor Green
Write-Host ""

# Wait a bit for database to be fully ready
Write-Host "Waiting for database to be ready..." -ForegroundColor Yellow
Start-Sleep -Seconds 10

# Create user script
$script = @'
from airflow import settings
from airflow.providers.fab.auth_manager.models import User, Role
from werkzeug.security import generate_password_hash

session = settings.Session()

# Get or create Admin role
admin_role = session.query(Role).filter(Role.name == 'Admin').first()
if not admin_role:
    admin_role = Role(name='Admin')
    session.add(admin_role)
    session.commit()

# Check if user exists
user = session.query(User).filter(User.username == 'airflow').first()

if not user:
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
else:
    # Update password
    user.password = generate_password_hash('airflow')
    user.active = True
    session.commit()
    print('SUCCESS: User password updated')
'@

Write-Host "Creating user..." -ForegroundColor Yellow
$result = kubectl exec -n $NAMESPACE $podName -c airflow-webserver -- python3 -c $script 2>&1

Write-Host $result

if ($result -match "SUCCESS") {
    Write-Host ""
    Write-Host "=== SUCCESS ===" -ForegroundColor Green
    Write-Host ""
    Write-Host "Credentials:" -ForegroundColor Cyan
    Write-Host "  URL: http://4.153.190.166/airflow" -ForegroundColor Yellow
    Write-Host "  Username: airflow" -ForegroundColor Yellow
    Write-Host "  Password: airflow" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Wait 1 minute, then try logging in!" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "Error creating user. Check output above." -ForegroundColor Red
}
