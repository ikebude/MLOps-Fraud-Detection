from flask import Flask, render_template, jsonify, request, stream_with_context, Response, session, redirect
import json
import os
import re
import secrets
import requests
from datetime import datetime, timedelta
import time
import math
from dotenv import load_dotenv
from functools import lru_cache, wraps
import concurrent.futures
from werkzeug.security import generate_password_hash, check_password_hash
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
_LEGACY_DEFAULT_SECRET = 'Moniguard-secret-key-change-in-production'
_DEV_MODE = os.getenv('MONIGUARD_DEV_MODE', 'false').lower() == 'true'


def _load_secret_key() -> str:
    key = os.getenv('SECRET_KEY', '')
    if key and key != _LEGACY_DEFAULT_SECRET and len(key) >= 32:
        return key
    if _DEV_MODE:
        logger.warning("SECRET_KEY missing/weak; MONIGUARD_DEV_MODE=true so using a random per-process key "
                       "(sessions will not survive a restart). Never use dev mode in deployment.")
        return secrets.token_hex(32)
    raise RuntimeError("SECRET_KEY must be set to a random value of at least 32 characters "
                       "(python -c \"import secrets; print(secrets.token_hex(32))\"). "
                       "For local development only, set MONIGUARD_DEV_MODE=true to generate one.")


app.secret_key = _load_secret_key()
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=os.getenv('MONIGUARD_SECURE_COOKIES', 'false').lower() == 'true',
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
)

# User accounts for role-based access (demo/development). Passwords come from the
# environment (plaintext, hashed at load, or a werkzeug hash); never from source.
_DEMO_ACCOUNTS = [  # (username, role, env var holding its password or werkzeug hash)
    ('Admin User', 'admin', 'MONIGUARD_ADMIN_PASSWORD'),
    ('Exec User', 'executive', 'MONIGUARD_EXEC_PASSWORD'),
    ('Ops User', 'operations', 'MONIGUARD_OPS_PASSWORD'),
    ('Analyst User', 'analyst', 'MONIGUARD_ANALYST_PASSWORD'),
]
_HASH_PREFIXES = ('scrypt:', 'pbkdf2:')


def _load_users() -> dict:
    users = {}
    for username, role, env_var in _DEMO_ACCOUNTS:
        secret = os.getenv(env_var, '')
        if not secret:
            continue  # account disabled when its password is not configured
        pw_hash = secret if secret.startswith(_HASH_PREFIXES) else generate_password_hash(secret)
        users[username] = {'password_hash': pw_hash, 'role': role}
    if not users:
        logger.warning("No MONIGUARD_*_PASSWORD set: no dashboard user can log in.")
    return users


USERS = _load_users()
_DUMMY_HASH = generate_password_hash(secrets.token_hex(16))  # equalises timing for unknown usernames


def _public_users() -> dict:
    """Safe view for templates: never includes password hashes."""
    return {name: {'role': info['role']} for name, info in USERS.items()}


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
MONIGUARD_BASE_PATH = os.getenv('MONIGUARD_BASE_PATH', '').rstrip('/')
MONIGUARD_REALTIME_INFERENCE = os.getenv('MONIGUARD_REALTIME_INFERENCE', 'true').lower() == 'true'
MONIGUARD_REALTIME_MODE = os.getenv('MONIGUARD_REALTIME_MODE', 'per_transaction').lower()
MONIGUARD_REALTIME_MAX_RECORDS = int(os.getenv('MONIGUARD_REALTIME_MAX_RECORDS', '1'))
if MONIGUARD_BASE_PATH and not MONIGUARD_BASE_PATH.startswith('/'):
    MONIGUARD_BASE_PATH = f'/{MONIGUARD_BASE_PATH}'

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
                    t.vendor_id as merchant, t.location, t.country, t.fraud_type
                FROM fraud_predictions fp
                LEFT JOIN transactions t ON fp.transaction_id = t.transaction_id
                WHERE fp.fraud_prediction = 1 OR fp.actual_fraud = 1
                ORDER BY fp.prediction_timestamp DESC
                LIMIT %s
            """, (limit,))
            
            columns = ['transaction_id', 'user_id', 'amount', 'fraud_probability',
                      'fraud_prediction', 'fraud_label', 'risk_level',
                      'prediction_timestamp', 'actual_fraud', 'merchant', 'location', 'country', 'fraud_type']
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
                    t.vendor_id as merchant, t.location, t.country, t.fraud_type
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
                      'prediction_timestamp', 'actual_fraud', 'merchant', 'location', 'country', 'fraud_type']
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
            """, (str(hours),))  # Parameterized query
            
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

# =============================================
# Helper Decorators & Logic
# =============================================

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return redirect(MONIGUARD_BASE_PATH + '/login')
        return f(*args, **kwargs)
    return decorated_function

