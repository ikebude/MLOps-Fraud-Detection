#!/usr/bin/env python3
"""
Complete system health check for MLOps Fraud Detection
Verifies all services, databases, and configurations are working correctly
"""

import requests
import psycopg2
import os
import sys
import json
import time
from datetime import datetime
from dotenv import load_dotenv

# Load environment
load_dotenv()

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'

def print_status(message, status="info"):
    if status == "success":
        print(f"{Colors.GREEN}✅ {message}{Colors.END}")
    elif status == "error":
        print(f"{Colors.RED}❌ {message}{Colors.END}")
    elif status == "warning":
        print(f"{Colors.YELLOW}⚠️  {message}{Colors.END}")
    else:
        print(f"{Colors.BLUE}ℹ️  {message}{Colors.END}")

def check_service(url, name, timeout=5):
    """Check if a service is reachable"""
    try:
        response = requests.get(url, timeout=timeout)
        if response.status_code == 200:
            print_status(f"{name} is healthy", "success")
            return True
        else:
            print_status(f"{name} returned status {response.status_code}", "error")
            return False
    except requests.exceptions.ConnectionError:
        print_status(f"{name} is not reachable at {url}", "error")
        return False
    except Exception as e:
        print_status(f"{name} check failed: {e}", "error")
        return False

def check_database():
    """Check database connectivity and table existence"""
    try:
        # Check PostgreSQL connection
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST', '127.0.0.1'),
            port=int(os.getenv('DB_PORT', 5432)),
            database='transactions_db',
            user='postgres',
            password=os.getenv('POSTGRES_PASSWORD', 'airflow')
        )
        
        with conn.cursor() as cur:
            # Check transactions table
            cur.execute("SELECT COUNT(*) FROM transactions LIMIT 1")
            cur.fetchone()
            print_status("transactions table exists", "success")
            
            # Check fraud_predictions table
            cur.execute("SELECT COUNT(*) FROM fraud_predictions LIMIT 1")
            cur.fetchone()
            print_status("fraud_predictions table exists", "success")
            
            # Check user permissions
            cur.execute("SELECT 1")
            print_status("Database connection successful", "success")
        
        conn.close()
        return True
        
    except psycopg2.errors.UndefinedTable as e:
        if "fraud_predictions" in str(e):
            print_status("fraud_predictions table missing - run database initialization", "error")
        else:
            print_status(f"Database table missing: {e}", "error")
        return False
    except Exception as e:
        print_status(f"Database connection failed: {e}", "error")
        return False

def check_mlflow_model():
    """Check if MLflow has a trained model"""
    try:
        response = requests.get("http://localhost:5500/api/2.0/mlflow/registered-models/list", timeout=5)
        if response.status_code == 200:
            models = response.json().get('registered_models', [])
            fraud_model = next((m for m in models if m['name'] == 'fraud_detection_model'), None)
            if fraud_model:
                print_status("fraud_detection_model found in MLflow", "success")
                return True
            else:
                print_status("No trained model found - run training DAG", "warning")
                return False
        else:
            print_status("MLflow API not accessible", "error")
            return False
    except Exception as e:
        print_status(f"MLflow model check failed: {e}", "error")
        return False

def check_inference_model():
    """Check if inference service has loaded a model"""
    try:
        response = requests.get("http://localhost:8000/health", timeout=5)
        if response.status_code == 200:
            health = response.json()
            if health.get('model_loaded'):
                print_status("Inference service has loaded model", "success")
                return True
            else:
                print_status("Inference service hasn't loaded model", "warning")
                return False
        else:
            print_status("Inference health check failed", "error")
            return False
    except Exception as e:
        print_status(f"Inference model check failed: {e}", "error")
        return False

def check_dashboard_metrics():
    """Check if dashboard can fetch model metrics"""
    try:
        response = requests.get("http://localhost:5000/api/model_metrics", timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get('status') == 'success':
                precision = data.get('precision')
                if precision and precision > 0:
                    print_status(f"Dashboard metrics working (precision: {precision:.4f})", "success")
                    return True
                else:
                    print_status("Dashboard metrics loaded but precision is 0", "warning")
                    return False
            else:
                print_status(f"Dashboard metrics error: {data.get('message')}", "error")
                return False
        else:
            print_status("Dashboard metrics API not accessible", "error")
            return False
    except Exception as e:
        print_status(f"Dashboard metrics check failed: {e}", "error")
        return False

def main():
    print(f"{Colors.BOLD}{Colors.BLUE}")
    print("🔍 MLOps Fraud Detection - Complete System Health Check")
    print("=" * 60)
    print(f"{Colors.END}")
    
    results = []
    
    # Check core services
    print(f"\n{Colors.BOLD}📡 Service Health Checks{Colors.END}")
    results.append(check_service("http://localhost:5000/health", "FraudGuard Dashboard"))
    results.append(check_service("http://localhost:8000/health", "Inference API"))
    results.append(check_service("http://localhost:5500/health", "MLflow Server"))
    results.append(check_service("http://localhost:8080/health", "Airflow Webserver"))
    results.append(check_service("http://localhost:9001/minio/health/live", "MinIO Console"))
    
    # Check database
    print(f"\n{Colors.BOLD}🗄️  Database Checks{Colors.END}")
    db_ok = check_database()
    results.append(db_ok)
    
    # Check model status
    print(f"\n{Colors.BOLD}🤖 Model Status Checks{Colors.END}")
    results.append(check_mlflow_model())
    results.append(check_inference_model())
    results.append(check_dashboard_metrics())
    
    # Summary
    print(f"\n{Colors.BOLD}📊 Summary{Colors.END}")
    passed = sum(results)
    total = len(results)
    
    if passed == total:
        print_status(f"All {total} checks passed! System is healthy ✨", "success")
    else:
        print_status(f"{passed}/{total} checks passed", "warning")
        print(f"\n{Colors.YELLOW}To fix issues:{Colors.END}")
        print("1. Restart services: cd src && docker-compose restart")
        print("2. Reinitialize database: docker-compose down && docker-compose up -d postgres && sleep 10 && psql -h 127.0.0.1 -U postgres -f init-multiple-dbs.sh && docker-compose up -d")
        print("3. Run training: Open http://localhost:8080 and trigger 'fraud_detection_training' DAG")
        print("4. Check logs: docker-compose logs [service-name]")
    
    print(f"\n{Colors.BLUE}🌐 Access URLs:{Colors.END}")
    print("• Dashboard: http://localhost:5000")
    print("• Inference API: http://localhost:8000")
    print("• MLflow: http://localhost:5500")
    print("• Airflow: http://localhost:8080")
    print("• MinIO: http://localhost:9001")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
