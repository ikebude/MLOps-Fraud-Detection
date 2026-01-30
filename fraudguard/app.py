from flask import Flask, render_template, jsonify, request, stream_with_context, Response
import json
import os
import requests
from datetime import datetime
import time
import math
from dotenv import load_dotenv
from functools import lru_cache
import concurrent.futures
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    import mlflow
    MLFLOW_AVAILABLE = True
except ImportError:
    MLFLOW_AVAILABLE = False

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Configuration from environment variables
INFERENCE_SERVICE_URL = os.getenv('INFERENCE_SERVICE_URL', 'http://inference:8000')
MLFLOW_TRACKING_URI = os.getenv('MLFLOW_TRACKING_URI', 'http://mlflow:5000')
AIRFLOW_WEBSERVER_URL = os.getenv('AIRFLOW_WEBSERVER_URL', 'http://airflow-webserver:8080')
FRAUDGUARD_BASE_PATH = os.getenv('FRAUDGUARD_BASE_PATH', '').rstrip('/')
FRAUDGUARD_REALTIME_INFERENCE = os.getenv('FRAUDGUARD_REALTIME_INFERENCE', 'true').lower() == 'true'
FRAUDGUARD_REALTIME_MODE = os.getenv('FRAUDGUARD_REALTIME_MODE', 'per_transaction').lower()
FRAUDGUARD_REALTIME_MAX_RECORDS = int(os.getenv('FRAUDGUARD_REALTIME_MAX_RECORDS', '1'))
if FRAUDGUARD_BASE_PATH and not FRAUDGUARD_BASE_PATH.startswith('/'):
    FRAUDGUARD_BASE_PATH = f'/{FRAUDGUARD_BASE_PATH}'

DEFAULT_DATA = {
    'metrics': {
        'total_transactions': 0,
        'fraud_rate': 0.0,
        'approval_rate': 0.0,
        'active_alerts': 0
    },
    'model_health': {
        'name': 'Unknown',
        'version': 'N/A',
        'accuracy': 0.0,
        'drift_status': 'Unknown'
    },
    'transactions': []
}

@app.context_processor
def inject_base_path():
    return {'base_path': FRAUDGUARD_BASE_PATH}

