from flask import Flask, render_template, jsonify, request, stream_with_context, Response, session, redirect
import json
import os
import requests
from datetime import datetime, timedelta
import time
import math
from dotenv import load_dotenv
from functools import lru_cache
import concurrent.futures
import logging
import threading

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    import mlflow
    MLFLOW_AVAILABLE = True
except ImportError:
    MLFLOW_AVAILABLE = False

try:
    import psycopg2
    from psycopg2 import pool
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False
    logger.warning("psycopg2 not available - database queries will fall back to Inference API")

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'fraudguard-secret-key-change-in-production')

# User accounts for role-based access (demo/development)
USERS = {
    'Analyst User': {'password': 'password', 'role': 'analyst'},
    'Ops User': {'password': 'password', 'role': 'operations'},
    'Exec User': {'password': 'password', 'role': 'executive'},
}

# In-memory alert store (for demo purposes — would be DB-backed in production)
_alerts_store = []
_integration_logs = []  # Simulated outbound API calls
_notification_settings = {
    'recipients': [],
    'threshold': 'all',
    'method': 'email',
    'schedule': 'business_hours'
}

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

# Database configuration for direct fraud_predictions access
DB_HOST = os.getenv('DB_HOST', os.getenv('POSTGRES_HOST', 'postgres'))
DB_PORT = int(os.getenv('DB_PORT', os.getenv('POSTGRES_PORT', '5432')))
DB_NAME = os.getenv('DB_NAME', os.getenv('POSTGRES_TRANSACTIONS_DB', 'transactions_db'))
DB_USER = os.getenv('DB_USER', os.getenv('POSTGRES_TRANSACTIONS_USER', 'fraud_producer'))
DB_PASSWORD = os.getenv('DB_PASSWORD', os.getenv('POSTGRES_TRANSACTIONS_PASSWORD', 'producer_password'))

# Database connection pool
db_pool = None
db_pool_lock = threading.Lock()

def _init_db_pool():
    """Initialize database connection pool."""
    global db_pool
    if not PSYCOPG2_AVAILABLE:
        logger.warning("psycopg2 not available, cannot create database pool")
        return None
    
    with db_pool_lock:
        if db_pool is not None:
            return db_pool
        try:
            db_pool = pool.ThreadedConnectionPool(
                minconn=2,
                maxconn=10,
                host=DB_HOST,
                port=DB_PORT,
                dbname=DB_NAME,
                user=DB_USER,
                password=DB_PASSWORD
            )
            logger.info(f"Database connection pool initialized: {DB_HOST}:{DB_PORT}/{DB_NAME}")
            return db_pool
        except Exception as e:
            logger.error(f"Failed to create database connection pool: {e}")
            return None

def _get_db_connection():
    """Get a connection from the pool."""
    global db_pool
    if db_pool is None:
        _init_db_pool()
    if db_pool is None:
        return None
    try:
        return db_pool.getconn()
    except Exception as e:
        logger.error(f"Failed to get database connection: {e}")
        return None

def _put_db_connection(conn):
    """Return a connection to the pool."""
    global db_pool
    if db_pool is not None and conn is not None:
        try:
            db_pool.putconn(conn)
        except Exception as e:
            logger.error(f"Failed to return connection to pool: {e}")

