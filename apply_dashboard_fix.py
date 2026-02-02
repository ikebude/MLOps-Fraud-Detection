#!/usr/bin/env python3
"""
Quick restart script to apply the dashboard accuracy fix.
"""

import subprocess
import sys
import time

def run_command(cmd, cwd=None):
    """Run a command and return success status."""
    try:
        result = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)
        return result.returncode == 0, result.stdout, result.stderr
    except Exception as e:
        return False, "", str(e)

def restart_fraudguard():
    """Restart the FraudGuard service to apply the fix."""
    
    print("🔧 Restarting FraudGuard to apply dashboard accuracy fix...")
    
    # Navigate to src directory
    src_path = r"c:\Users\3Consult\Documents\AI Solution Projects\MLOps_Fraud_Detection\src"
    
    # Stop FraudGuard
    print("🛑 Stopping FraudGuard container...")
    success, stdout, stderr = run_command("docker-compose stop fraudguard", src_path)
    if not success:
        print(f"❌ Failed to stop FraudGuard: {stderr}")
        return False
    
    # Start FraudGuard
    print("🚀 Starting FraudGuard container...")
    success, stdout, stderr = run_command("docker-compose up -d fraudguard", src_path)
    if not success:
        print(f"❌ Failed to start FraudGuard: {stderr}")
        return False
    
    # Wait for it to be ready
    print("⏳ Waiting for FraudGuard to be ready...")
    time.sleep(10)
    
    # Check if it's running
    success, stdout, stderr = run_command("docker-compose ps fraudguard", src_path)
    if success and "Up" in stdout:
        print("✅ FraudGuard restarted successfully!")
        return True
    else:
        print(f"❌ FraudGuard may not be running properly: {stderr}")
        return False

def test_fix():
    """Test if the fix is working."""
    
    print("\n🧪 Testing the fix...")
    
    try:
        import requests
        response = requests.get("http://localhost:5000/api/model_metrics", timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('status') == 'success':
                metrics = data.get('metrics', {})
                precision = metrics.get('precision')
                if precision is not None and precision != 0:
                    print(f"✅ Fix working! Precision: {precision}")
                    return True
                else:
                    print("⚠️ API working but precision still 0 or missing")
            else:
                print(f"⚠️ API returned: {data.get('status')}")
        else:
            print(f"❌ API returned status {response.status_code}")
            
    except Exception as e:
        print(f"❌ Test failed: {e}")
    
    return False

if __name__ == "__main__":
    print("🔧 Dashboard Accuracy Fix - Apply & Test")
    print("=" * 50)
    
    if restart_fraudguard():
        if test_fix():
            print("\n🎉 SUCCESS! Dashboard accuracy fix applied successfully!")
            print("🌐 Refresh http://localhost:5000 to see the updated metrics")
        else:
            print("\n⚠️ FraudGuard restarted but fix may need more time")
            print("💡 Wait 30 seconds then refresh the dashboard")
            print("🧪 Run 'python test_dashboard_fix.py' to verify")
    else:
        print("\n❌ Failed to restart FraudGuard")
        print("💡 Check Docker logs: docker-compose logs fraudguard")
    
    print("\n📝 What was fixed:")
    print("   • Added detailed logging to MLflow metrics retrieval")
    print("   • Improved error handling in model metrics API")
    print("   • Fixed silent exception catching that prevented metrics from loading")
    print("   • Added metric extraction at top level for easier access")