def clean_nan_values(obj):
    """Recursively replace NaN, Infinity, and -Infinity with None (which becomes null in JSON)
    This prevents JSON serialization errors."""
    if isinstance(obj, dict):
        return {k: clean_nan_values(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean_nan_values(item) for item in obj]
    elif isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return 0.0
        return obj
    return obj

def _pick_first(data, keys, default=None):
    """Pick first available key from data dict"""
    if isinstance(data, dict):
        for key in keys:
            if key in data:
                return data[key]
    return default

def _build_transactions(results, sort_by: str = 'timestamp', sort_order: str = 'desc'):
    """
    Build transaction list from inference results with enhanced sorting.
    
    Args:
        results: List of inference result dictionaries
        sort_by: Sort field ('timestamp', 'risk_score', 'amount', 'fraud_probability')
        sort_order: 'asc' or 'desc'
    
    Returns:
        List of formatted transaction dictionaries, properly sorted
    """
    transactions = []
    for result in results:
        txn_id = _pick_first(result, ['transaction_id', 'id', 'txn_id'], 'Unknown')
        user_id = _pick_first(result, ['user_id', 'user', 'customer_id'], 'Unknown')
        amount = _pick_first(result, ['amount', 'transaction_amount', 'value'], 0.0)
        timestamp = _pick_first(result, ['timestamp', 'time', 'created_at', 'prediction_timestamp'], None)
        
        # Get fraud prediction
        fraud_pred = _pick_first(result, ['fraud_prediction', 'is_fraud', 'fraud'], 0)
        fraud_prob = _pick_first(result, ['fraud_probability', 'fraud_score', 'probability'], 0.0)
        confidence = _pick_first(result, ['confidence', 'model_confidence'], 0.0)
        
        # Calculate risk score (0-100)
        risk_score = int(fraud_prob * 100) if isinstance(fraud_prob, (int, float)) else int(confidence * 100) if isinstance(confidence, (int, float)) else 0
        
        # Format timestamp
        sort_timestamp = None
        if timestamp:
            try:
                if isinstance(timestamp, str):
                    # Try parsing ISO format
                    dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                else:
                    dt = timestamp
                time_str = dt.strftime('%a, %d %b %Y %H:%M:%S GMT')
                sort_timestamp = dt.timestamp()
            except:
                time_str = str(timestamp)
                sort_timestamp = 0
        else:
            time_str = datetime.now().strftime('%a, %d %b %Y %H:%M:%S GMT')
            sort_timestamp = datetime.now().timestamp()
        
        # Get top features if available
        top_features = result.get('top_features', []) if isinstance(result, dict) else []
        
        # Get merchant/vendor info if available
        merchant = _pick_first(result, ['merchant', 'vendor', 'vendor_name', 'merchant_name'], 'Transaction')
        
        transactions.append({
            'id': txn_id,
            'user_id': user_id,
            'time': time_str,
            'timestamp': time_str,
            '_sort_timestamp': sort_timestamp,
            'merchant': merchant,
            'amount': float(amount) if amount else 0.0,
            'risk_score': risk_score,
            '_sort_risk_score': risk_score,
            'fraud_probability': float(fraud_prob) if fraud_prob else 0.0,
            '_sort_fraud_probability': float(fraud_prob) if fraud_prob else 0.0,
            'status': 'Flagged' if (fraud_pred == 1 or str(fraud_pred).lower() == 'true') else 'Approved',
            'top_features': top_features[:5] if isinstance(top_features, list) else []
        })
    
    # Enhanced multi-column sorting
    reverse = (sort_order.lower() == 'desc')
    
    if sort_by == 'risk_score':
        transactions.sort(key=lambda x: (x.get('_sort_risk_score', 0), x.get('_sort_timestamp', 0)), reverse=reverse)
    elif sort_by == 'amount':
        transactions.sort(key=lambda x: (x.get('amount', 0), x.get('_sort_timestamp', 0)), reverse=reverse)
    elif sort_by == 'fraud_probability':
        transactions.sort(key=lambda x: (x.get('_sort_fraud_probability', 0), x.get('_sort_timestamp', 0)), reverse=reverse)
    else:  # Default: timestamp
        transactions.sort(key=lambda x: x.get('_sort_timestamp', 0), reverse=reverse)
    
    return transactions

def _build_trends(results):
    """Build trend data for charts from inference results - FIXED TO SHOW CORRECT TIME"""
    if not results:
        return {
            'labels': [],
            'valid_transactions': [],
            'fraud_attempts': []
        }
    
    # Sort results by timestamp first (newest first)
    sorted_results = []
    for txn in results:
        ts_str = _pick_first(txn, ['timestamp', 'time', 'created_at', 'prediction_timestamp'], None)
        try:
            if isinstance(ts_str, str):
                ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
            else:
                ts = ts_str if ts_str else datetime.now()
            sorted_results.append((ts, txn))
        except:
            sorted_results.append((datetime.now(), txn))
    
    # Sort by timestamp (oldest to newest for chronological display)
    sorted_results.sort(key=lambda x: x[0])
    
    # Group by 15-minute time buckets with ACTUAL timestamps
    buckets = {}
    for ts, txn in sorted_results:
        try:
            # Round to 15-minute bucket
            minute = (ts.minute // 15) * 15
            bucket_time = ts.replace(minute=minute, second=0, microsecond=0)
            # Use actual datetime for label (shows real time)
            label = bucket_time.strftime('%H:%M')
            # Store full timestamp for sorting
            bucket_key = bucket_time.isoformat()
        except:
            bucket_key = f"bucket_{len(buckets)}"
            label = f"T{len(buckets) + 1}"
        
        if bucket_key not in buckets:
            buckets[bucket_key] = {'total': 0, 'fraud': 0, 'timestamp': bucket_time, 'label': label}
        buckets[bucket_key]['total'] += 1
        fraud_pred = _pick_first(txn, ['fraud_prediction'], 0)
        if str(fraud_pred) in ('1', 'True', 'true'):
            buckets[bucket_key]['fraud'] += 1

    # Sort buckets by timestamp (chronological order)
    sorted_buckets = sorted(buckets.items(), key=lambda x: x[1]['timestamp'] if x[1]['timestamp'] else datetime.min)
    # Take last 20 for display (most recent)
    sorted_buckets = sorted_buckets[-20:] if len(sorted_buckets) > 20 else sorted_buckets
    
    labels = [b['label'] for _, b in sorted_buckets]
    valid = [(b['total'] - b['fraud']) for _, b in sorted_buckets]
    frauds = [b['fraud'] for _, b in sorted_buckets]

    return {
        'labels': labels,
        'valid_transactions': valid,
        'fraud_attempts': frauds
    }


@lru_cache(maxsize=1)
def _get_model_health_cached():
    """Cached version to avoid repeated MLflow calls"""
    return _get_model_health_impl()

def _get_model_health_impl():
    """Get model health information from MLflow - FIXED TO GET ACTUAL VERSION"""
    model_name = "fraud_detection_model"
    model_version = "N/A"
    model_accuracy = 0.0
    run_name = None
    
    if not MLFLOW_AVAILABLE:
        logger.warning("MLflow not available")
        return {
            'name': model_name,
            'version': model_version,
            'accuracy': model_accuracy,
            'run_name': run_name
        }
    
    try:
        mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
        client = mlflow.tracking.MlflowClient()
        logger.info(f"Connecting to MLflow at {MLFLOW_TRACKING_URI}")
        
        # FIRST: Try to get registered model version (actual version number like "8")
        registered_model_found = False
        try:
            registered_models = client.search_registered_models()
            logger.info(f"Found {len(registered_models)} registered models")
            
            # Find model by name
            target_model = None
            for m in registered_models:
                if m.name == model_name:
                    target_model = m
                    break
            
            if target_model:
                # Get all versions for this model
                model_versions = client.search_model_versions(f"name='{model_name}'")
                logger.info(f"Found {len(model_versions)} versions for {model_name}")
                
                if model_versions:
                    # Sort by version number (descending) to get latest
                    # Handle both numeric and non-numeric versions
                    def version_key(v):
                        try:
                            return int(v.version)
                        except:
                            return 0
                    
                    sorted_versions = sorted(model_versions, key=version_key, reverse=True)
                    latest_version = sorted_versions[0]
                    model_version = latest_version.version  # Actual version number like "8"
                    run_id = latest_version.run_id
                    logger.info(f"Found registered model version: {model_version}, run_id: {run_id}")
                    
                    # Get run details for metrics and name
                    try:
                        run = client.get_run(run_id)
                        run_name = run.info.run_name if hasattr(run.info, 'run_name') else None
                        metrics = run.data.metrics if hasattr(run, 'data') and hasattr(run.data, 'metrics') else {}
                        logger.info(f"Run metrics available: {list(metrics.keys())}")
                        
                        # Get precision
                        if 'precision' in metrics:
                            model_accuracy = float(metrics['precision']) * 100
                            logger.info(f"Found precision: {model_accuracy}%")
                        elif 'test_precision' in metrics:
                            model_accuracy = float(metrics['test_precision']) * 100
                        elif 'val_precision' in metrics:
                            model_accuracy = float(metrics['val_precision']) * 100
                        elif 'test_accuracy' in metrics:
                            model_accuracy = float(metrics['test_accuracy']) * 100
                        elif 'accuracy' in metrics:
                            model_accuracy = float(metrics['accuracy']) * 100
                        elif 'f1' in metrics:
                            model_accuracy = float(metrics['f1']) * 100
                        elif 'f1_score' in metrics:
                            model_accuracy = float(metrics['f1_score']) * 100
                        elif 'roc_auc' in metrics:
                            model_accuracy = float(metrics['roc_auc']) * 100
                        else:
                            logger.warning(f"No accuracy metric found. Available: {list(metrics.keys())}")
                        
                        logger.info(f"Model version {model_version}: accuracy={model_accuracy}%, run_name={run_name}")
                        registered_model_found = True
                    except Exception as run_err:
                        logger.error(f"Error getting run {run_id}: {run_err}")
                        import traceback
                        traceback.print_exc()
            else:
                logger.info(f"No registered model found with name '{model_name}'")
        except Exception as reg_err:
            logger.error(f"Error getting registered model: {reg_err}")
            import traceback
            traceback.print_exc()
        
        # FALLBACK: If no registered model or no accuracy found, get latest run from experiments
        if not registered_model_found or model_accuracy == 0.0:
            try:
                experiments = client.search_experiments()
                logger.info(f"Fallback: Found {len(experiments)} experiments")
                
                if experiments:
                    exp = experiments[0]
                    runs = client.search_runs(
                        experiment_ids=[exp.experiment_id],
                        max_results=1,
                        order_by=["start_time DESC"]
                    )
                    
                    if runs and len(runs) > 0:
                        run = runs[0]
                        run_name = run.info.run_name if hasattr(run.info, 'run_name') else None
                        # Only set to "latest" if we didn't get a version from registered model
                        if model_version == "N/A":
                            model_version = "latest"
                        
                        metrics = run.data.metrics if hasattr(run, 'data') and hasattr(run.data, 'metrics') else {}
                        logger.info(f"Fallback run metrics: {list(metrics.keys())}")
                        
                        # Get precision - ONLY if we don't have accuracy yet
                        if model_accuracy == 0.0:
                            if 'precision' in metrics:
                                model_accuracy = float(metrics['precision']) * 100
                                logger.info(f"Fallback: Found precision: {model_accuracy}%")
                            elif 'test_precision' in metrics:
                                model_accuracy = float(metrics['test_precision']) * 100
                            elif 'val_precision' in metrics:
                                model_accuracy = float(metrics['val_precision']) * 100
                            elif 'test_accuracy' in metrics:
                                model_accuracy = float(metrics['test_accuracy']) * 100
                            elif 'accuracy' in metrics:
                                model_accuracy = float(metrics['accuracy']) * 100
                            elif 'f1' in metrics:
                                model_accuracy = float(metrics['f1']) * 100
                            elif 'f1_score' in metrics:
                                model_accuracy = float(metrics['f1_score']) * 100
                            elif 'roc_auc' in metrics:
                                model_accuracy = float(metrics['roc_auc']) * 100
                        
                        # Update run_name if we got it from fallback
                        if not run_name and hasattr(run.info, 'run_name'):
                            run_name = run.info.run_name
                        
                        logger.info(f"Fallback: Found latest run: {run_name}, accuracy={model_accuracy}%, version={model_version}")
            except Exception as exp_err:
                logger.error(f"Error searching experiments: {exp_err}")
                import traceback
                traceback.print_exc()
            
    except Exception as e:
        logger.error(f"Error accessing MLflow: {e}")
        import traceback
        traceback.print_exc()
    
    # Ensure accuracy is valid
    if math.isnan(model_accuracy) or math.isinf(model_accuracy) or model_accuracy < 0:
        model_accuracy = 0.0
    if model_accuracy > 100:
        model_accuracy = 100.0
    
    # Format display name
    display_name = model_name
    if run_name:
        display_name = run_name.replace('-', ' ').title()
        logger.info(f"Using display name: {display_name}")
    
    logger.info(f"Returning model health: name={display_name}, version={model_version}, accuracy={model_accuracy}%")
    
    return {
        'name': display_name,
        'version': model_version,
        'accuracy': model_accuracy,
        'run_name': run_name
    }

def _get_model_health():
    """Get model health - wrapper with cache clearing on demand"""
    # Clear cache if needed (for testing)
    if hasattr(_get_model_health_cached, 'cache_clear'):
        # Don't cache for now - always get fresh data
        pass
    return _get_model_health_impl()

def get_inference_health():
    """Check inference service health"""
    try:
        response = requests.get(f"{INFERENCE_SERVICE_URL}/health", timeout=5)
        if response.status_code == 200:
            return response.json()
        return {'status': 'unhealthy'}
    except:
        return {'status': 'unreachable'}

@app.route('/')
def index():
    """Dashboard home page"""
    return render_template('dashboard.html')

@app.route('/transactions')
def transactions():
    """Transactions page"""
    return render_template('transactions.html')

@app.route('/system-health')
def system_health():
    """System Health page"""
    try:
        inference_health = get_inference_health()
        model_health = _get_model_health()
        
        # Get real-time stats
        try:
            stats_response = requests.get(f"{INFERENCE_SERVICE_URL}/inference/stats", timeout=5)
            stats = stats_response.json() if stats_response.status_code == 200 else {}
        except:
            stats = {}
        
        return render_template('system_health.html', 
                             inference_health=inference_health,
                             model_health=model_health,
                             stats=stats)
    except Exception as e:
        logger.error(f"Error loading system health: {e}")
        return render_template('system_health.html', 
                             inference_health={'status': 'unknown'},
                             model_health={'name': 'Unknown', 'version': 'N/A', 'accuracy': 0.0},
                             stats={})

@app.route('/alerts')
def alerts():
    """Alerts page"""
    try:
        # Get flagged transactions (alerts)
        try:
            results_response = requests.get(f"{INFERENCE_SERVICE_URL}/inference/results", 
                                          params={'page': 1, 'per_page': 100}, timeout=5)
            results = []
            if results_response.status_code == 200:
                results_data = results_response.json()
                if results_data.get('status') == 'success':
                    all_results = results_data.get('results', [])
                    # Filter only flagged transactions
                    results = [r for r in all_results if _pick_first(r, ['fraud_prediction', 'is_fraud', 'fraud'], 0) in (1, '1', True, 'True', 'true')]
        except:
            results = []
        
        return render_template('alerts.html', alerts=results[:50])  # Show top 50 alerts
    except Exception as e:
        logger.error(f"Error loading alerts: {e}")
        return render_template('alerts.html', alerts=[])

@app.route('/settings')
def settings():
    """Settings page"""
    try:
        # Get current configuration
        model_health = _get_model_health()
        inference_health = get_inference_health()
        
        return render_template('settings.html',
                             model_health=model_health,
                             inference_health=inference_health)
    except Exception as e:
        logger.error(f"Error loading settings: {e}")
        return render_template('settings.html',
                             model_health={'name': 'Unknown', 'version': 'N/A', 'accuracy': 0.0},
                             inference_health={'status': 'unknown'})

@app.route('/api/data')
def api_data():
    """API endpoint for dashboard data - fetches real data from inference service"""
    try:
        # Try to get real data from inference service
        try:
            # Don't trigger inference here - continuous worker handles it
            # Just fetch the latest stats and results
            
            # Get inference stats (with longer timeout for first load)
            # Use parallel requests for better performance
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                stats_future = executor.submit(requests.get, f"{INFERENCE_SERVICE_URL}/inference/stats", timeout=15)
                results_future = executor.submit(requests.get, f"{INFERENCE_SERVICE_URL}/inference/results", 
                                                  params={'page': 1, 'per_page': 1000}, timeout=15)
                
                stats_response = stats_future.result()
                results_response = results_future.result()
            
            if stats_response.status_code == 200:
                stats = stats_response.json()
                transactions = []
                trends = None
                results = []
                total_from_results = 0
                if results_response.status_code == 200:
                    results_data = results_response.json()
                    if results_data.get('status') == 'success':
                        results = results_data.get('results', [])
                        total_from_results = results_data.get('total_records', len(results))
                        # Sort by timestamp descending to get latest first
                        transactions = _build_transactions(results)
                        trends = _build_trends(results)
                
                model_health = _get_model_health()
                
                # Build response with real data
                # Get ACTUAL total from stats (not limited to 1000)
                total_txns = int(stats.get('total_records', 0) or 0)
                # If stats show 0 or exactly 1000 (might be a limit/cache), use results total
                if total_from_results > 0:
                    if total_from_results > total_txns or total_txns == 1000:
                        total_txns = total_from_results
                elif total_txns == 0 and results:
                    total_txns = len(results)
                
                fraud_count = int(stats.get('fraud_detections', 0) or 0)
                fraud_rate = float(stats.get('fraud_rate', 0.0) or 0.0)
                approval_rate = round(100 - fraud_rate, 2)
                
                # Better drift detection: compare current fraud rate to expected baseline (e.g., 2-3%)
                # If fraud rate is significantly higher than baseline, show warning
                # Made less sensitive - only warn if fraud rate is > 2x baseline
                baseline_fraud_rate = 2.5  # Expected baseline fraud rate
                drift_threshold = 2.0  # 2.0x baseline = warning (less sensitive)
                drift_status = 'Normal'
                if fraud_rate > (baseline_fraud_rate * drift_threshold):
                    drift_status = 'Warning'
                elif fraud_rate > (baseline_fraud_rate * 3.0):
                    drift_status = 'Critical'
                
                # Get inference stats for presentation (enhanced)
                inference_stats = {
                    'avg_fraud_probability': stats.get('avg_fraud_probability', 0.0),
                    'avg_confidence': stats.get('avg_confidence', 0.0),
                    'model_version': stats.get('model_version'),
                    'model_source': stats.get('model_source'),
                    'timestamp': stats.get('timestamp') or datetime.now().isoformat()
                }
                
                # Add enhanced metrics if available
                enhanced_metrics = stats.get('enhanced_metrics', {})
                business_metrics = enhanced_metrics.get('business_metrics', {})
                operational_metrics = enhanced_metrics.get('operational_metrics', {})
                
                # Add business impact metrics
                if business_metrics:
                    inference_stats['business_impact'] = {
                        'fraud_prevented_value_usd': business_metrics.get('fraud_prevented_value_usd', 0),
                        'revenue_preserved_usd': business_metrics.get('revenue_preserved_usd', 0),
                        'estimated_roi_percent': business_metrics.get('estimated_roi_percent', 0),
                        'total_volume_usd': business_metrics.get('total_volume_usd', 0)
                    }
                
                # Add operational metrics
                if operational_metrics:
                    inference_stats['operational'] = {
                        'avg_latency_ms': operational_metrics.get('avg_latency_ms', 0),
                        'throughput_tps': operational_metrics.get('throughput_tps', 0),
                        'p95_latency_ms': operational_metrics.get('p95_latency_ms', 0)
                    }
                
                return jsonify({
                    'status': 'success',
                    'metrics': {
                        'total_transactions': total_txns,
                        'fraud_rate': round(fraud_rate, 2) if not math.isnan(fraud_rate) else 0.0,
                        'approval_rate': round(approval_rate, 2) if not math.isnan(approval_rate) else 0.0,
                        'active_alerts': fraud_count
                    },
                    'model_health': {
                        'name': model_health['name'],
                        'version': model_health['version'],
                        'accuracy': model_health['accuracy'] if not (isinstance(model_health['accuracy'], float) and math.isnan(model_health['accuracy'])) else 0.0,
                        'drift_status': drift_status,
                        'run_name': model_health.get('run_name')  # Include original run name
                    },
                    'transactions': transactions,
                    'trends': trends if trends else {
                        'labels': [],
                        'valid_transactions': [],
                        'fraud_attempts': []
                    },
                    'inference_stats': inference_stats
                }), 200
            else:
                # Fallback to default data if inference service is unavailable
                return jsonify({
                    'status': 'inference_unavailable',
                    'metrics': {
                        'total_transactions': 0,
                        'fraud_rate': 0.0,
                        'approval_rate': 0.0,
                        'active_alerts': 0
                    },
                    'model_health': {
                        'name': 'Unknown',
                        'version': 'N/A',
                        'accuracy': 0.0,
                        'drift_status': 'Unknown'
                    },
                    'transactions': [],
                    'trends': {
                        'labels': [],
                        'valid_transactions': [],
                        'fraud_attempts': []
                    }
                }), 200
        except Exception as e:
            logger.error(f"Error fetching data from inference service: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({
                'status': 'error',
                'error': str(e),
                'metrics': {
                    'total_transactions': 0,
                    'fraud_rate': 0.0,
                    'approval_rate': 0.0,
                    'active_alerts': 0
                },
                'model_health': {
                    'name': 'Unknown',
                    'version': 'N/A',
                    'accuracy': 0.0,
                    'drift_status': 'Unknown'
                },
                'transactions': [],
                'trends': {
                    'labels': [],
                    'valid_transactions': [],
                    'fraud_attempts': []
                }
            }), 500
    except Exception as e:
        logger.error(f"Unexpected error in api_data: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'status': 'error',
            'error': str(e),
            'metrics': {
                'total_transactions': 0,
                'fraud_rate': 0.0,
                'approval_rate': 0.0,
                'active_alerts': 0
            },
            'model_health': {
                'name': 'Unknown',
                'version': 'N/A',
                'accuracy': 0.0,
                'drift_status': 'Unknown'
            },
            'transactions': [],
            'trends': {
                'labels': [],
                'valid_transactions': [],
                'fraud_attempts': []
            }
        }), 500