def get_live_fraud_feed(limit: int = 100):
    """
    Query fraud_predictions table for live fraud feed.
    Returns transactions where fraud_prediction=1 OR actual_fraud=1.
    """
    conn = _get_db_connection()
    if conn is None:
        logger.warning("No database connection, falling back to empty results")
        return []
    
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    fp.transaction_id, fp.user_id, fp.amount, fp.fraud_probability,
                    fp.fraud_prediction, fp.fraud_label, fp.risk_level,
                    fp.prediction_timestamp, fp.actual_fraud,
                    t.vendor_id as merchant, t.location, t.country
                FROM fraud_predictions fp
                LEFT JOIN transactions t ON fp.transaction_id = t.transaction_id
                WHERE fp.fraud_prediction = 1 OR fp.actual_fraud = 1
                ORDER BY fp.prediction_timestamp DESC
                LIMIT %s
            """, (limit,))
            
            columns = ['transaction_id', 'user_id', 'amount', 'fraud_probability',
                      'fraud_prediction', 'fraud_label', 'risk_level',
                      'prediction_timestamp', 'actual_fraud', 'merchant', 'location', 'country']
            rows = cur.fetchall()
            
            results = []
            for row in rows:
                record = dict(zip(columns, row))
                # Format timestamp
                if record.get('prediction_timestamp'):
                    record['timestamp'] = record['prediction_timestamp'].isoformat()
                else:
                    record['timestamp'] = datetime.now().isoformat()
                
                # Ensure merchant is not None
                if not record.get('merchant'):
                    record['merchant'] = 'Unknown Merchant'
                    
                results.append(record)
            
            logger.debug(f"Fetched {len(results)} fraud records from database")
            return results
    except Exception as e:
        logger.error(f"Error fetching live fraud feed: {e}")
        return []
    finally:
        _put_db_connection(conn)

def get_all_predictions_feed(limit: int = 100, offset: int = 0, search: str = None):
    """
    Query fraud_predictions table for ALL predictions (fraud and legitimate).
    Returns the most recent predictions, with optional search filter.
    """
    conn = _get_db_connection()
    if conn is None:
        logger.warning("No database connection, falling back to empty results")
        return []
    
    try:
        with conn.cursor() as cur:
            query = """
                SELECT 
                    fp.transaction_id, fp.user_id, fp.amount, fp.fraud_probability,
                    fp.fraud_prediction, fp.fraud_label, fp.risk_level,
                    fp.prediction_timestamp, fp.actual_fraud,
                    t.vendor_id as merchant, t.location, t.country
                FROM fraud_predictions fp
                LEFT JOIN transactions t ON fp.transaction_id = t.transaction_id
            """
            params = []
            
            if search:
                query += """
                    WHERE fp.transaction_id ILIKE %s 
                    OR fp.user_id ILIKE %s 
                    OR fp.fraud_label ILIKE %s
                """
                search_term = f"%{search}%"
                params.extend([search_term, search_term, search_term])
            
            query += " ORDER BY fp.prediction_timestamp DESC LIMIT %s OFFSET %s"
            params.extend([limit, offset])
            
            cur.execute(query, tuple(params))
            
            columns = ['transaction_id', 'user_id', 'amount', 'fraud_probability',
                      'fraud_prediction', 'fraud_label', 'risk_level',
                      'prediction_timestamp', 'actual_fraud', 'merchant', 'location', 'country']
            rows = cur.fetchall()
            
            results = []
            for row in rows:
                record = dict(zip(columns, row))
                # Format timestamp
                if record.get('prediction_timestamp'):
                    record['timestamp'] = record.get('prediction_timestamp').isoformat()
                else:
                    record['timestamp'] = datetime.now().isoformat()
                
                # Ensure merchant is not None
                if not record.get('merchant'):
                    record['merchant'] = 'Transaction'
                    
                results.append(record)
            
            logger.debug(f"Fetched {len(results)} prediction records from database")
            return results
    except Exception as e:
        logger.error(f"Error fetching predictions feed: {e}")
        return []
    finally:
        _put_db_connection(conn)

def get_total_predictions_count(search: str = None) -> int:
    """Get total count of predictions for pagination."""
    conn = _get_db_connection()
    if conn is None:
        return 0
    
    try:
        with conn.cursor() as cur:
            query = "SELECT COUNT(*) FROM fraud_predictions"
            params = []
            
            if search:
                query += """
                    WHERE transaction_id ILIKE %s 
                    OR user_id ILIKE %s 
                    OR fraud_label ILIKE %s
                """
                search_term = f"%{search}%"
                params.extend([search_term, search_term, search_term])
            
            cur.execute(query, tuple(params))
            return cur.fetchone()[0]
    except Exception as e:
        logger.error(f"Error counting predictions: {e}")
        return 0
    finally:
        _put_db_connection(conn)

def get_realtime_stats():
    """
    Get real-time statistics directly from fraud_predictions table.
    """
    conn = _get_db_connection()
    if conn is None:
        logger.warning("No database connection for stats")
        return None
    
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    COUNT(*) as total_transactions,
                    COALESCE(SUM(CASE WHEN fraud_prediction = 1 OR actual_fraud = 1 THEN 1 ELSE 0 END), 0) as fraud_detections,
                    COALESCE(ROUND(100.0 * SUM(CASE WHEN fraud_prediction = 1 OR actual_fraud = 1 THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2), 0) as fraud_rate,
                    COALESCE(AVG(fraud_probability), 0) as avg_fraud_probability
                FROM fraud_predictions
                WHERE prediction_timestamp >= NOW() - INTERVAL '24 hours'
            """)
            row = cur.fetchone()
            
            if row:
                stats = {
                    'total_records': int(row[0]) if row[0] else 0,
                    'fraud_detections': int(row[1]) if row[1] else 0,
                    'fraud_rate': float(row[2]) if row[2] else 0.0,
                    'avg_fraud_probability': float(row[3]) if row[3] else 0.0,
                    'timestamp': datetime.utcnow().isoformat() + 'Z'
                }
                logger.debug(f"Database stats: total={stats['total_records']}, fraud={stats['fraud_detections']}")
                return stats
            return None
    except Exception as e:
        logger.error(f"Error fetching real-time stats: {e}")
        return None
    finally:
        _put_db_connection(conn)

