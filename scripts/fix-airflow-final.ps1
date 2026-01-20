# Final Fix for Airflow User (Airflow 2.9+ compatible)
$NAMESPACE = "mlops"
$podName = kubectl get pods -n $NAMESPACE -l app=airflow-webserver -o jsonpath='{.items[0].metadata.name}' 2>&1

Write-Host "=== Fixing Airflow User (Airflow 2.9+) ===" -ForegroundColor Green
Write-Host "Pod: $podName" -ForegroundColor Cyan
Write-Host ""

# Try method 1: Use correct import path for Airflow 2.9+
$pythonFix = @'
import sys
sys.path.insert(0, '/opt/airflow')

try:
    from airflow import settings
    from airflow.providers.fab.auth_manager.models import User
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
except ImportError as e:
    print(f'Import error: {e}')
    print('Trying alternative import...')
    try:
        from airflow import settings
        from airflow.www.security import User
        from werkzeug.security import generate_password_hash
        
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
        print('SUCCESS: User created/updated with alternative method!')
    except Exception as e2:
        print(f'Alternative method also failed: {e2}')
        print('Please use: airflow db reset --yes (WARNING: Deletes all data)')
except Exception as e:
    print(f'Error: {e}')
    print('Please use: airflow db reset --yes (WARNING: Deletes all data)')
'@

Write-Host "Attempting to create/update user..." -ForegroundColor Yellow
$result = kubectl exec -n $NAMESPACE $podName -c airflow-webserver -- python3 -c $pythonFix 2>&1

Write-Host $result

if ($result -match "SUCCESS") {
    Write-Host ""
    Write-Host "=== SUCCESS ===" -ForegroundColor Green
    Write-Host "Airflow credentials:" -ForegroundColor Cyan
    Write-Host "  URL: http://4.153.190.166/airflow" -ForegroundColor White
    Write-Host "  Username: airflow" -ForegroundColor White
    Write-Host "  Password: airflow" -ForegroundColor White
} else {
    Write-Host ""
    Write-Host "=== ALTERNATIVE SOLUTION ===" -ForegroundColor Yellow
    Write-Host "The Python method didn't work. Use database reset:" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "WARNING: This will DELETE all DAG runs and history!" -ForegroundColor Red
    Write-Host ""
    $confirm = Read-Host "Do you want to reset the database? (yes/no)"
    if ($confirm -eq "yes") {
        Write-Host "Resetting database..." -ForegroundColor Yellow
        kubectl exec -n $NAMESPACE $podName -c airflow-webserver -- airflow db reset --yes
        Write-Host ""
        Write-Host "Database reset complete. Default user should be: airflow/airflow" -ForegroundColor Green
    } else {
        Write-Host "Database reset cancelled." -ForegroundColor Yellow
        Write-Host ""
        Write-Host "Manual fix required. Access the pod and create user manually." -ForegroundColor Yellow
    }
}
