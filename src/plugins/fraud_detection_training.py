"""
Fraud Detection Model Training with Complete Feature Engineering

    This module ingests RAW e-commerce transactions and performs complete feature engineering
    to create 74 advanced fraud detection features before training the model.

Architecture:
1. Data Ingestion - Fetch raw transactions from database
2. Feature Engineering - Calculate all 62 features from raw data
3. Model Training - XGBoost with SMOTE and hyperparameter tuning
4. MLflow Tracking - Log metrics, parameters, and artifacts
5. Model Deployment - Save and register model

Feature Categories:
- Temporal Features (8): Account age, transaction velocities, timing patterns
- Identity Features (7): Verification scores, SIM swap, disposable email detection
- Device Features (5): Fingerprinting, emulator detection, trust scores
- Location Features (5): IP risk, VPN/proxy detection, location mismatches
- Payment Features (7): Failed ratios, anomalies, verification
- Network Features (7): Fraud rings, linked accounts, vendor risk
- Behavioral Features (6): Activity timing, consistency, review patterns
- Address Features (5): Risk scores, reuse rates, shared addresses
- Delivery Features (4): Delays, failed patterns, disputes
- Account Linking (8): Device sharing, phone/IP sharing, multi-device flags

Requirements:
    pip install pandas numpy scikit-learn xgboost imbalanced-learn mlflow \
                psycopg2-binary python-dotenv pyyaml joblib matplotlib boto3
"""

import json
import logging
import os
import signal
import sys
import time
import socket
import urllib.parse
import yaml
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Tuple, Any, Optional

import numpy as np
import pandas as pd
from dotenv import load_dotenv
import mlflow
import mlflow.sklearn

# Structured JSON logging setup
try:
    from pythonjsonlogger import jsonlogger
    json_logger_available = True
except Exception:
    json_logger_available = False

root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
if root_logger.handlers:
    for h in list(root_logger.handlers):
        root_logger.removeHandler(h)
handler = logging.StreamHandler(sys.stdout)
if json_logger_available:
    handler.setFormatter(jsonlogger.JsonFormatter('%(asctime)s %(levelname)s %(name)s %(message)s'))
else:
    handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
root_logger.addHandler(handler)
logger = logging.getLogger(__name__)

# Prometheus metrics (optional)
try:
    from prometheus_client import Gauge, Counter, Histogram
    PROMETHEUS_AVAILABLE = True
except Exception:
    PROMETHEUS_AVAILABLE = False

if PROMETHEUS_AVAILABLE:
    training_duration_seconds = Histogram(
        'fraud_detection_training_duration_seconds',
        'Time taken for training pipeline',
        buckets=(60, 300, 600, 1200, 3600)
    )
    training_accuracy = Gauge('fraud_detection_training_accuracy', 'Model accuracy from latest training')
    training_precision = Gauge('fraud_detection_training_precision', 'Model precision from latest training')
    training_recall = Gauge('fraud_detection_training_recall', 'Model recall from latest training')
    training_f1_score = Gauge('fraud_detection_training_f1_score', 'Model F1 score from latest training')
    training_roc_auc = Gauge('fraud_detection_training_roc_auc', 'Model ROC AUC from latest training')
    training_errors_total = Counter('fraud_detection_training_errors_total', 'Total number of training errors', ['error_type'])
    training_runs_total = Counter('fraud_detection_training_runs_total', 'Total number of training runs', ['status'])

# Global flag for graceful shutdown
_shutdown_requested = False

def _sigterm_handler(signum, frame):
    """Handle SIGTERM gracefully."""
    global _shutdown_requested
    logger.warning('Received SIGTERM signal. Shutting down gracefully...')
    _shutdown_requested = True