def get_trend_data(hours: int = 6):
    """
    Get trend data from fraud_predictions table grouped by 15-minute buckets.
    """
    conn = _get_db_connection()
    if conn is None:
        logger.warning("No database connection for trend data")
        return {'labels': [], 'valid_transactions': [], 'fraud_attempts': []}
    
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    DATE_TRUNC('hour', prediction_timestamp) + 
                    INTERVAL '15 min' * FLOOR(EXTRACT(MINUTE FROM prediction_timestamp) / 15) as time_bucket,
                    COUNT(*) as total,
                    COALESCE(SUM(CASE WHEN fraud_prediction = 1 OR actual_fraud = 1 THEN 1 ELSE 0 END), 0) as fraud_count
                FROM fraud_predictions
                WHERE prediction_timestamp >= NOW() - INTERVAL '%s hours'
                GROUP BY time_bucket
                ORDER BY time_bucket
            """ % hours)  # Using string formatting for interval since parameterized doesn't work well here
            
            rows = cur.fetchall()
            
            labels = []
            valid_transactions = []
            fraud_attempts = []
            
            for row in rows:
                time_bucket, total, fraud_count = row
                if time_bucket:
                    labels.append(time_bucket.strftime('%H:%M'))
                else:
                    labels.append('--:--')
                valid_transactions.append(int(total) - int(fraud_count))
                fraud_attempts.append(int(fraud_count))
            
            logger.debug(f"Trend data: {len(labels)} buckets over {hours} hours")
            return {
                'labels': labels,
                'valid_transactions': valid_transactions,
                'fraud_attempts': fraud_attempts
            }
    except Exception as e:
        logger.error(f"Error fetching trend data: {e}")
        return {'labels': [], 'valid_transactions': [], 'fraud_attempts': []}
    finally:
        _put_db_connection(conn)

# Initialize database pool on startup
if PSYCOPG2_AVAILABLE:
    _init_db_pool()

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
        fraud_prob_raw = _pick_first(result, ['fraud_probability', 'fraud_score', 'probability'], 0.0)
        confidence_raw = _pick_first(result, ['confidence', 'model_confidence'], 0.0)
        
        # Convert to native float (DB returns Decimal type which fails isinstance checks)
        try:
            fraud_prob = float(fraud_prob_raw) if fraud_prob_raw is not None else 0.0
        except (TypeError, ValueError):
            fraud_prob = 0.0
        try:
            confidence = float(confidence_raw) if confidence_raw is not None else 0.0
        except (TypeError, ValueError):
            confidence = 0.0
        
        # Calculate risk score (0-100)
        risk_score = int(fraud_prob * 100) if fraud_prob > 0 else int(confidence * 100)
        
        # Format timestamp - use WAT (West Africa Time, UTC+1)
        sort_timestamp = None
        if timestamp:
            try:
                if isinstance(timestamp, str):
                    # Try parsing ISO format
                    dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                else:
                    dt = timestamp
                # Convert to WAT (UTC+1) for Nigerian market

                if dt.tzinfo is None:
                    # Assume UTC, add 1 hour for WAT
                    dt_wat = dt + timedelta(hours=1)
                else:
                    dt_wat = dt + timedelta(hours=1)
                time_str = dt_wat.strftime('%Y-%m-%d %H:%M:%S WAT')
                sort_timestamp = dt.timestamp()
            except:
                time_str = str(timestamp)
                sort_timestamp = 0
        else:

            dt = datetime.utcnow() + timedelta(hours=1)
            time_str = dt.strftime('%Y-%m-%d %H:%M:%S WAT')
            sort_timestamp = dt.timestamp()
        
        # Get top features if available
        top_features = result.get('top_features', []) if isinstance(result, dict) else []
        
        # Generate explanations from available data when top_features is empty
        if not top_features and fraud_prob > 0:
            explanations = []
            # Amount-based explanation
            amt = float(amount) if amount else 0.0
            if amt > 100000:
                explanations.append({'feature': 'High Transaction Amount', 'contribution': round(fraud_prob * 0.35, 3), 'value': f'₦{amt:,.2f}'})
            elif amt > 50000:
                explanations.append({'feature': 'Elevated Amount', 'contribution': round(fraud_prob * 0.25, 3), 'value': f'₦{amt:,.2f}'})
            # Fraud probability explanation
            if fraud_prob >= 0.8:
                explanations.append({'feature': 'Very High Fraud Score', 'contribution': round(fraud_prob * 0.4, 3), 'value': f'{fraud_prob:.2%}'})
            elif fraud_prob >= 0.5:
                explanations.append({'feature': 'Elevated Fraud Score', 'contribution': round(fraud_prob * 0.3, 3), 'value': f'{fraud_prob:.2%}'})
            elif fraud_prob >= 0.2:
                explanations.append({'feature': 'Moderate Fraud Score', 'contribution': round(fraud_prob * 0.2, 3), 'value': f'{fraud_prob:.2%}'})
            # Risk level explanation
            risk_lvl = _pick_first(result, ['risk_level'], None)
            if risk_lvl and risk_lvl in ('CRITICAL', 'HIGH'):
                explanations.append({'feature': f'{risk_lvl} Risk Classification', 'contribution': round(fraud_prob * 0.25, 3), 'value': risk_lvl})
            # Actual fraud flag
            actual = _pick_first(result, ['actual_fraud', 'is_fraud'], None)
            if actual and int(actual) == 1:
                explanations.append({'feature': 'Confirmed Fraud', 'contribution': 1.0, 'value': 'Yes'})
            top_features = explanations
        
        # Get merchant/vendor info - Prioritize the joined 'merchant' column
        merchant = _pick_first(result, ['merchant', 'vendor_id', 'vendor', 'vendor_name', 'merchant_name'], 'Transaction')
        
        # Get location info
        location = _pick_first(result, ['location', 'country', 'geo_location'], 'Unknown')
        # Get risk level from database (populated by inference service)
        risk_level = _pick_first(result, ['risk_level'], None)
        # If not available from DB, derive from fraud_probability
        # ALIGNED with inference service main.py (_get_risk_level) thresholds
        if not risk_level:
            if isinstance(fraud_prob, (int, float)):
                if fraud_prob >= 0.8:
                    risk_level = 'CRITICAL'
                elif fraud_prob >= 0.6:
                    risk_level = 'HIGH'
                elif fraud_prob >= 0.4:
                    risk_level = 'MEDIUM'
                elif fraud_prob >= 0.2:
                    risk_level = 'LOW'
                else:
                    risk_level = 'MINIMAL'
            else:
                risk_level = 'UNKNOWN'
        
        transactions.append({
            'id': txn_id,
            'user_id': user_id,
            'time': time_str,
            'timestamp': time_str,
            '_sort_timestamp': sort_timestamp,
            'merchant': merchant,
            'location': location,
            'amount': float(amount) if amount else 0.0,
            'risk_score': risk_score,
            '_sort_risk_score': risk_score,
            'fraud_probability': fraud_prob,
            '_sort_fraud_probability': fraud_prob,
            'risk_level': risk_level,
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
        actual_fraud = _pick_first(txn, ['actual_fraud'], 0)
        
        if str(fraud_pred) in ('1', 'True', 'true') or str(actual_fraud) in ('1', 'True', 'true'):
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
    
    # Check for local model if MLflow failed or returned nothing
    if (model_version == "N/A" or model_version is None):
        local_model_path = '/app/models/fraud_detection_model.pkl'
        # Also check local development path
        if not os.path.exists(local_model_path):
             local_model_path = os.path.join(os.getcwd(), 'models', 'fraud_detection_model.pkl')
             
        if os.path.exists(local_model_path):
            try:
                mtime = os.path.getmtime(local_model_path)
                dt = datetime.fromtimestamp(mtime)
                model_version = "Local"
                if not run_name:
                    run_name = f"Local Model ({dt.strftime('%Y-%m-%d %H:%M')})"
                logger.info(f"Found local model at {local_model_path}")
            except Exception as e:
                logger.error(f"Error checking local model: {e}")

    # Ensure accuracy is valid
    if math.isnan(model_accuracy) or math.isinf(model_accuracy) or model_accuracy < 0:
        model_accuracy = 0.0
    if model_accuracy > 100:
        model_accuracy = 100.0
    
    # Format display name
    display_name = model_name
    if run_name:
        display_name = run_name.replace('-', ' ').title() if isinstance(run_name, str) else str(run_name)
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
    return render_template('dashboard.html', page='overview')

@app.route('/transactions')
def transactions():
    """Transactions page"""
    return render_template('transactions.html', page='transactions')

@app.route('/system-health')
def system_health():
    """System Health page"""
    try:
        import sys
        import platform
        
        inference_health = get_inference_health()
        model_health = _get_model_health()
        
        # Get real-time stats directly from DB
        stats = get_realtime_stats()
        
        # If DB stats empty, fallback or initialize defaults
        if not stats:
            stats = {
                'total_records': 0, 'fraud_detections': 0, 
                'fraud_rate': 0.0, 'active_alerts': 0
            }
        
        # Dynamic system environment
        sys_env = {
            'os': platform.system() + ' • Docker Container',
            'python_version': platform.python_version(),
            'threads': threading.active_count(),
            'db_available': PSYCOPG2_AVAILABLE and db_pool is not None,
        }
        
        return render_template('system_health.html', 
                             page='system_health',
                             inference_health=inference_health,
                             model_health=model_health,
                             stats=stats,
                             sys_env=sys_env)
    except Exception as e:
        logger.error(f"Error loading system health: {e}")
        return render_template('system_health.html', 
                             page='system_health',
                             inference_health={'status': 'unknown'},
                             model_health={'name': 'Unknown', 'version': 'N/A', 'accuracy': 0.0},
                             stats={},
                             sys_env={'os': 'Unknown', 'python_version': 'N/A', 'threads': 0, 'db_available': False})

@app.route('/alerts')
def alerts():
    """Alerts page"""
    try:
        # Get flagged transactions (alerts) directly from database
        # Reusing get_live_fraud_feed which returns fraud_prediction=1 OR actual_fraud=1
        raw_results = get_live_fraud_feed(limit=100)
        
        # Process with standard builder to get top_features, consistent risk_scores, etc.
        alerts_data = _build_transactions(raw_results, sort_by='risk_score', sort_order='desc')
        
        return render_template('alerts.html', page='alerts', alerts=alerts_data, USERS=USERS)
    except Exception as e:
        logger.error(f"Error loading alerts: {e}")
        return render_template('alerts.html', page='alerts', alerts=[], USERS=USERS)

@app.route('/settings')
def settings():
    """Settings page"""
    try:
        # Get current configuration
        model_health = _get_model_health()
        inference_health = get_inference_health()
        db_available = PSYCOPG2_AVAILABLE and db_pool is not None
        
        return render_template('settings.html',
                             page='settings',
                             model_health=model_health,
                             inference_health=inference_health,
                             db_available=db_available)
    except Exception as e:
        logger.error(f"Error loading settings: {e}")
        return render_template('settings.html',
                             page='settings',
                             model_health={'name': 'Unknown', 'version': 'N/A', 'accuracy': 0.0},
                             inference_health={'status': 'unknown'},
                             db_available=False)

@app.route('/api/transactions')
def api_transactions():
    """
    API endpoint for paginated transactions.
    Supports search, limit, and offset.
    """
    try:
        limit = int(request.args.get('limit', 50))
        offset = int(request.args.get('offset', 0))
        search = request.args.get('search', '').strip() or None
        
        # Get raw data and total count
        raw_results = get_all_predictions_feed(limit=limit, offset=offset, search=search)
        total_count = get_total_predictions_count(search=search)
        
        # Process with standard builder
        transactions_data = _build_transactions(raw_results, sort_by='timestamp', sort_order='desc')
        
        return jsonify({
            'status': 'success',
            'transactions': transactions_data,
            'pagination': {
                'total': total_count,
                'limit': limit,
                'offset': offset,
                'page': (offset // limit) + 1 if limit > 0 else 1,
                'pages': (total_count + limit - 1) // limit if limit > 0 else 1
            }
        })
    except Exception as e:
        logger.error(f"Error serving transactions API: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e),
            'transactions': [],
            'pagination': {
                'total': 0,
                'limit': 50,
                'offset': 0,
                'page': 1,
                'pages': 1
            }
        }), 500

@app.route('/api/data')
def api_data():
    """API endpoint for dashboard data - fetches REAL-TIME data from fraud_predictions database."""
    try:
        # PRIMARY: Get real-time data directly from database
        db_stats = get_realtime_stats()
        db_has_data = db_stats is not None and db_stats.get('total_records', 0) > 0
        
        if db_has_data:
            # Use direct database queries for real-time data
            logger.info("Using direct database queries for dashboard data")
            
            # Get all predictions for the transaction feed (not just fraud)
            # USER REQUEST: "The live transaction feed is supposed to show records where, the fraud_predictions and the actual fraud are 1"
            results = get_live_fraud_feed(limit=20)
            transactions = _build_transactions(results)
            
            # Get trend data from database
            trends = get_trend_data(hours=6)
            
            # Get model health from MLflow
            model_health = _get_model_health()
            
            # Extract stats from database query
            total_txns = db_stats.get('total_records', 0)
            fraud_count = db_stats.get('fraud_detections', 0)
            fraud_rate = db_stats.get('fraud_rate', 0.0)
            approval_rate = round(100 - fraud_rate, 2) if fraud_rate else 100.0
            avg_fraud_prob = db_stats.get('avg_fraud_probability', 0.0)
            
            # Drift detection based on fraud rate (check Critical FIRST, then Warning)
            baseline_fraud_rate = 2.5
            drift_status = 'Normal'
            if fraud_rate > (baseline_fraud_rate * 3.0):
                drift_status = 'Critical'
            elif fraud_rate > (baseline_fraud_rate * 2.0):
                drift_status = 'Warning'
            
            # Build inference stats - include total_records and fraud_detections for UI
            inference_stats = {
                'avg_fraud_probability': avg_fraud_prob,
                'avg_confidence': 1.0 - avg_fraud_prob if avg_fraud_prob else 0.0,
                'total_records': total_txns,
                'fraud_detections': fraud_count,
                'model_version': model_health.get('version'),
                'model_source': 'database',
                'timestamp': db_stats.get('timestamp', datetime.now().isoformat())
            }
            
            return jsonify({
                'status': 'success',
                'source': 'database',  # Indicate data source
                'metrics': {
                    'total_transactions': total_txns,
                    'fraud_rate': round(fraud_rate, 2) if not math.isnan(fraud_rate) else 0.0,
                    'approval_rate': round(approval_rate, 2) if not math.isnan(approval_rate) else 100.0,
                    'active_alerts': fraud_count
                },
                'model_health': {
                    'name': model_health['name'],
                    'version': model_health['version'],
                    'accuracy': model_health['accuracy'] if not (isinstance(model_health['accuracy'], float) and math.isnan(model_health['accuracy'])) else 0.0,
                    'drift_status': drift_status,
                    'run_name': model_health.get('run_name')
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
            # FALLBACK: Try inference service API if database is empty or unavailable
            logger.info("Database empty or unavailable, falling back to Inference API")
            try:
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
                    if results_response.status_code == 200:
                        results_data = results_response.json()
                        if results_data.get('status') == 'success':
                            results = results_data.get('results', [])
                            transactions = _build_transactions(results)
                            trends = _build_trends(results)
                    
                    model_health = _get_model_health()
                    total_txns = int(stats.get('total_records', 0) or 0)
                    fraud_count = int(stats.get('fraud_detections', 0) or 0)
                    fraud_rate = float(stats.get('fraud_rate', 0.0) or 0.0)
                    approval_rate = round(100 - fraud_rate, 2)
                    
                    baseline_fraud_rate = 2.5
                    drift_status = 'Normal'
                    if fraud_rate > (baseline_fraud_rate * 3.0):
                        drift_status = 'Critical'
                    elif fraud_rate > (baseline_fraud_rate * 2.0):
                        drift_status = 'Warning'
                    
                    return jsonify({
                        'status': 'success',
                        'source': 'inference_api',  # Indicate data source
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
                            'run_name': model_health.get('run_name')
                        },
                        'transactions': transactions,
                        'trends': trends if trends else {
                            'labels': [],
                            'valid_transactions': [],
                            'fraud_attempts': []
                        },
                        'inference_stats': stats
                    }), 200
            except Exception as api_e:
                logger.warning(f"Inference API fallback also failed: {api_e}")
            
            # Final fallback: return empty data
            return jsonify({
                'status': 'no_data',
                'source': 'none',
                'metrics': {
                    'total_transactions': 0,
                    'fraud_rate': 0.0,
                    'approval_rate': 100.0,
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
    """Server-Sent Events stream for REAL-TIME database updates."""
    interval_ms = int(request.args.get('interval_ms', '250'))  # 250ms for TRUE real-time
    interval_s = max(interval_ms / 1000.0, 0.2)  # Minimum 0.2 second for real-time

    def generate():
        yield "retry: 2000\n\n"
        last_txn_id = None  # Track last transaction ID to detect new ones
        while True:
            try:
                # PRIMARY: Get data directly from database
                db_stats = get_realtime_stats()
                
                if db_stats is not None:
                    # Get latest transaction from database
                    # USER REQUEST: Live feed should only show fraud/potential fraud
                    results = get_live_fraud_feed(limit=10)
                    transactions = _build_transactions(results)
                    
                    # Get the most recent transaction
                    transaction = None
                    if transactions:
                        transaction = transactions[0]
                        current_txn_id = transaction.get('id')
                        # Only update if it's a new transaction
                        if current_txn_id != last_txn_id:
                            last_txn_id = current_txn_id
                    
                    # Get stats from database
                    total_txns = db_stats.get('total_records', 0)
                    fraud_count = db_stats.get('fraud_detections', 0)
                    fraud_rate = float(db_stats.get('fraud_rate', 0.0) or 0.0)
                    approval_rate = round(100 - fraud_rate, 2) if fraud_rate else 100.0
                    
                    model_health = _get_model_health()
                    
                    # Drift detection (check Critical FIRST, then Warning)
                    baseline_fraud_rate = 2.5
                    drift_status = 'Normal'
                    if fraud_rate > (baseline_fraud_rate * 3.0):
                        drift_status = 'Critical'
                    elif fraud_rate > (baseline_fraud_rate * 2.0):
                        drift_status = 'Warning'
                    
                    payload = {
                        'source': 'database',
                        'metrics': {
                            'total_transactions': total_txns,
                            'fraud_rate': round(fraud_rate, 2) if not math.isnan(fraud_rate) else 0.0,
                            'approval_rate': round(approval_rate, 2) if not math.isnan(approval_rate) else 100.0,
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
                else:
                    # FALLBACK: Use Inference API
                    try:
                        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                            stats_future = executor.submit(requests.get, f"{INFERENCE_SERVICE_URL}/inference/stats", timeout=3)
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

                        transactions = _build_transactions(results)
                        transaction = transactions[0] if transactions else None
                        
                        total_txns = int(stats.get('total_records', 0) or 0)
                        fraud_count = int(stats.get('fraud_detections', 0) or 0)
                        fraud_rate = float(stats.get('fraud_rate', 0.0) or 0.0)
                        approval_rate = round(100 - fraud_rate, 2)
                        model_health = _get_model_health()
                        
                        baseline_fraud_rate = 2.5
                        drift_threshold = 2.0
                        drift_status = 'Normal'
                        if fraud_rate > (baseline_fraud_rate * drift_threshold):
                            drift_status = 'Warning'
                        elif fraud_rate > (baseline_fraud_rate * 3.0):
                            drift_status = 'Critical'

                        payload = {
                            'source': 'inference_api',
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
                    except Exception:
                        # No data available
                        payload = {
                            'source': 'none',
                            'metrics': {
                                'total_transactions': 0,
                                'fraud_rate': 0.0,
                                'approval_rate': 100.0,
                                'active_alerts': 0
                            },
                            'model_health': {
                                'name': 'Unknown',
                                'version': 'N/A',
                                'accuracy': 0.0,
                                'drift_status': 'Unknown'
                            },
                            'transaction': None,
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

# =============================================
# Authentication & Role-Based Routes
# =============================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page with role selection"""
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        role = request.form.get('role', '')
        
        user = USERS.get(username)
        if user and user['password'] == password:
            session['username'] = username
            session['role'] = role or user.get('role', 'analyst')
            # Redirect based on role
            role_map = {
                'admin': '/admin',
                'executive': '/executive',
                'operations': '/operations',
            }
            target = role_map.get(session['role'], '/')
            return redirect(FRAUDGUARD_BASE_PATH + target)
        
        return render_template('login.html', error='Invalid credentials')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    """Logout and clear session"""
    session.clear()
    return redirect(FRAUDGUARD_BASE_PATH + '/login')

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """Password reset page"""
    message = None
    if request.method == 'POST':
        name = request.form.get('name', '')
        new_password = request.form.get('new_password', '')
        if name in USERS and new_password:
            USERS[name]['password'] = new_password
            message = 'Password updated successfully. You can now login.'
        else:
            message = 'User not found or invalid password.'
    return render_template('password_reset.html', message=message)



