# Direct Fix for Airflow User
$NAMESPACE = "mlops"
$podName = kubectl get pods -n $NAMESPACE -l app=airflow-webserver -o jsonpath='{.items[0].metadata.name}' 2>&1

Write-Host "=== Fixing Airflow User ===" -ForegroundColor Green
Write-Host "Pod: $podName" -ForegroundColor Cyan
Write-Host ""

# Create Python script to fix user
$pythonFix = @'
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
    print('Creating new user...')
else:
    print('Updating existing user...')

user.password = generate_password_hash('airflow')
session.commit()
print('SUCCESS: User airflow/airflow is ready!')
'@

Write-Host "Executing Python script to create/update user..." -ForegroundColor Yellow
$result = kubectl exec -n $NAMESPACE $podName -c airflow-webserver -- python3 -c $pythonFix 2>&1

Write-Host $result -ForegroundColor $(if ($result -match "SUCCESS") { "Green" } else { "Yellow" })

if ($result -match "SUCCESS") {
    Write-Host ""
    Write-Host "=== SUCCESS ===" -ForegroundColor Green
    Write-Host "Airflow credentials are now:" -ForegroundColor Cyan
    Write-Host "  URL: http://4.153.190.166/airflow" -ForegroundColor White
    Write-Host "  Username: airflow" -ForegroundColor White
    Write-Host "  Password: airflow" -ForegroundColor White
    Write-Host ""
    Write-Host "You can now login!" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "If this didn't work, the user may need to be created via database reset." -ForegroundColor Yellow
    Write-Host "Try: kubectl exec -n $NAMESPACE $podName -c airflow-webserver -- airflow db reset --yes" -ForegroundColor Cyan
    Write-Host "(WARNING: This will reset the database and delete all DAG runs!)" -ForegroundColor Red
}