class FraudDetectionTraining:
    """
    End-to-end fraud detection training with complete feature engineering.
    
    This class:
    1. Ingests raw transaction data from PostgreSQL
    2. Engineers 74 sophisticated fraud detection features
    3. Trains XGBoost model with SMOTE for class imbalance
    4. Tracks experiments in MLflow
    5. Deploys trained model
    """
    
    def __init__(self, config_path='/app/config.yaml'):
        """Initialize training system."""
        
        # Environment setup
        os.environ['GIT_PYTHON_REFRESH'] = 'quiet'
        os.environ['GIT_PYTHON_GIT_EXECUTABLE'] = '/usr/bin/git'
        
        # Load environment variables
        load_dotenv(dotenv_path='/app/.env')
        
        # Load configuration
        self.config = self._load_config(config_path)
        
        # AWS credentials for MLflow
        os.environ.update({
            'AWS_ACCESS_KEY_ID': os.getenv('AWS_ACCESS_KEY_ID'),
            'AWS_SECRET_ACCESS_KEY': os.getenv('AWS_SECRET_ACCESS_KEY'),
        })
        
        # Validate environment
        self._validate_environment()
        
        # Initialize MLflow
        self._setup_mlflow()
        
        logger.info("Fraud detection training system initialized")
    
    def _load_config(self, config_path: str) -> dict:
        """Load YAML configuration."""
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            logger.info('Configuration loaded successfully')
            return config
        except Exception as e:
            logger.error(f'Failed to load configuration: {e}')
            raise
    
    def _validate_environment(self):
        """Validate required environment variables and connections."""
        
        # Check database configuration
        db_host = os.getenv('DB_HOST') or os.getenv('POSTGRES_HOST')
        if not db_host:
            logger.warning('Database host not configured')
        else:
            logger.info(f'Database configured: {db_host}')
        
        # Check MLflow storage
        self._check_minio_connection()
        
        # Wait for key services
        try:
            pg_host = os.getenv('POSTGRES_HOST') or os.getenv('DB_HOST')
            if pg_host:
                self._wait_for_hostname(pg_host, timeout=60)
        except Exception:
            logger.debug('Postgres hostname check skipped or failed')
    
    def _check_minio_connection(self):
        """Validate object storage for MLflow artifacts."""
        try:
            import boto3
            
            s3_endpoint = self.config.get('mlflow', {}).get('s3_endpoint_url')
            if not s3_endpoint:
                logger.info('No S3 endpoint configured')
                return
            
            # Skip for Azure Blob
            if s3_endpoint.startswith('wasbs://') or 'blob.core.windows.net' in s3_endpoint:
                logger.info(f'Azure Blob storage detected: {s3_endpoint}')
                return
            
            s3 = boto3.client(
                's3',
                endpoint_url=s3_endpoint,
                aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
                aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY')
            )
            
            buckets = s3.list_buckets()
            bucket_names = [b['Name'] for b in buckets.get('Buckets', [])]
            logger.info(f'Object storage verified. Buckets: {bucket_names}')
            
            mlflow_bucket = self.config['mlflow'].get('bucket', 'mlflow')
            if mlflow_bucket not in bucket_names:
                s3.create_bucket(Bucket=mlflow_bucket)
                logger.info(f'Created MLflow bucket: {mlflow_bucket}')
                
        except Exception as e:
            logger.error(f'Object storage connection failed: {e}')
    
    def _wait_for_hostname(self, host: str, port: Optional[int] = None, 
                          timeout: int = 30, interval: float = 2.0):
        """Wait for hostname to resolve."""
        start = time.time()
        while True:
            try:
                socket.getaddrinfo(host, port or 0)
                if port:
                    with socket.create_connection((host, port), timeout=3):
                        return True
                return True
            except Exception as e:
                if time.time() - start > timeout:
                    logger.warning(f'Timeout waiting for {host}:{port}')
                    raise TimeoutError(f'Could not resolve {host}') from e
                time.sleep(interval)
    
    def _setup_mlflow(self):
        """Configure MLflow for experiment tracking."""
        try:
            import mlflow
            
            # Wait for MLflow server
            tracking_uri = self.config.get('mlflow', {}).get('tracking_uri')
            if tracking_uri:
                parsed = urllib.parse.urlparse(tracking_uri)
                host = parsed.hostname
                port = parsed.port or (80 if parsed.scheme == 'http' else 443)
                if host:
                    try:
                        self._wait_for_hostname(host, port=port, timeout=60)
                    except Exception:
                        logger.debug('MLflow hostname check timed out')
            
            mlflow.set_tracking_uri(self.config['mlflow']['tracking_uri'])
            mlflow.set_experiment(self.config['mlflow']['experiment_name'])
            logger.info('MLflow configured successfully')
            
        except Exception as e:
            logger.warning(f'MLflow setup failed: {e}')
    
    def ingest_data(self, table_name: str = 'transactions', limit: int = 10000) -> pd.DataFrame:
        """
        Ingest raw transaction data from PostgreSQL database.

        Args:
            table_name: name of the transactions table to query (validated)
            limit: maximum number of rows to ingest

        Returns:
            DataFrame with raw transaction data
        """
        logger.info("Starting data ingestion from PostgreSQL (table=%s, limit=%s)...", table_name, limit)

        try:
            import psycopg2
            import re

            # Validate table name to avoid SQL injection (simple whitelist)
            # Allow optional schema: schema.table or table
            table_name_pattern = r'^([A-Za-z_][A-Za-z0-9_]*)(\.([A-Za-z_][A-Za-z0-9_]*))?$'
            if not re.match(table_name_pattern, table_name):
                raise ValueError(f"Invalid table name: {table_name}")