@app.route('/executive')
def exec_dashboard():
    """Executive dashboard — high-level KPIs and trends"""
    return render_template('exec_dashboard.html', page='executive')

@app.route('/operations')
def ops_dashboard():
    """Operations dashboard — case list and actions"""
    return render_template('ops_dashboard.html', page='operations')

@app.route('/settings')
def settings():
    """User settings page"""
    return render_template('settings.html', page='settings')

# =============================================
# Alerts API (supports the enhanced alerts page)
# =============================================

def _build_alert_from_transaction(txn, idx):
    """Convert a _build_transactions() item into the alert format the UI expects."""
    fraud_prob = txn.get('fraud_probability', 0.0)
    risk_score = txn.get('risk_score', 0)
    
    # Derive severity from risk_score — ALIGNED with inference service thresholds
    if risk_score >= 80:
        severity = 'critical'
    elif risk_score >= 60:
        severity = 'high'
    elif risk_score >= 40:
        severity = 'medium'
    else:
        severity = 'low'
    
    # Build a reason string from top_features
    top_features = txn.get('top_features', [])
    if top_features:
        reason = top_features[0].get('feature', 'Suspicious transaction pattern')
    else:
        reason = 'Suspicious transaction pattern detected by model'
    
    # Check if we already have in-memory state for this alert
    alert_id = f"ALT-{str(txn.get('id', idx)).replace(' ', '')[:12]}"
    existing = next((a for a in _alerts_store if a['id'] == alert_id), None)
    
    alert = {
        'id': alert_id,
        'severity': severity,
        'reason': reason,
        'risk_score': risk_score,
        'fraud_probability': fraud_prob,
        'status': existing['status'] if existing else 'New',
        'assigned_to': existing['assigned_to'] if existing else None,
        'created_at': txn.get('timestamp', datetime.now().isoformat()),
        'transaction': {
            'transaction_id': txn.get('id', 'Unknown'),
            'customer_id': txn.get('user_id', 'Unknown'),
            'amount': txn.get('amount', 0.0),
            'merchant': txn.get('merchant', 'Unknown'),
            'channel': 'Online',
            'location': txn.get('location', 'Unknown'),
            'device_id': 'N/A',
            'previous_login': None
        }
    }
    return alert

