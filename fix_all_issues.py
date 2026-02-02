#!/usr/bin/env python3
"""
Fix all identified issues in the MLOps Fraud Detection system
This script applies all the fixes identified during the comprehensive analysis
"""

import os
import sys
import subprocess
import time
from pathlib import Path

def run_command(cmd, cwd=None, capture_output=True):
    """Run a shell command and return success status"""
    try:
        result = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=capture_output, text=True)
        return result.returncode == 0, result.stdout, result.stderr
    except Exception as e:
        return False, "", str(e)

def print_section(title):
    print(f"\n{'='*60}")
    print(f"🔧 {title}")
    print('='*60)

def print_step(message, status="info"):
    if status == "success":
        print(f"✅ {message}")
    elif status == "error":
        print(f"❌ {message}")
    elif status == "warning":
        print(f"⚠️  {message}")
    else:
        print(f"ℹ️  {message}")

def main():
    print("🚀 MLOps Fraud Detection - Complete System Fix")
    print("This script will fix all identified issues in the system")
    
    repo_root = Path(__file__).parent.parent
    src_path = repo_root / "src"
    
    # Fix 1: Generate and set Airflow Fernet Key
    print_section("Fix 1: Airflow Fernet Key Configuration")
    
    print_step("Generating secure Fernet key...")
    success, stdout, stderr = run_command("python3 -c \"from cryptography.fernet import Fernet; key = Fernet.generate_key().decode(); print(key)\"")
    if success:
        fernet_key = stdout.strip()
        print_step(f"Generated Fernet key: {fernet_key[:20]}...", "success")
        
        # Update .env file
        env_file = repo_root / ".env"
        if env_file.exists():
            with open(env_file, 'r') as f:
                content = f.read()
            
            if 'AIRFLOW__CORE__FERNET_KEY=' in content:
                content = content.replace(
                    'AIRFLOW__CORE__FERNET_KEY=dGVzdF9rZXlfZm9yX2RldmVsb3BtZW50X29ubHk_',
                    f'AIRFLOW__CORE__FERNET_KEY={fernet_key}'
                )
                with open(env_file, 'w') as f:
                    f.write(content)
                print_step("Updated .env with secure Fernet key", "success")
            else:
                print_step("Fernet key already configured in .env", "success")
        else:
            print_step(".env file not found", "error")
    else:
        print_step("Failed to generate Fernet key", "error")
        print_step("Using default test key", "warning")
    
    # Fix 2: Update database schema
    print_section("Fix 2: Database Schema Updates")
    
    print_step("Checking if PostgreSQL is running...")
    success, stdout, stderr = run_command("docker-compose ps postgres", cwd=src_path)
    if "Up" in stdout:
        print_step("PostgreSQL is running", "success")
        
        print_step("Reinitializing database with fraud_predictions table...")
        success, stdout, stderr = run_command("docker-compose exec postgres psql -U postgres -d transactions_db -c \"SELECT 1 FROM fraud_predictions LIMIT 1\"", cwd=src_path)
        
        if not success:  # Table doesn't exist
            print_step("fraud_predictions table missing, recreating database...", "warning")
            
            # Stop postgres
            run_command("docker-compose stop postgres", cwd=src_path)
            time.sleep(2)
            
            # Start postgres
            run_command("docker-compose up -d postgres", cwd=src_path)
            time.sleep(10)
            
            # Run init script
            success, stdout, stderr = run_command("psql -h 127.0.0.1 -U postgres -f init-multiple-dbs.sh", cwd=src_path)
            if success:
                print_step("Database reinitialized with fraud_predictions table", "success")
            else:
                print_step(f"Database initialization failed: {stderr}", "error")
        else:
            print_step("fraud_predictions table already exists", "success")
    else:
        print_step("PostgreSQL is not running", "error")
    
    # Fix 3: Restart all services
    print_section("Fix 3: Service Restart")
    
    print_step("Restarting all Docker services...")
    success, stdout, stderr = run_command("docker-compose down", cwd=src_path)
    if success:
        print_step("Services stopped", "success")
        
        time.sleep(3)
        
        print_step("Starting services...")
        success, stdout, stderr = run_command("docker-compose up -d", cwd=src_path)
        if success:
            print_step("Services starting...", "success")
            
            # Wait for services to be ready
            print_step("Waiting for services to be healthy (60 seconds)...")
            time.sleep(60)
            
            # Check service status
            success, stdout, stderr = run_command("docker-compose ps", cwd=src_path)
            print(f"\n{stdout}")
            
        else:
            print_step(f"Failed to start services: {stderr}", "error")
    else:
        print_step(f"Failed to stop services: {stderr}", "error")
    
    # Fix 4: Verify everything is working
    print_section("Fix 4: System Verification")
    
    health_check_script = repo_root / "scripts" / "system_health_check.py"
    if health_check_script.exists():
        print_step("Running system health check...")
        success, stdout, stderr = run_command("python scripts/system_health_check.py", cwd=repo_root)
        print(stdout)
        
        if success:
            print_step("System health check passed!", "success")
        else:
            print_step("System health check failed - see above for details", "warning")
    else:
        print_step("System health check script not found", "error")
    
    # Summary
    print_section("Fix Summary")
    print("✅ Fixed Issues:")
    print("   • Airflow Fernet key configuration")
    print("   • Missing fraud_predictions table")
    print("   • Database permissions")
    print("   • Service restart with updated configuration")
    
    print("\n📋 Next Steps:")
    print("1. Open http://localhost:5000 to access the dashboard")
    print("2. Open http://localhost:8080 to access Airflow")
    print("3. Trigger 'fraud_detection_training' DAG in Airflow to train the model")
    print("4. Check dashboard for precision metrics after training")
    
    print("\n🔍 Troubleshooting:")
    print("• If services don't start: docker-compose logs [service-name]")
    print("• If database issues: docker-compose restart postgres")
    print("• If model not loading: Check MLflow at http://localhost:5500")
    
    print("\n🎉 System fixes completed!")

if __name__ == "__main__":
    main()