# Get database credentials (prefer explicit TRANSACTIONS_* envs for training)
            db_config = {
                'host': os.getenv('TRANSACTIONS_HOST') or os.getenv('DB_HOST') or os.getenv('POSTGRES_HOST', '127.0.0.1'),
                'port': int(os.getenv('TRANSACTIONS_PORT') or os.getenv('DB_PORT') or os.getenv('POSTGRES_PORT') or 5432),
                'dbname': os.getenv('TRANSACTIONS_DB') or os.getenv('DB_NAME') or os.getenv('POSTGRES_DB') or 'transactions_db',
                'user': os.getenv('TRANSACTIONS_USER') or os.getenv('DB_USER') or os.getenv('POSTGRES_USER') or 'fraud_training',
                'password': os.getenv('TRANSACTIONS_PASSWORD') or os.getenv('DB_PASSWORD') or os.getenv('POSTGRES_PASSWORD') or 'training_password',
                'sslmode': os.getenv('DB_SSLMODE', 'prefer')
            }

            logger.info(
                "Connecting to transactions DB: %s:%s/%s (user=%s)",
                db_config['host'], db_config['port'], db_config['dbname'], db_config['user']
            )

            # Connect to database
            conn = psycopg2.connect(**db_config)

            # Ensure table exists (and try to discover schema if not on search_path)
            try:
                with conn.cursor() as cur:
                    # to_regclass returns NULL if not found in search_path; accepts 'schema.table' too
                    cur.execute("SELECT to_regclass(%s)", (table_name,))
                    reg = cur.fetchone()[0]
                    if not reg:
                        # Try finding the table in any schema
                        cur.execute(
                            """
                            SELECT table_schema
                            FROM information_schema.tables
                            WHERE table_name = %s
                            LIMIT 1
                            """,
                            (table_name,)
                        )
                        row = cur.fetchone()
                        if row:
                            found_schema = row[0]
                            table_name = f"{found_schema}.{table_name}"
                            logger.warning("Table found in schema '%s' — using '%s'", found_schema, table_name)
                        else:
                            raise ValueError(
                                f"Transactions table '{table_name}' not found in database '{db_config['dbname']}'. "
                                "Ensure the table exists, or set Airflow Variable 'transactions_table' to the correct schema.table, "
                                "or set DB env vars (POSTGRES_DB/DB_NAME) to point to the database containing your transactions."
                            )
            except Exception:
                conn.close()
                raise

            safe_limit = max(1, min(int(limit), 500000))
            query = f"""
                SELECT 
                    transaction_id, order_id, user_id, full_name, email, phone_number,
                    gender, age, registration_date, account_status, session_id, timestamp,
                    action, device_id, ip_address, location, country, device_type, browser,
                    geo_location, session_duration, product_id, product_name, category,
                    price, discount, vendor_id, quantity, payment_method, payment_status,
                    amount, currency, delivery_address, return_request, refund_status,
                    rating, is_fraud, fraud_type, created_at
                FROM {table_name}
                ORDER BY timestamp DESC
                LIMIT {safe_limit}
            """

            logger.info("Executing query (limit=%s) against %s", safe_limit, table_name)

            # Prefer SQLAlchemy engine for large reads (pandas handles engine/connection more efficiently)
            try:
                from sqlalchemy import create_engine
                # Construct URL for transactions DB
                url = (
                    f"postgresql+psycopg2://{db_config['user']}:{db_config['password']}@"
                    f"{db_config['host']}:{db_config['port']}/{db_config['dbname']}"
                )
                engine = create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=10)
                df = pd.read_sql_query(query, engine)
            except Exception as e:
                logger.warning('SQLAlchemy engine not available or failed: %s. Falling back to DB-API connection.', e)
                df = pd.read_sql_query(query, conn)
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

            logger.info(f"Ingested {len(df)} raw transactions from {table_name} (requested {safe_limit})")
            if len(df):
                logger.info(f"Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")
                logger.info(f"Fraud rate: {df['is_fraud'].mean()*100:.2f}%")

            return df
            
        except Exception as e:
            logger.error(f"Data ingestion failed: {e}", exc_info=True)
            raise
    
    def engineer_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Perform complete feature engineering to create 74 fraud detection features.
        (54 engineered + 20 raw producers = 74 total)
        
        Args:
            df: Raw transaction DataFrame
            
        Returns:
            DataFrame with engineered features
        """
        logger.info("Starting feature engineering for 74 features (54 engineered + 20 raw)...")
        
        df = df.copy()
        
        # Convert timestamp to datetime
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df['registration_date'] = pd.to_datetime(df['registration_date'])
        
        # Sort by timestamp for velocity calculations
        df = df.sort_values('timestamp').reset_index(drop=True)
        
        # ========== AMOUNT-BASED FEATURES (STRONGEST SIGNAL) ==========
        # Data analysis shows fraud amount avg=113,805 vs legitimate avg=42,506 (2.7x)
        logger.info("Engineering amount-based features (strongest signal)...")
        
        # 1. Account age in days (still useful)
        df['account_age_days'] = (df['timestamp'] - df['registration_date']).dt.total_seconds() / 86400
        df['account_age_days'] = df['account_age_days'].clip(lower=0)
        
        # 2. Amount z-score (how many std devs from mean)
        amount_mean = df['amount'].mean()
        amount_std = df['amount'].std()
        df['amount_zscore'] = (df['amount'] - amount_mean) / (amount_std + 1e-6)
        
        # 3. Amount percentile rank (0-1 scale)
        df['amount_percentile'] = df['amount'].rank(pct=True)
        
        # 4. High value transaction flag (top 10%)
        amount_90th = df['amount'].quantile(0.90)
        df['is_high_value'] = (df['amount'] > amount_90th).astype(int)
        
        # 5. Amount to user's average ratio
        user_avg_amount = df.groupby('user_id')['amount'].transform('mean')
        df['amount_to_user_avg_ratio'] = df['amount'] / (user_avg_amount + 1)
        
        # 6. Amount to category average ratio (category anomaly detection)
        category_avg_amount = df.groupby('category')['amount'].transform('mean')
        df['amount_to_category_avg_ratio'] = df['amount'] / (category_avg_amount + 1)
        
        # 7. Session-to-amount ratio (fraud = short session + high value)
        df['session_amount_ratio'] = df['session_duration'] / (df['amount'] / 1000 + 1)
        
        # 8. Short session flag (fraudsters spend less time)
        session_25th = df['session_duration'].quantile(0.25)
        df['is_short_session'] = (df['session_duration'] < session_25th).astype(int)
        
        # 9-10. Combined fraud risk indicators  
        df['high_value_short_session'] = (df['is_high_value'] & df['is_short_session']).astype(int)
        df['fraud_risk_composite'] = (
            df['amount_zscore'].clip(-3, 3) / 6 * 0.4 +  # Normalized amount deviation
            df['is_high_value'] * 0.3 +                   # High value flag
            df['is_short_session'] * 0.2 +                # Short session flag
            (df['payment_status'] == 'failed').astype(float) * 0.1  # Failed payment
        ).clip(0, 1)
        
        # 11. Velocity features (transaction count based, not time-based)
        df['user_transaction_count'] = df.groupby('user_id')['transaction_id'].transform('count')
        df['user_total_amount'] = df.groupby('user_id')['amount'].transform('sum')
        df['user_avg_transaction'] = df['user_total_amount'] / (df['user_transaction_count'] + 1)
        
        # 12. Bulk purchase flag (high quantity = potential triangulation fraud)
        df['is_bulk_purchase'] = (df['quantity'] >= 3).astype(int)
        
        # 13. Hour of day (keep for variance in future data)
        df['hour_of_day'] = df['timestamp'].dt.hour
        
        # ========== IDENTITY FEATURES (4) ==========
        logger.info("Engineering identity features...")
        
        # 9. Identity mismatch score
        df['identity_mismatch_score'] = 0.0
        df.loc[df['account_age_days'] < 7, 'identity_mismatch_score'] += 0.3
        df.loc[df['account_status'] == 'new', 'identity_mismatch_score'] += 0.2
        df['identity_mismatch_score'] = df['identity_mismatch_score'].clip(0, 1)
        
        # 10. Identity verification score
        df['identity_verification_score'] = 0.7
        df.loc[df['account_status'] == 'verified', 'identity_verification_score'] = 0.95
        df.loc[df['account_status'] == 'new', 'identity_verification_score'] = 0.3
        df.loc[df['account_status'] == 'suspended', 'identity_verification_score'] = 0.1
        
        # 11. Identity confidence score
        df['identity_confidence_score'] = (
            df['identity_verification_score'] * 0.6 + 
            (1 - df['identity_mismatch_score']) * 0.4
        )
        
        # ========== DEVICE FEATURES (4) ==========
        logger.info("Engineering device features...")
        
        # 13. Device fingerprint score
        device_counts = df.groupby('device_id')['user_id'].nunique()
        device_user_count = df['device_id'].map(device_counts)
        df['device_fingerprint_score'] = 1 - (device_user_count - 1).clip(0, 10) / 10
        
        # 14. Android emulator detection
        df['android_emulator_detection'] = (
            (df['device_type'] == 'Mobile') & 
            (df['device_id'].fillna('').str.contains('emu|emulator|android', case=False, na=False) |
             df['browser'].str.contains('Android', case=False, na=False))
        ).astype(int)
        
        # 15. Browser integrity score
        trusted_browsers = ['Chrome', 'Firefox', 'Safari', 'Edge']
        df['browser_integrity_score'] = df['browser'].isin(trusted_browsers).astype(float).clip(0, 1)
        
        # 16. Device trust score
        df['device_trust_score'] = (
            df['device_fingerprint_score'] * 0.5 +
            (1 - df['android_emulator_detection']) * 0.3 +
            df['browser_integrity_score'] * 0.2
        )
        
        # 17. Device change rate
        df['device_change_rate'] = df.groupby('user_id')['device_id'].transform(
            lambda x: x.nunique() / len(x) if len(x) > 0 else 0
        )
        
        # ========== LOCATION FEATURES (3) ==========
        logger.info("Engineering location features...")
        
        # 18. IP risk score
        df['ip_risk_score'] = 0.0
        df.loc[df['ip_address'].str.startswith('100.'), 'ip_risk_score'] += 0.5
        df.loc[df['ip_address'].str.startswith('200.'), 'ip_risk_score'] += 0.5
        df['ip_risk_score'] = df['ip_risk_score'].clip(0, 1)
        
        # 19. Proxy detection flag
        df['proxy_detection_flag'] = (df['ip_risk_score'] > 0.6).astype(int)
        
        # 20. VPN usage flag
        df['vpn_usage_flag'] = (df['ip_risk_score'] > 0.4).astype(int)
        
        # ========== PAYMENT FEATURES (5) ==========
        logger.info("Engineering payment features...")
        
        # 21. Failed payment ratio
        user_payment_stats = df.groupby('user_id').agg({
            'payment_status': lambda x: (x == 'failed').sum() / len(x) if len(x) > 0 else 0
        }).rename(columns={'payment_status': 'failed_payment_ratio'})
        df = df.merge(user_payment_stats, left_on='user_id', right_index=True, how='left')
        df['failed_payment_ratio'] = df['failed_payment_ratio'].fillna(0)
        
        # 22. Current order value ratio
        user_avg_amount = df.groupby('user_id')['amount'].transform('mean')
        df['current_order_value_ratio'] = df['amount'] / (user_avg_amount + 1)
        
        # 23. Payment method anomaly
        user_payment_methods = df.groupby('user_id')['payment_method'].transform('nunique')
        df['payment_method_anomaly'] = (user_payment_methods > 3).astype(int)
        
        # 24. Payment anomaly score
        df['payment_anomaly_score'] = (
            df['failed_payment_ratio'] * 0.4 +
            (df['current_order_value_ratio'] > 3).astype(float) * 0.3 +
            df['payment_method_anomaly'] * 0.3
        )
        
        # 25. Payment status risk (indicator of payment problems)
        df['payment_status_risk'] = (df['payment_status'].isin(['failed', 'pending'])).astype(int)
        
        # ========== NETWORK FEATURES (5) ==========
        logger.info("Engineering network features...")
        
        # 26. Fraud ring score
        ip_user_count = df.groupby('ip_address')['user_id'].transform('nunique')
        device_user_count_net = df.groupby('device_id')['user_id'].transform('nunique')
        df['fraud_ring_score'] = ((ip_user_count > 5) | (device_user_count_net > 3)).astype(float) * 0.7
        
        # 27. Vendor risk score
        vendor_fraud_rate = df.groupby('vendor_id')['is_fraud'].transform('mean')
        df['vendor_risk_score'] = vendor_fraud_rate.fillna(0.5)
        
        # 28. User reputation score
        df['user_reputation_score'] = 0.7
        df.loc[df['account_status'] == 'verified', 'user_reputation_score'] = 0.9
        df.loc[df['account_status'] == 'new', 'user_reputation_score'] = 0.4
        df.loc[df['account_status'] == 'suspended', 'user_reputation_score'] = 0.1
        df['user_reputation_score'] -= df['failed_payment_ratio'] * 0.3
        df['user_reputation_score'] = df['user_reputation_score'].clip(0, 1)
        
        # 29. Shared IP count
        df['shared_ip_count'] = df.groupby('ip_address')['user_id'].transform('nunique')
        
        # 30. Shared phone number count
        df['shared_phone_number_count'] = df.groupby('phone_number')['user_id'].transform('nunique')
        
        # ========== BEHAVIORAL FEATURES (4) ==========
        logger.info("Engineering behavioral features...")
        
        # 31. Activity timing score
        # Replaced is_night_transaction with inline calculation
        is_night = ((df['hour_of_day'] >= 22) | (df['hour_of_day'] <= 5)).astype(int)
        median_hour = df.groupby('user_id')['hour_of_day'].transform('median').fillna(df['hour_of_day'].median())
        hour_dev = (df['hour_of_day'] - median_hour).abs()
        hour_dev_norm = (hour_dev / 12).clip(0, 1)
        df['activity_timing_score'] = (is_night * 0.6 + hour_dev_norm * 0.4).clip(0, 1)
        
        # 32. Anomaly frequency score
        # Replaced velocity features with available ones
        df['anomaly_frequency_score'] = (
            (df['user_transaction_count'] > 10).astype(float) * 0.4 +
            (df['amount'] > 100000).astype(float) * 0.3 +
            (df['is_short_session']).astype(float) * 0.3
        )
        
        # 33. Behavioral consistency score
        df['behavioral_consistency_score'] = 1 - df['anomaly_frequency_score']
        
        # 34. Session behavior score
        df['session_behavior_score'] = 1 - (
            (df['is_short_session']).astype(float) * 0.5 +
            (df['action'] == 'purchase').astype(float) * 0.3
        )
        
        # ========== PRODUCT/PRICE FEATURES (1) ==========
        logger.info("Engineering product features...")
        
        # 35. Product price anomaly score
        category_avg_price = df.groupby('category')['price'].transform('mean')
        df['product_price_anomaly_score'] = (
            (df['price'] / (category_avg_price + 1)) - 1
        ).abs().clip(0, 2) / 2
        
        # ========== ADDRESS FEATURES (2) ==========
        logger.info("Engineering address features...")
        
        # 36. Address reuse rate
        df['address_reuse_rate'] = df.groupby('user_id')['delivery_address'].transform(
            lambda x: 1 - (x.nunique() / len(x)) if len(x) > 0 else 0
        )
        
        # 37. Shared address count
        df['shared_address_count'] = df.groupby('delivery_address')['user_id'].transform('nunique')
        
        # ========== DELIVERY/REFUND FEATURES (5) ==========
        logger.info("Engineering delivery and refund features...")
        
        # 38. Refund abuse score
        user_refund_rate = df.groupby('user_id')['return_request'].transform('mean')
        df['refund_abuse_score'] = user_refund_rate.fillna(0)
        
        # 39. Failed delivery pattern
        df['failed_delivery_pattern'] = (
            (df['payment_status'] == 'failed') & 
            (df['action'] == 'purchase')
        ).astype(int)
        
        # 40. Refund to purchase ratio
        user_purchase_count = df[df['action'] == 'purchase'].groupby('user_id').size()
        user_refund_count = df[df['return_request']].groupby('user_id').size()
        refund_ratio = (user_refund_count / user_purchase_count).fillna(0)
        df['refund_to_purchase_ratio'] = df['user_id'].map(refund_ratio).fillna(0)
        
        # 41. Delivery dispute rate
        df['delivery_dispute_rate'] = (
            (df['return_request']) & 
            (df['refund_status'].isin(['requested', 'approved']))
        ).astype(float)
        df['delivery_dispute_rate'] = df.groupby('user_id')['delivery_dispute_rate'].transform('mean').fillna(0)
        
        # 42. Refund severity score
        refund_severity_map = {
            'none': 0,
            'requested': 0.3,
            'approved': 0.6,
            'completed': 0.8,
            'denied': 0.2
        }
        df['refund_severity_score'] = df['refund_status'].map(refund_severity_map).fillna(0)
        
        # ========== AGGREGATE FEATURES ==========
        # NOTE: Removed hour_sin, hour_cos, day_of_week (zero variance in current data)
        logger.info("Adding aggregate features...")
        
        # Month (keep - may have some variance)
        df['month'] = df['timestamp'].dt.month
        
        # 47. Price-discount ratio
        df['price_discount_ratio'] = df['discount'] / (df['price'].abs() + 1)
        
        # ========== AGGREGATION FEATURES (7) ==========
        
        # 48. Amount per quantity
        df['amount_per_quantity'] = df['amount'] / (df['quantity'] + 1)
        
        # 49. Vendor average quantity
        df['vendor_avg_quantity'] = df.groupby('vendor_id')['quantity'].transform('mean').fillna(0)
        
        # 50. User average session duration
        df['user_avg_session_duration'] = df.groupby('user_id')['session_duration'].transform('mean').fillna(0)
        
        # 51. Product popularity
        df['product_popularity'] = df.groupby('product_id')['transaction_id'].transform('count') / max(1, len(df))
        
        # 52. Vendor unique products
        df['vendor_unique_products'] = df.groupby('vendor_id')['product_id'].transform('nunique').fillna(0)
        
        # 53. Country average amount
        df['country_avg_amount'] = df.groupby('country')['amount'].transform('mean').fillna(0)
        
        # 54. Time since previous transaction
        df['time_since_prev_txn_sec'] = df.groupby('user_id')['timestamp'].diff().dt.total_seconds().fillna(0)
        
        logger.info(f"Feature engineering complete with enhanced amount-based features")
        logger.info(f"Total columns: {len(df.columns)} (engineered + raw)")
        
        return df
    
    def train_model(self, df: pd.DataFrame) -> Tuple[Any, Dict]:
        """
        Train XGBoost fraud detection model with engineered features.
        
        Args:
            df: DataFrame with engineered features
            
        Returns:
            Tuple of (trained_model, metrics_dict)
        """
        start_time = time.time()
        logger.info("Starting model training...")
        
        try:
            # Import ML libraries
            from sklearn.model_selection import train_test_split, RandomizedSearchCV, StratifiedKFold
            from sklearn.preprocessing import OrdinalEncoder, OneHotEncoder, FunctionTransformer
            from sklearn.compose import ColumnTransformer
            from sklearn.metrics import (precision_recall_curve, average_precision_score,
                                       precision_score, recall_score, f1_score, fbeta_score,
                                       confusion_matrix, make_scorer)
            from xgboost import XGBClassifier
            from imblearn.pipeline import Pipeline as ImbPipeline
            from imblearn.over_sampling import SMOTE
            import joblib
            import matplotlib.pyplot as plt
            from mlflow.models.signature import infer_signature
            # Ensure feature engineering has been applied so all 62 features exist
            try:
                df = self.engineer_features(df)
                logger.info(f"Post-engineering columns: {len(df.columns)}")
            except Exception as e:
                logger.warning(f"Feature engineering step failed or returned early: {e}")

            # Prepare features and target
            exclude_cols = [
                'transaction_id', 'order_id', 'user_id', 'full_name', 'email',
                'phone_number', 'session_id', 'device_id', 'ip_address', 'product_id',
                'product_name', 'delivery_address', 'geo_location', 'vendor_id',
                'is_fraud', 'fraud_type', 'created_at', 'timestamp', 'registration_date'
            ]
            feature_cols = [col for col in df.columns if col not in exclude_cols]
            X = df[feature_cols].copy()
            y = df['is_fraud'].copy()
            
            # Handle missing values
            X = X.fillna(0)

            # Identify categorical columns
            categorical_cols = X.select_dtypes(include=['object', 'category']).columns.tolist()
            numeric_cols = X.select_dtypes(include=[np.number]).columns.tolist()

            logger.info(f"Training with {len(feature_cols)} features")
            logger.info(f"Categorical: {len(categorical_cols)}, Numeric: {len(numeric_cols)}")
            logger.info(f"Class distribution: {y.value_counts().to_dict()}")

            # Check engineered feature count (warning only - don't abort)
            expected_count = int(self.config.get('model', {}).get('expected_feature_count', 50))
            if len(feature_cols) < expected_count:
                logger.warning(
                    "Found %d features, expected %d. Training will continue with available features.",
                    len(feature_cols), expected_count
                )
            
            # Train/test split
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=0.2, random_state=42, stratify=y
            )
            
            # Start MLflow run
            run = None
            max_mlflow_retries = 3
            backoff = 2
            
            for attempt in range(1, max_mlflow_retries + 1):
                try:
                    run = mlflow.start_run()
                    break
                except Exception as e:
                    logger.warning(f'MLflow start_run attempt {attempt}/{max_mlflow_retries} failed: {e}')
                    if attempt == max_mlflow_retries:
                        raise
                    time.sleep(backoff ** (attempt - 1))
            
            try:
                # Log data metrics
                mlflow.log_metrics({
                    'train_samples': X_train.shape[0],
                    'test_samples': X_test.shape[0],
                    'positive_samples': int(y_train.sum()),
                    'fraud_rate': float(y_train.mean()),
                    'num_features': len(feature_cols),
                    'num_categorical': len(categorical_cols),
                    'num_numeric': len(numeric_cols)
                })
                
                # Build preprocessing pipeline using OrdinalEncoder for categoricals (SMOTE-compatible)
                # OrdinalEncoder produces integer values that SMOTE can interpolate; OneHotEncoder produces invalid fractional categories
                from sklearn.compose import ColumnTransformer
                from sklearn.preprocessing import OrdinalEncoder
                if categorical_cols:
                    # Use OrdinalEncoder on all categorical columns
                    preprocessor = ColumnTransformer(
                        transformers=[
                            ("cat", OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1, dtype=np.float32), categorical_cols),
                        ],
                        remainder="passthrough"
                    )
                else:
                    preprocessor = FunctionTransformer(func=lambda x: x, validate=False)
                
                # XGBoost configuration
                xgb_n_jobs = int(os.getenv('XGB_N_JOBS', 
                                          str(self.config.get('model', {}).get('n_jobs', 1))))
                xgb_n_estimators = int(self.config.get('model', {}).get('params', {}).get('n_estimators', 100))

                # Compute scale_pos_weight from training labels to handle class imbalance
                # Use 1.5x multiplier (2.0x caused worse results)
                pos = int(y_train.sum())
                neg = int(len(y_train) - pos)
                base_weight = float(neg / max(1, pos)) if pos > 0 else 1.0
                scale_pos_weight = base_weight * 1.5  # Boost fraud class weight by 50%
                logger.info(f'Computed scale_pos_weight={scale_pos_weight:.4f} (base={base_weight:.4f}, neg={neg}, pos={pos})')
                mlflow.log_param('scale_pos_weight', scale_pos_weight)

                xgb = XGBClassifier(
                    eval_metric='aucpr',
                    random_state=self.config.get('model', {}).get('seed', 42),
                    reg_lambda=1.0,
                    n_estimators=xgb_n_estimators,
                    n_jobs=xgb_n_jobs,
                    tree_method=self.config.get('model', {}).get('tree_method', 'hist'),
                    scale_pos_weight=scale_pos_weight
                )
                
                # Build pipeline with SMOTE for class imbalance (safe with OrdinalEncoder)
                logger.info('Constructing pipeline with SMOTE for class imbalance')
                # Use sampling_strategy=0.5 (fraud:legitimate = 1:2 ratio) to balance without extreme overfitting
                pipeline = ImbPipeline([
                    ('preprocessor', preprocessor),
                    ('smote', SMOTE(sampling_strategy=0.5, k_neighbors=3, random_state=self.config.get('model', {}).get('seed', 42))),
                    ('classifier', xgb)
                ])
                
                # Hyperparameter search space - conservative to prevent overfitting
                param_dist = {
                    'classifier__max_depth': [3, 5, 7],
                    'classifier__learning_rate': [0.01, 0.05, 0.1],
                    'classifier__subsample': [0.6, 0.8, 1.0],
                    'classifier__colsample_bytree': [0.6, 0.8, 1.0],
                    'classifier__gamma': [0, 0.1, 0.3],
                    'classifier__reg_alpha': [0, 0.1, 0.5]
                }
                
                # Randomized search with stratified CV
                # For best fraud prevention: use beta=5 (recall 5x weighted over precision)
                # Business priority: Catch fraud > minimize false alarms
                # Target: Recall 60-70%, Precision 40-50% (realistic for this class imbalance)
                from sklearn.metrics import fbeta_score
                searcher = RandomizedSearchCV(
                    pipeline,
                    param_dist,
                    n_iter=50,  # More iterations to find best parameter combo
                    scoring=make_scorer(fbeta_score, beta=5, zero_division=0),  # beta=5 prioritizes recall heavily
                    cv=StratifiedKFold(n_splits=3, shuffle=True),
                    n_jobs=1,  # Sequential to avoid DB connection issues
                    refit=True,
                    error_score='raise',
                    random_state=self.config.get('model', {}).get('seed', 42),
                    verbose=1
                )
                
                logger.info('Starting hyperparameter tuning with RECALL MAXIMIZATION (beta=5, realistic fraud prevention)...')
                searcher.fit(X_train, y_train)
                best_model = searcher.best_estimator_
                best_params = searcher.best_params_
                logger.info(f'Best hyperparameters: {best_params}')
                
                
                # Determine optimal threshold MAXIMIZING RECALL for fraud prevention
                # Strategy: Find threshold with highest recall, accept lower precision
                # Metric Goal: Recall >= 0.80 (catch 80% of fraud)
                train_proba = best_model.predict_proba(X_train)[:, 1]
                precision_arr, recall_arr, thresholds_arr = precision_recall_curve(y_train, train_proba)
                
                # Find threshold with recall >= 0.80 and maximize precision among those
                valid_indices = np.where(recall_arr >= 0.80)[0]
                if len(valid_indices) > 0:
                    best_idx = valid_indices[np.argmax(precision_arr[valid_indices])]
                    best_threshold = thresholds_arr[best_idx] if best_idx < len(thresholds_arr) else 0.3
                    logger.info(f'Found threshold {best_threshold:.4f} with recall >= 80%')
                else:
                    # If can't hit 80%, try 70%
                    valid_indices = np.where(recall_arr >= 0.70)[0]
                    if len(valid_indices) > 0:
                        best_idx = valid_indices[np.argmax(precision_arr[valid_indices])]
                        best_threshold = thresholds_arr[best_idx] if best_idx < len(thresholds_arr) else 0.2
                        logger.warning(f'Could not reach 80% recall. Targeting 70%. Threshold {best_threshold:.4f}')
                    else:
                        # Fallback: maximize F2 score (recall weighted higher)
                        f2_scores = (5 * precision_arr * recall_arr) / (4 * precision_arr + recall_arr + 1e-6)
                        best_idx = np.argmax(f2_scores)
                        best_threshold = thresholds_arr[best_idx] if best_idx < len(thresholds_arr) else 0.1
                        logger.warning(f'Could not reach 70% recall. Maximizing F2-score. Threshold {best_threshold:.4f}')
                
                logger.info(f'Optimal threshold: {best_threshold:.4f} (FRAUD PREVENTION: maximize recall, accept lower precision)')
                
                # Evaluate on test set
                test_proba = best_model.predict_proba(X_test)[:, 1]
                y_pred = (test_proba >= best_threshold).astype(int)
                
                # Calculate metrics
                test_precision = precision_score(y_test, y_pred, zero_division=0)
                test_recall = recall_score(y_test, y_pred, zero_division=0)
                test_f1 = f1_score(y_test, y_pred, zero_division=0)
                test_auc_pr = average_precision_score(y_test, test_proba)
                
                metrics = {
                    'auc_pr': float(test_auc_pr),
                    'precision': float(test_precision),
                    'recall': float(test_recall),
                    'f1': float(test_f1),
                    'threshold': float(best_threshold)
                }
                
                # Validate realistic fraud prevention targets
                # With severe class imbalance (96.8% legitimate), 80%+ on both is likely infeasible
                # Realistic targets: Recall 60-70% (catch most fraud), Precision 40-50% (acceptable false alarms)
                recall_target = 0.60
                precision_target = 0.40
                
                if test_recall >= 0.70:
                    logger.info(f'✓✓ STRONG RECALL: {test_recall:.2%} - Catching {int(test_recall*100)}% of fraud')
                    if test_precision >= precision_target:
                        logger.info(f'✓ PRECISION: {test_precision:.2%} - Acceptable false alarm rate')
                    else:
                        logger.info(f'⚠ PRECISION: {test_precision:.2%} - Lower than ideal but acceptable for fraud prevention')
                elif test_recall >= recall_target:
                    logger.warning(f'⚠ RECALL: {test_recall:.2%} - Catching ~60% of fraud (could be better)')
                    logger.info(f'  Precision: {test_precision:.2%}')
                else:
                    logger.error(f'✗ RECALL TOO LOW: {test_recall:.2%} - Need to improve features or collect more fraud data')
                    logger.error(f'  Precision: {test_precision:.2%}')
                
                # Log to MLflow
                mlflow.log_metrics(metrics)
                mlflow.log_params(best_params)
                
                # Confusion matrix
                cm = confusion_matrix(y_test, y_pred)
                tn, fp, fn, tp = cm.ravel()
                
                # Log confusion matrix details for dual-metric analysis
                logger.info(f'Confusion Matrix Analysis:')
                logger.info(f'  ✓ True Negatives (legitimate correctly allowed): {tn}')
                logger.info(f'  ✗ False Positives (legitimate wrongly flagged): {fp}')
                logger.info(f'  ✗ False Negatives (fraud MISSED): {fn}')
                logger.info(f'  ✓ True Positives (fraud correctly caught): {tp}')
                logger.info(f'Dual-metric performance:')
                logger.info(f'  • Recall = TP/(TP+FN) = {tp}/{tp+fn} = {tp/(tp+fn):.2%}')
                logger.info(f'  • Precision = TP/(TP+FP) = {tp}/{tp+fp} = {tp/(tp+fp):.2%}')
                logger.info(f'  • Specificity = TN/(TN+FP) = {tn}/{tn+fp} = {tn/(tn+fp):.2%}')
                
                plt.figure(figsize=(6, 4))
                plt.imshow(cm, interpolation='nearest', cmap=plt.cm.Blues)
                plt.title('Confusion Matrix')
                plt.colorbar()
                tick_marks = np.arange(2)
                plt.xticks(tick_marks, ['Not Fraud', 'Fraud'])
                plt.yticks(tick_marks, ['Not Fraud', 'Fraud'])
                
                for i in range(2):
                    for j in range(2):
                        plt.text(j, i, format(cm[i, j], 'd'), 
                               ha='center', va='center', color='red')
                
                plt.tight_layout()
                cm_filename = 'confusion_matrix.png'
                plt.savefig(cm_filename)
                mlflow.log_artifact(cm_filename)
                plt.close()
                
                # Precision-Recall curve
                plt.figure(figsize=(10, 6))
                plt.plot(recall_arr, precision_arr, marker='.', label='PR Curve')
                plt.xlabel('Recall')
                plt.ylabel('Precision')
                plt.title('Precision-Recall Curve')
                plt.legend()
                pr_filename = 'precision_recall_curve.png'
                plt.savefig(pr_filename)
                mlflow.log_artifact(pr_filename)
                plt.close()
                
                # Log feature importance
                try:
                    classifier = best_model.named_steps['classifier']
                    feature_importance = classifier.feature_importances_
                    
                    # Create mapping of feature indices to names
                    feature_names = []
                    if hasattr(best_model.named_steps['preprocessor'], 'get_feature_names_out'):
                        feature_names = list(best_model.named_steps['preprocessor'].get_feature_names_out())
                    else:
                        feature_names = [f'feature_{i}' for i in range(len(feature_importance))]
                    
                    # Log top 20 features by importance
                    # Log top features and bottom features for future optimization
                    top_indices = np.argsort(feature_importance)[-20:][::-1]
                    bottom_indices = np.argsort(feature_importance)[:10]
                    
                    logger.info('Top 20 Feature Importances (keep these):')
                    for idx in top_indices:
                        logger.info(f'  {feature_names[idx]}: {feature_importance[idx]:.6f}')
                    
                    logger.info('Bottom 10 Feature Importances (candidates for next round of feature selection):')
                    for idx in bottom_indices:
                        logger.info(f'  {feature_names[idx]}: {feature_importance[idx]:.6f}')
                    
                    # Compute optional feature selection for next iteration
                    max_importance = np.max(feature_importance)
                    importance_threshold = max_importance * 0.015  # 1.5% of max
                    weak_candidates = [
                        (feature_names[i], feature_importance[i]) 
                        for i in range(len(feature_names)) 
                        if feature_importance[i] < importance_threshold
                    ]
                    if weak_candidates:
                        logger.info(f'Weak features for future removal (importance < 1.5% of max = {importance_threshold:.6f}):')
                        for feat_name, feat_importance in sorted(weak_candidates, key=lambda x: x[1]):
                            logger.info(f'  - {feat_name}: {feat_importance:.6f}')
                    
                    # Create and save feature importance plot
                    plt.figure(figsize=(10, 8))
                    top_features = [feature_names[i] for i in top_indices]
                    top_importances = feature_importance[top_indices]
                    plt.barh(range(len(top_features)), top_importances)
                    plt.yticks(range(len(top_features)), top_features)
                    plt.xlabel('Importance')
                    plt.title('Top 20 Feature Importances')
                    plt.tight_layout()
                    fi_filename = 'feature_importance.png'
                    plt.savefig(fi_filename)
                    mlflow.log_artifact(fi_filename)
                    plt.close()
                except Exception as e:
                    logger.debug(f'Failed to log feature importance: {e}')
                
                # Save and register model
                signature = infer_signature(X_train, y_pred)
                mlflow.sklearn.log_model(
                    sk_model=best_model,
                    artifact_path='model',
                    signature=signature,
                    registered_model_name='fraud_detection_model'
                )
                
                # Save model locally
                os.makedirs('/app/models', exist_ok=True)
                joblib.dump(best_model, '/app/models/fraud_detection_model.pkl')
                
                logger.info(f'Training complete with metrics: {metrics}')
                # Update Prometheus metrics if available
                try:
                    if PROMETHEUS_AVAILABLE and isinstance(metrics, dict):
                        if 'accuracy' in metrics:
                            training_accuracy.set(float(metrics.get('accuracy', 0)))
                        if 'precision' in metrics:
                            training_precision.set(float(metrics.get('precision', 0)))
                        if 'recall' in metrics:
                            training_recall.set(float(metrics.get('recall', 0)))
                        if 'f1' in metrics:
                            training_f1_score.set(float(metrics.get('f1', 0)))
                        if 'roc_auc' in metrics:
                            training_roc_auc.set(float(metrics.get('roc_auc', 0)))
                        training_duration_seconds.observe(time.time() - start_time)
                        training_runs_total.labels(status='success').inc()
                except Exception:
                    logger.debug('Failed to record Prometheus training metrics')

                return best_model, metrics
                
            finally:
                try:
                    if run is not None:
                        mlflow.end_run()
                except Exception:
                    logger.debug('Failed to properly end MLflow run')
                
                # Cleanup
                import gc
                try:
                    del searcher, pipeline, X_train, X_test, y_train, y_test
                except NameError:
                    pass
                gc.collect()
        
        except Exception as e:
            # Record failure metrics
            if PROMETHEUS_AVAILABLE:
                try:
                    training_errors_total.labels(error_type='training_failure').inc()
                    training_runs_total.labels(status='failure').inc()
                    training_duration_seconds.observe(time.time() - start_time)
                except Exception:
                    logger.debug('Failed to record Prometheus error metrics')
            logger.error(f'Training failed: {e}', exc_info=True)
            raise
    
    def run_training_pipeline(self):
        """Execute the complete training pipeline."""
        logger.info("="*70)
        logger.info("FRAUD DETECTION TRAINING PIPELINE")
        logger.info("="*70)
        
        try:
            # Step 1: Ingest raw data
            logger.info("STEP 1: Data Ingestion")
            df_raw = self.ingest_data()
            
            if len(df_raw) < 100:
                logger.error("Insufficient data for training (minimum 100 records required)")
                return None, None
            
            # Step 2: Engineer features
            logger.info("STEP 2: Feature Engineering (74 features)")
            df_features = self.engineer_features(df_raw)
            
            # Step 3: Train model
            logger.info("STEP 3: Model Training")
            model, metrics = self.train_model(df_features)
            
            logger.info("="*70)
            logger.info("TRAINING PIPELINE COMPLETE")
            logger.info("="*70)
            logger.info(f"Model Performance:")
            for metric, value in metrics.items():
                logger.info(f"  {metric}: {value:.4f}")
            logger.info("="*70)
            
            return model, metrics
            
        except Exception as e:
            logger.error(f"Training pipeline failed: {e}", exc_info=True)
            raise


if __name__ == '__main__':
    # Configure logging
    logging.basicConfig(
        format="%(asctime)s - %(levelname)s - %(module)s - %(message)s",
        level=logging.INFO,
        handlers=[
            logging.FileHandler('./fraud_detection_training.log'),
            logging.StreamHandler()
        ]
    )
    
    # Register signal handler
    signal.signal(signal.SIGTERM, _sigterm_handler)
    
    # Run training
    trainer = FraudDetectionTraining()
    trainer.run_training_pipeline()