@app.route('/api/alerts', methods=['GET'])
def api_alerts_list():
    """Get alerts with optional filters."""
    try:
        # Get flagged transactions from DB
        raw_results = get_live_fraud_feed(limit=200)
        transactions = _build_transactions(raw_results, sort_by='risk_score', sort_order='desc')
        
        # Convert to alert format
        alerts_list = [_build_alert_from_transaction(txn, i) for i, txn in enumerate(transactions)]
        
        # Apply filters
        severity = request.args.get('severity', '')
        status = request.args.get('status', '')
        fraud_type = request.args.get('fraud_type', '')
        start_date = request.args.get('start_date', '')
        end_date = request.args.get('end_date', '')
        min_risk = request.args.get('min_risk', '')
        max_risk = request.args.get('max_risk', '')
        assigned = request.args.get('assigned', '')
        
        if severity:
            alerts_list = [a for a in alerts_list if a['severity'] == severity]
        if status:
            alerts_list = [a for a in alerts_list if a['status'] == status]
        if min_risk:
            alerts_list = [a for a in alerts_list if a['risk_score'] >= int(min_risk)]
        if max_risk:
            alerts_list = [a for a in alerts_list if a['risk_score'] <= int(max_risk)]
        if assigned:
            alerts_list = [a for a in alerts_list if a.get('assigned_to') == assigned]
        
        return jsonify(alerts_list)
    except Exception as e:
        logger.error(f"Error in alerts API: {e}")
        return jsonify([]), 500