@app.route('/api/stream')
def api_stream():
    """Server-Sent Events stream for per-transaction updates - OPTIMIZED FOR REAL-TIME."""
    interval_ms = int(request.args.get('interval_ms', '500'))  # 500ms for TRUE real-time
    interval_s = max(interval_ms / 1000.0, 0.3)  # Minimum 0.3 second for real-time
    last_timestamp = None  # Track last transaction timestamp to detect new ones

    def generate():
        yield "retry: 2000\n\n"
        last_timestamp = None  # Track last transaction timestamp to detect new ones
        while True:
            try:
                # Use parallel requests for better performance
                with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                    stats_future = executor.submit(requests.get, f"{INFERENCE_SERVICE_URL}/inference/stats", timeout=3)
                    # Get latest transactions (sorted by newest first)
                    results_future = executor.submit(requests.get, 
                                                    f"{INFERENCE_SERVICE_URL}/inference/results?page=1&per_page=10",
                                                    timeout=3)
                    
                    stats_response = stats_future.result()
                    results_response = results_future.result()

                stats = {}
                if stats_response.status_code == 200:
                    stats = stats_response.json()

                results = []
                if results_response.status_code == 200:
                    results_data = results_response.json()
                    if results_data.get('status') == 'success':
                        results = results_data.get('results', [])

                # Build transactions (already sorted newest first)
                transactions = _build_transactions(results)
                # ALWAYS send the latest transaction if available - ensure real-time feed
                transaction = None
                if transactions:
                    # Send the most recent transaction every cycle to ensure feed is live
                    transaction = transactions[0]
                    latest_ts_str = transaction.get('timestamp')
                    if latest_ts_str:
                        try:
                            latest_ts = datetime.fromisoformat(latest_ts_str.replace('Z', '+00:00'))
                            if last_timestamp is None or latest_ts > last_timestamp:
                                last_timestamp = latest_ts
                        except:
                            last_timestamp = datetime.now()
                    else:
                        last_timestamp = datetime.now()
                else:
                    # No transactions yet, but still send metrics update
                    pass

                # Get actual total (not limited to 1000)
                total_txns = int(stats.get('total_records', 0) or 0)
                # Get real total from results pagination if available
                if results_response.status_code == 200:
                    try:
                        results_data = results_response.json()
                        if results_data.get('status') == 'success':
                            total_from_results = results_data.get('total_records', 0)
                            if total_from_results > total_txns or total_txns == 1000:
                                total_txns = total_from_results
                    except:
                        pass
                if total_txns == 0 and results:
                    total_txns = len(results)
                fraud_count = int(stats.get('fraud_detections', 0) or 0)
                fraud_rate = float(stats.get('fraud_rate', 0.0) or 0.0)
                approval_rate = round(100 - fraud_rate, 2)
                model_health = _get_model_health()
                
                # Better drift detection (less sensitive)
                baseline_fraud_rate = 2.5
                drift_threshold = 2.0  # Less sensitive
                drift_status = 'Normal'
                if fraud_rate > (baseline_fraud_rate * drift_threshold):
                    drift_status = 'Warning'
                elif fraud_rate > (baseline_fraud_rate * 3.0):
                    drift_status = 'Critical'

                payload = {
                    'metrics': {
                        'total_transactions': total_txns,
                        'fraud_rate': round(fraud_rate, 2) if not math.isnan(fraud_rate) else 0.0,
                        'approval_rate': round(approval_rate, 2) if not math.isnan(approval_rate) else 0.0,
                        'active_alerts': fraud_count
                    },
                    'model_health': {
                        'name': model_health['name'],
                        'version': model_health['version'],
                        'accuracy': model_health['accuracy'] if not (isinstance(model_health['accuracy'], float) and math.isnan(model_health['accuracy'])) else 0.0,
                        'drift_status': drift_status
                    },
                    'transaction': transaction,
                    'timestamp': datetime.now().isoformat()
                }
                
                # Clean NaN values before JSON serialization
                payload = clean_nan_values(payload)
                
                yield f"data: {json.dumps(payload)}\n\n"
                time.sleep(interval_s)
            except GeneratorExit:
                break
            except Exception:
                time.sleep(interval_s)

    return Response(stream_with_context(generate()), mimetype='text/event-stream')

@app.route('/api/health')
def api_health():
    """Health check endpoint"""
    inference_health = get_inference_health()
    return jsonify({
        'status': 'healthy',
        'inference_service': inference_health,
        'timestamp': datetime.now().isoformat()
    }), 200

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug)
