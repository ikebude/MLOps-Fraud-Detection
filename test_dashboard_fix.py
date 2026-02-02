#!/usr/bin/env python3
"""
Test script to verify the dashboard accuracy fix.
This script tests the MLflow metrics retrieval functionality.
"""

import requests
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_model_metrics_api():
    """Test the model metrics API endpoint."""
    
    # Test the standalone model metrics endpoint
    try:
        logger.info("Testing /api/model_metrics endpoint...")
        response = requests.get("http://localhost:5000/api/model_metrics", timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            logger.info(f"✅ Model metrics API status: {data.get('status')}")
            
            if data.get('status') == 'success':
                metrics = data.get('metrics', {})
                logger.info(f"📊 Found {len(metrics)} metrics")
                
                # Check for key metrics
                key_metrics = ['precision', 'recall', 'f1', 'auc_pr', 'threshold']
                for metric in key_metrics:
                    value = metrics.get(metric)
                    if value is not None:
                        logger.info(f"   {metric}: {value}")
                    else:
                        logger.warning(f"   {metric}: NOT FOUND")
                
                # Check top-level metrics
                logger.info("🔍 Top-level metrics:")
                for metric in key_metrics:
                    value = data.get(metric)
                    if value is not None:
                        logger.info(f"   {metric}: {value}")
                
            else:
                logger.warning(f"⚠️ API returned non-success status: {data}")
                
        else:
            logger.error(f"❌ Model metrics API failed with status {response.status_code}")
            logger.error(f"Response: {response.text}")
            
    except requests.exceptions.ConnectionError:
        logger.error("❌ Cannot connect to FraudGuard at http://localhost:5000")
        logger.info("Make sure the FraudGuard service is running")
    except Exception as e:
        logger.error(f"❌ Error testing model metrics API: {e}")

def test_main_dashboard_api():
    """Test the main dashboard API that includes model health."""
    
    try:
        logger.info("\nTesting /api/data endpoint (main dashboard)...")
        response = requests.get("http://localhost:5000/api/data", timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            logger.info(f"✅ Dashboard API status: {data.get('status')}")
            
            model_health = data.get('model_health', {})
            logger.info(f"🏥 Model health keys: {list(model_health.keys())}")
            
            # Check for key metrics in model_health
            key_metrics = ['precision', 'recall', 'f1', 'auc_pr', 'threshold']
            for metric in key_metrics:
                value = model_health.get(metric)
                if value is not None and value != '—':
                    logger.info(f"   {metric}: {value}")
                else:
                    logger.warning(f"   {metric}: {value}")
            
        else:
            logger.error(f"❌ Dashboard API failed with status {response.status_code}")
            logger.error(f"Response: {response.text}")
            
    except Exception as e:
        logger.error(f"❌ Error testing dashboard API: {e}")

def test_mlflow_direct():
    """Test direct MLflow connection."""
    
    try:
        logger.info("\nTesting direct MLflow connection...")
        response = requests.get("http://localhost:5500/health", timeout=5)
        
        if response.status_code == 200:
            logger.info("✅ MLflow is reachable")
        else:
            logger.warning(f"⚠️ MLflow health check failed: {response.status_code}")
            
    except Exception as e:
        logger.error(f"❌ Cannot connect to MLflow: {e}")

if __name__ == "__main__":
    logger.info("🧪 Testing Dashboard Accuracy Fix")
    logger.info("=" * 50)
    
    test_mlflow_direct()
    test_model_metrics_api()
    test_main_dashboard_api()
    
    logger.info("\n" + "=" * 50)
    logger.info("🎯 Test completed")
    logger.info("📝 Check the logs above to see if metrics are loading correctly")
    logger.info("🌐 If successful, refresh http://localhost:5000 to see the updated dashboard")