@app.route('/api/alerts/<alert_id>', methods=['GET', 'POST'])
def api_alert_detail(alert_id):
    """Get or update a single alert."""
    if request.method == 'GET':
        # Find alert by rebuilding from DB
        try:
            raw_results = get_live_fraud_feed(limit=200)
            transactions = _build_transactions(raw_results, sort_by='risk_score', sort_order='desc')
            alerts_list = [_build_alert_from_transaction(txn, i) for i, txn in enumerate(transactions)]
            alert = next((a for a in alerts_list if a['id'] == alert_id), None)
            if alert:
                return jsonify(alert)
            return jsonify({'error': 'Alert not found'}), 404
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    elif request.method == 'POST':
        # Update alert status or assignment
        data = request.get_json(silent=True) or {}
        existing = next((a for a in _alerts_store if a['id'] == alert_id), None)
        if not existing:
            existing = {'id': alert_id, 'status': 'New', 'assigned_to': None}
            _alerts_store.append(existing)
        
        if 'status' in data:
            old_status = existing['status']
            new_status = data['status']
            existing['status'] = new_status
            
            # Simulate Real-World Integrations based on action
            if new_status == 'Confirmed Fraud':
                _integration_logs.insert(0, {
                    'timestamp': datetime.now().strftime('%H:%M:%S'),
                    'system': 'CORE_BANKING',
                    'action': 'POST /v1/cards/block',
                    'payload': f"{{'txn_id': '{alert_id}', 'reason': 'fraud_confirmed'}}",
                    'status': '200 OK'
                })
                _integration_logs.insert(0, {
                    'timestamp': datetime.now().strftime('%H:%M:%S'),
                    'system': 'CRM_Service',
                    'action': 'POST /v1/customers/flag',
                    'payload': f"{{'customer_id': 'CUST-{alert_id[-4:]}', 'risk_level': 'CRITICAL'}}",
                    'status': '201 Created'
                })
            elif new_status == 'False Positive':
                _integration_logs.insert(0, {
                    'timestamp': datetime.now().strftime('%H:%M:%S'),
                    'system': 'ML_PIPELINE',
                    'action': 'POST /v1/feedback/train',
                    'payload': f"{{'id': '{alert_id}', 'label': 0}}",
                    'status': '202 Accepted'
                })
            elif new_status == 'Escalated':
                _integration_logs.insert(0, {
                    'timestamp': datetime.now().strftime('%H:%M:%S'),
                    'system': 'JIRA_TICKET',
                    'action': 'POST /v1/issue/create',
                    'payload': f"{{'summary': 'Investigate {alert_id}', 'priority': 'High'}}",
                    'status': '201 Created'
                })

        if 'assigned_to' in data:
            existing['assigned_to'] = data['assigned_to']
            _integration_logs.insert(0, {
                'timestamp': datetime.now().strftime('%H:%M:%S'),
                'system': 'NOTIFIER',
                'action': 'POST /slack/send',
                'payload': f"{{'user': '{data['assigned_to']}', 'message': 'New case assigned: {alert_id}'}}",
                'status': '200 OK'
            })
        
        # Keep logs capped at 50 to prevent memory growth
        if len(_integration_logs) > 50:
            _integration_logs.pop()

        return jsonify({'success': True, 'alert': existing})

@app.route('/api/system/logs', methods=['GET'])
def api_system_logs():
    """Get recent integration simulation logs."""
    return jsonify(_integration_logs)

# =============================================
# Notification Settings API
# =============================================

@app.route('/api/notification-settings', methods=['GET', 'POST'])
def api_notification_settings():
    """Get or update notification settings."""
    global _notification_settings
    
    if request.method == 'GET':
        return jsonify(_notification_settings)
    
    elif request.method == 'POST':
        data = request.get_json(silent=True) or {}
        if 'recipients' in data:
            _notification_settings['recipients'] = data['recipients']
        if 'threshold' in data:
            _notification_settings['threshold'] = data['threshold']
        if 'method' in data:
            _notification_settings['method'] = data['method']
        if 'schedule' in data:
            _notification_settings['schedule'] = data['schedule']
        return jsonify({'success': True, 'settings': _notification_settings})

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug)