def role_required(roles):
    if isinstance(roles, str):
        roles = [roles]
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'username' not in session:
                return redirect(MONIGUARD_BASE_PATH + '/login')
            if session.get('role') not in roles:
                # Redirect to their own dashboard
                role_dashboards = {
                    'admin': '/admin',
                    'executive': '/executive',
                    'operations': '/operations',
                    'analyst': '/'
                }
                return redirect(MONIGUARD_BASE_PATH + role_dashboards.get(session.get('role'), '/'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@app.before_request
def check_auth():
    """Global authentication check."""
    # List of open endpoints
    allowed_paths = ['/login', '/logout', '/health', '/api/health']
    
    # Check if request path is in allowed or starts with /static/
    current_path = request.path
    if MONIGUARD_BASE_PATH and current_path.startswith(MONIGUARD_BASE_PATH):
        current_path = current_path[len(MONIGUARD_BASE_PATH):]
        
    is_allowed = any(current_path == p for p in allowed_paths) or current_path.startswith('/static/')
    
    if not is_allowed and 'username' not in session:
        return redirect(MONIGUARD_BASE_PATH + '/login')

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
    return {'base_path': MONIGUARD_BASE_PATH}

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
        # IMPORTANT: time_str must be ISO 8601 so JavaScript's new Date() can parse it.
        # WAT = UTC+1, so we append '+01:00' to the ISO string.
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
                # ISO 8601 format with +01:00 offset — JS can parse this
                time_str = dt_wat.strftime('%Y-%m-%dT%H:%M:%S') + '+01:00'
                time_display = dt_wat.strftime('%Y-%m-%d %H:%M:%S WAT')
                sort_timestamp = dt.timestamp()
            except:
                time_str = str(timestamp)
                time_display = str(timestamp)
                sort_timestamp = 0
        else:
            dt = datetime.utcnow() + timedelta(hours=1)
            time_str = dt.strftime('%Y-%m-%dT%H:%M:%S') + '+01:00'
            time_display = dt.strftime('%Y-%m-%d %H:%M:%S WAT')
            sort_timestamp = dt.timestamp()
        
        # Get top features if available
        top_features = result.get('top_features', []) if isinstance(result, dict) else []
        
        # Generate explanations from available data when top_features is empty
        if not top_features and (fraud_prob > 0 or fraud_pred == 1):
            explanations = []
            
            # Use fraud_type if available (most descriptive)
            fraud_type = _pick_first(result, ['fraud_type'], None)
            if fraud_type and fraud_type != 'None':
                explanations.append({'feature': 'Fraud Type (Ground Truth)', 'contribution': 0.95, 'value': fraud_type.replace('_', ' ').title()})
            
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
            'time_display': time_display,
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
    # if hasattr(_get_model_health_cached, 'cache_clear'):
    #     # Don't cache for now - always get fresh data
    #     pass
    return _get_model_health_cached()

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
@login_required
def index():
    """Dashboard home page"""
    return render_template('dashboard.html', page='overview')

@app.route('/transactions')
@login_required
def transactions():
    """Transactions page"""
    return render_template('transactions.html', page='transactions')

@app.route('/system-health')
@role_required(['admin'])
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
@role_required(['analyst', 'operations', 'admin'])
def alerts():
    """Alerts page"""
    try:
        # Get flagged transactions (alerts) directly from database
        # Reusing get_live_fraud_feed which returns fraud_prediction=1 OR actual_fraud=1
        raw_results = get_live_fraud_feed(limit=100)
        
        # Process with standard builder to get top_features, consistent risk_scores, etc.
        alerts_data = _build_transactions(raw_results, sort_by='risk_score', sort_order='desc')
        
        return render_template('alerts.html', page='alerts', alerts=alerts_data, USERNAMES=sorted(USERS))
    except Exception as e:
        logger.error(f"Error loading alerts: {e}")
        return render_template('alerts.html', page='alerts', alerts=[], USERNAMES=sorted(USERS))

@app.route('/settings')
@login_required
def settings_page_view():
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
@login_required
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
@login_required
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
@login_required
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
                        drift_status = 'Normal'
                        if fraud_rate > (baseline_fraud_rate * 3.0):
                            drift_status = 'Critical'
                        elif fraud_rate > (baseline_fraud_rate * 2.0):
                            drift_status = 'Warning'

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
    # Redirect if already logged in
    if 'username' in session:
        role_dashboards = {
            'admin': '/admin',
            'executive': '/executive',
            'operations': '/operations',
            'analyst': '/'
        }
        return redirect(MONIGUARD_BASE_PATH + role_dashboards.get(session.get('role'), '/'))

    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        user = USERS.get(username)
        ok = check_password_hash(user['password_hash'] if user else _DUMMY_HASH, password)
        if user and ok:
            session.clear()  # prevent session fixation
            session['username'] = username
            session['role'] = user['role']  # ONLY from the stored user; any form 'role' is ignored
            role_map = {
                'admin': '/admin',
                'executive': '/executive',
                'operations': '/operations',
            }
            return redirect(MONIGUARD_BASE_PATH + role_map.get(session['role'], '/'))

        return render_template('login.html', error='Invalid credentials'), 401

    return render_template('login.html')

@app.route('/logout')
def logout():
    """Logout and clear session"""
    session.clear()
    return redirect(MONIGUARD_BASE_PATH + '/login')

@app.cli.command('hash-password')
def hash_password_cmd():
    """Print a werkzeug hash to paste into MONIGUARD_<ROLE>_PASSWORD, then restart the dashboard."""
    import getpass
    import click
    pw = getpass.getpass('New password: ')
    if len(pw) < 12 or pw != getpass.getpass('Repeat: '):
        raise click.ClickException('Passwords must match and be at least 12 characters.')
    click.echo(generate_password_hash(pw))


@app.route('/admin')
@role_required(['admin'])
def admin_dashboard():
    """Admin dashboard — system oversight"""
    return render_template('admin_dashboard.html', page='admin', USERS=_public_users())

@app.route('/executive')
@role_required(['executive', 'admin'])
def exec_dashboard():
    """Executive dashboard — high-level KPIs and trends"""
    return render_template('exec_dashboard.html', page='executive')

@app.route('/operations')
@role_required(['operations', 'admin'])
def ops_dashboard():
    """Operations dashboard — case list and actions"""
    return render_template('ops_dashboard.html', page='operations')



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
@role_required(['analyst', 'operations', 'admin'])
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
@login_required
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
@role_required(['admin'])
def api_system_logs():
    """Get recent integration simulation logs."""
    return jsonify(_integration_logs)

# =============================================
# Notification Settings API
# =============================================

@app.route('/api/notification-settings', methods=['GET', 'POST'])
@role_required(['admin'])
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






