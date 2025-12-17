"""
Fraud Detection Model Training library

This module contains the complete implementation of the fraud detection training logic.
It is intentionally kept in the plugins folder and free of heavy top-level side-effects
so it can be imported by Airflow without blocking DAG parsing or the scheduler.
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
from dotenv import load_dotenv

# Module logger
logger = logging.getLogger(__name__)

# Global flag for graceful shutdown on SIGTERM
_shutdown_requested = False

def _sigterm_handler(signum, frame):
    """Handle SIGTERM gracefully by setting shutdown flag."""
    global _shutdown_requested
    logger.warning('Received SIGTERM signal. Gracefully shutting down Kafka consumer...')
    _shutdown_requested = True


class FraudDetectionTraining:
    """
    End-to-end fraud detection training system implementing MLOps best practices.

    Key Architecture Components:
    - Configuration Management: Centralized YAML config with environment overrides
    - Data Ingestion: HTTP API with SASL/SSL authentication
    - Feature Engineering: Temporal, behavioral, and monetary feature constructs
    - Model Development: XGBoost with SMOTE for class imbalance
    - Hyperparameter Tuning: Randomized search with stratified cross-validation
    - Model Tracking: MLflow integration with metrics/artifact logging
    - Deployment Prep: Model serialization and registry

    The system is designed for horizontal scalability and cloud-native operation.
    """

    def __init__(self, config_path='/app/config.yaml'):
        # Environment hardening for containerized deployments
        os.environ['GIT_PYTHON_REFRESH'] = 'quiet'
        os.environ['GIT_PYTHON_GIT_EXECUTABLE'] = '/usr/bin/git'

        # Load environment variables before config to allow overrides
        load_dotenv(dotenv_path='/app/.env')

        # Configuration lifecycle management
        self.config = self._load_config(config_path)

        # Security-conscious credential handling
        os.environ.update({
            'AWS_ACCESS_KEY_ID': os.getenv('AWS_ACCESS_KEY_ID'),
            'AWS_SECRET_ACCESS_KEY': os.getenv('AWS_SECRET_ACCESS_KEY'),
        })

        # Pre-flight system checks
        self._validate_environment()

        # MLflow configuration for experiment tracking (imported locally to avoid DAG parse issues)
        try:
            import mlflow
            # Wait for MLflow server hostname to resolve to mitigate transient Docker DNS failures
            try:
                tracking_uri = self.config.get('mlflow', {}).get('tracking_uri')
                if tracking_uri:
                    parsed = urllib.parse.urlparse(tracking_uri)
                    host = parsed.hostname
                    port = parsed.port or (80 if parsed.scheme == 'http' else 443)
                    if host:
                        self._wait_for_hostname(host, port=port, timeout=60)
            except Exception:
                logger.debug('MLflow hostname check failed or timed out; continuing')

            mlflow.set_tracking_uri(self.config['mlflow']['tracking_uri'])
            mlflow.set_experiment(self.config['mlflow']['experiment_name'])
        except Exception:
            logger.warning('MLflow not available during initialization, will be imported during training')

    def _load_config(self, config_path: str) -> dict:
        """Load and validate hierarchical configuration."""
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            logger.info('Configuration loaded successfully')
            return config
        except Exception as e:
            logger.error('Failed to load configuration: %s', str(e))
            raise

    def _validate_environment(self):
        """System integrity verification with defense-in-depth checks."""
        fraud_api_url = os.getenv('FRAUD_API_URL')
        if not fraud_api_url:
            logger.warning('FRAUD_API_URL environment variable not set. Training may fail if no data source is available.')
        else:
            logger.info('FRAUD_API_URL is configured')

        # Keep object storage check for MLflow artifacts
        self._check_minio_connection()

        # Ensure key services are resolvable before starting heavy work (helps with transient Docker DNS issues)
        try:
            pg_host = os.getenv('POSTGRES_HOST')
            if pg_host:
                self._wait_for_hostname(pg_host, timeout=60)
        except Exception:
            logger.debug('Postgres hostname check skipped or failed; continuing')

    def _check_minio_connection(self):
        """Validate object storage connectivity and bucket configuration."""
        try:
            import boto3

            s3 = boto3.client(
                's3',
                endpoint_url=self.config['mlflow']['s3_endpoint_url'],
                aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
                aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY')
            )

            buckets = s3.list_buckets()
            bucket_names = [b['Name'] for b in buckets.get('Buckets', [])]
            logger.info('Minio connection verified. Buckets: %s', bucket_names)

            mlflow_bucket = self.config['mlflow'].get('bucket', 'mlflow')

            if mlflow_bucket not in bucket_names:
                s3.create_bucket(Bucket=mlflow_bucket)
                logger.info('Created missing MLFlow bucket: %s', mlflow_bucket)
        except Exception as e:
            logger.error('Minio connection failed: %s', str(e))

    def _wait_for_hostname(self, host: str, port: int | None = None, timeout: int = 30, interval: float = 2.0):
        """Wait until the given hostname resolves (and optionally the TCP port is reachable).

        This helps mitigate transient Docker DNS/name-resolution issues inside Compose.
        Raises TimeoutError if the host cannot be resolved within timeout seconds.
        """
        start = time.time()
        while True:
            try:
                # Try DNS resolution
                socket.getaddrinfo(host, port or 0)
                # Optionally check TCP port
                if port:
                    with socket.create_connection((host, port), timeout=3):
                        return True
                return True
            except Exception as e:
                if time.time() - start > timeout:
                    logger.warning('Timed out waiting for host %s:%s (%s)', host, port, e)
                    raise TimeoutError(f'Could not resolve host {host}') from e
                time.sleep(interval)

    def ingest_data(self) -> "pd.DataFrame":
        """
        End-to-end data ingestion pipeline from HTTP API.
        
        Implements:
        1. HTTP Pagination with resilient retries
        2. Response Normalization for multiple API shapes
        3. Type Conversion to proper data types
        4. Data Quality checks and trimming
        5. Monitoring and logging
        
        Returns:
            pd.DataFrame: Processed transaction records with correct data types
        """
        try:
            import pandas as pd
            import requests
            from requests.adapters import HTTPAdapter
            from urllib3.util.retry import Retry
            import time

            # ---- Phase 1: HTTP API Pagination ----
            base_url = os.getenv('FRAUD_API_URL')
            if not base_url:
                raise ValueError('FRAUD_API_URL is not configured')

            micro_batch_size = int(os.getenv('KAFKA_MICRO_BATCH_SIZE', 
                                            self.config.get('api', {}).get('micro_batch_size', 20000)))

            try:
                max_total_messages = int(os.getenv('FRAUD_API_MAX_RECORDS', 
                                                   self.config.get('api', {}).get('max_records', 80000)))
            except Exception:
                max_total_messages = 100000

            logger.info('Starting data ingestion from %s (page size=%d, max records=%d)', 
                       base_url, micro_batch_size, max_total_messages)

            session = requests.Session()
            retries = Retry(
                total=5,
                backoff_factor=2,
                status_forcelist=(500, 502, 503, 504),
                respect_retry_after_header=True,  # Respect server retry hints
                raise_on_status=False  # Don't raise immediately, we handle it
            )
            session.mount('https://', HTTPAdapter(max_retries=retries))
            session.mount('http://', HTTPAdapter(max_retries=retries))
            
            # Configure read timeout and connection timeout
            # timeout=(connect_timeout, read_timeout)
            timeout = (10, 120)  # 10s connect, 120s read

            offset = 0
            limit = micro_batch_size
            all_records = []
            attempt_backoff = 1
            max_attempt_backoff = 64

            while True:
                if _shutdown_requested:
                    logger.info('Shutdown requested. Stopping data ingestion loop.')
                    break

                params = {'offset': offset, 'limit': limit}
                try:
                    resp = session.get(base_url, params=params, timeout=timeout)
                    attempt_backoff = 1
                except requests.exceptions.Timeout as e:
                    logger.warning('Request timeout at offset %d after %.1fs. Retrying with backoff...', 
                                 offset, timeout[1])
                    time.sleep(attempt_backoff)
                    attempt_backoff = min(max_attempt_backoff, attempt_backoff * 2)
                    continue
                except requests.exceptions.ConnectionError as e:
                    logger.warning('Connection error at offset %d: %s. Retrying with backoff...', 
                                 offset, str(e))
                    time.sleep(attempt_backoff)
                    attempt_backoff = min(max_attempt_backoff, attempt_backoff * 2)
                    continue
                except Exception as e:
                    logger.warning('Transient error fetching API page at offset %d: %s', offset, str(e))
                    time.sleep(attempt_backoff)
                    attempt_backoff = min(max_attempt_backoff, attempt_backoff * 2)
                    continue

                if resp.status_code != 200:
                    logger.error('API responded with status %d: %s', resp.status_code, resp.text[:200])
                    resp.raise_for_status()

                payload = resp.json()

                if isinstance(payload, dict):
                    if 'data' in payload and isinstance(payload['data'], list):
                        page = payload['data']
                    elif 'transactions' in payload and isinstance(payload['transactions'], list):
                        page = payload['transactions']
                    else:
                        lists = [v for v in payload.values() if isinstance(v, list)]
                        page = lists[0] if lists else [payload]
                elif isinstance(payload, list):
                    page = payload
                else:
                    page = [payload]

                if not page:
                    logger.info('Received empty page from API at offset %d, stopping.', offset)
                    break

                all_records.extend(page)
                logger.info('Fetched %d records (offset %d). Total so far: %d', len(page), offset, len(all_records))

                if max_total_messages and len(all_records) >= max_total_messages:
                    logger.info('Reached max_total_messages limit (%d), stopping.', max_total_messages)
                    break

                if len(page) < limit:
                    logger.info('Last page received (size %d < limit %d).', len(page), limit)
                    break

                offset += len(page)

            if not all_records:
                raise ValueError('No records received from FRAUD API')

            df = pd.DataFrame(all_records)
            if df.empty:
                raise ValueError('No records received from FRAUD API (empty DataFrame)')

            logger.info('API pagination complete: %d total records, %d columns', len(df), len(df.columns))

            # ---- Phase 2: Data Type Conversion & Quality Checks ----
            
            timestamp_cols = ['timestamp', 'registration_date', 'created_at']
            for col in timestamp_cols:
                if col in df.columns:
                    df[col] = pd.to_datetime(df[col], errors='coerce', utc=True)

            if max_total_messages and len(df) > max_total_messages:
                present_ts = [c for c in timestamp_cols if c in df.columns]
                if present_ts:
                    ts_col = present_ts[0]
                    df = df.sort_values(by=ts_col, ascending=False, na_position='last').head(max_total_messages).reset_index(drop=True)
                    logger.info('Trimmed to most recent %d records using timestamp column: %s', max_total_messages, ts_col)
                else:
                    df = df.tail(max_total_messages).reset_index(drop=True)
                    logger.info('Trimmed to last %d records (no timestamp column available)', max_total_messages)

            numeric_cols = [
                'id', 'age', 'session_duration', 'price', 'discount', 'quantity',
                'amount', 'rating', 'account_age_days', 'sim_card_age_days',
                'vendor_age_days', 'discount_velocity_24h', 'transaction_velocity_1h',
                'transaction_velocity_24h', 'payment_velocity_1h', 'payment_velocity_24h',
                'shared_address_count', 'shared_phone_number_count', 'shared_ip_count',
                'linked_accounts', 'login_frequency', 'complaint_frequency'
            ]
            for col in numeric_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

            float_cols = [
                'identity_mismatch_score', 'identity_verification_score', 'sim_swap_probability',
                'device_fingerprint_score', 'product_price_anomaly_score', 'browser_integrity_score',
                'failed_payment_ratio', 'avg_order_value', 'current_order_value_ratio',
                'address_risk_score', 'location_distance_score', 'address_reuse_rate',
                'delivery_delay_ratio', 'rider_collusion_risk', 'refund_abuse_score',
                'refund_to_purchase_ratio', 'return_inspection_score', 'product_swap_probability',
                'fraud_ring_score', 'account_link_density', 'device_change_rate',
                'device_trust_score', 'ip_risk_score', 'user_reputation_score',
                'activity_timing_score', 'anomaly_frequency_score', 'behavioral_consistency_score',
                'vendor_risk_score', 'fake_review_score', 'delivery_dispute_rate'
            ]
            for col in float_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)

            boolean_cols = [
                'return_request', 'phone_verified', 'android_emulator_detection',
                'unusual_discount_flag', 'cart_tampering_detection', 'payment_method_anomaly',
                'is_linked_card', 'bank_transfer_verification', 'partial_payment_requirement',
                'ip_location_mismatch_flag', 'failed_delivery_pattern', 'otp_delivery_verification',
                'gps_delivery_confirmation', 'serial_number_mismatch', 'multi_device_login_flag',
                'proxy_detection_flag', 'vpn_usage_flag', 'rating_burst_detection',
                'email_disposable_flag'
            ]
            for col in boolean_cols:
                if col in df.columns:
                    df[col] = (df[col].astype(str).str.lower() == 't').astype(int)

            if 'is_fraud' in df.columns:
                df['is_fraud'] = pd.to_numeric(df['is_fraud'], errors='coerce').fillna(0).astype(int)
            else:
                raise ValueError('Fraud label (is_fraud) missing from data')

            fraud_rate = df['is_fraud'].mean() * 100
            logger.info('Data ingestion complete with fraud rate: %.2f%%', fraud_rate)
            logger.info('Final data shape: %d rows, %d columns', len(df), len(df.columns))

            return df
        except Exception as e:
            logger.error('Failed to ingest data: %s', str(e), exc_info=True)
            raise

    def create_features(self, df) -> "pd.DataFrame":
        """Feature engineering pipeline with temporal, behavioral, and risk features."""
        import numpy as np
        import pandas as pd

        df = df.sort_values(['user_id', 'timestamp']).copy() if 'user_id' in df.columns and 'timestamp' in df.columns else df.copy()

        # Temporal features
        if 'timestamp' in df.columns:
            df['transaction_hour'] = df['timestamp'].dt.hour
            df['is_night'] = ((df['transaction_hour'] >= 22) | (df['transaction_hour'] < 5)).astype(int)
            df['is_weekend'] = (df['timestamp'].dt.dayofweek >= 5).astype(int)
            df['transaction_day'] = df['timestamp'].dt.day
        else:
            df['transaction_hour'] = 0
            df['is_night'] = 0
            df['is_weekend'] = 0
            df['transaction_day'] = 0

        if 'account_age_days' not in df.columns:
            df['account_age_days'] = 0

        if 'transaction_velocity_24h' not in df.columns:
            df['transaction_velocity_24h'] = 0

        if 'current_order_value_ratio' not in df.columns:
            df['current_order_value_ratio'] = 1.0

        if 'vendor_id' in df.columns:
            high_risk_vendors = self.config.get('high_risk_vendors', [])
            df['vendor_risk_flag'] = df['vendor_id'].isin(high_risk_vendors).astype(int)
        else:
            df['vendor_risk_flag'] = 0

        # Feature set selection
        core_features = [
            'amount', 'price', 'discount', 'quantity',
            'is_night', 'is_weekend', 'transaction_day', 'transaction_hour',
            'account_age_days', 'session_duration'
        ]

        velocity_features = [
            'transaction_velocity_1h', 'transaction_velocity_24h',
            'payment_velocity_1h', 'payment_velocity_24h',
            'discount_velocity_24h', 'login_frequency'
        ]

        identity_features = [
            'identity_mismatch_score', 'identity_verification_score',
            'sim_swap_probability', 'phone_verified', 'email_disposable_flag'
        ]

        device_features = [
            'device_fingerprint_score', 'android_emulator_detection',
            'browser_integrity_score', 'ip_risk_score',
            'ip_location_mismatch_flag', 'location_distance_score',
            'proxy_detection_flag', 'vpn_usage_flag', 'device_trust_score'
        ]

        payment_features = [
            'failed_payment_ratio', 'current_order_value_ratio',
            'payment_method_anomaly', 'is_linked_card',
            'bank_transfer_verification', 'partial_payment_requirement'
        ]

        risk_features = [
            'fraud_ring_score', 'vendor_risk_score', 'user_reputation_score',
            'activity_timing_score', 'anomaly_frequency_score',
            'behavioral_consistency_score', 'fake_review_score',
            'product_price_anomaly_score', 'address_risk_score',
            'rider_collusion_risk', 'refund_abuse_score'
        ]

        delivery_features = [
            'delivery_delay_ratio', 'failed_delivery_pattern',
            'address_reuse_rate', 'shared_address_count',
            'refund_to_purchase_ratio', 'return_inspection_score',
            'product_swap_probability', 'delivery_dispute_rate'
        ]

        linkage_features = [
            'account_link_density', 'shared_phone_number_count',
            'shared_ip_count', 'linked_accounts',
            'device_change_rate', 'multi_device_login_flag'
        ]

        all_feature_candidates = (
            core_features + velocity_features + identity_features +
            device_features + payment_features + risk_features +
            delivery_features + linkage_features + ['vendor_risk_flag']
        )

        available_features = [f for f in all_feature_candidates if f in df.columns]

        for col in available_features:
            if df[col].isna().any():
                if df[col].dtype in ['int64', 'int32', 'float64', 'float32']:
                    df[col] = df[col].fillna(0)
                else:
                    df[col] = df[col].fillna(df[col].mode()[0] if len(df[col].mode()) > 0 else 0)

        logger.info('Selected %d features from %d candidates', len(available_features), len(all_feature_candidates))

        if 'is_fraud' not in df.columns:
            raise ValueError('Missing target column "is_fraud"')

        feature_df = df[available_features + ['is_fraud']].copy()

        if feature_df.empty:
            raise ValueError('Feature DataFrame is empty after feature engineering')

        logger.info('Feature engineering complete. Final shape: %d rows, %d columns', 
                   len(feature_df), len(feature_df.columns))

        return feature_df

    def train_model(self):
        """
        End-to-end training pipeline implementing ML best practices.
        
        Implements:
        1. Data Quality Checks
        2. Stratified Data Splitting
        3. Class Imbalance Mitigation (SMOTE)
        4. Hyperparameter Optimization
        5. Threshold Tuning
        6. Model Evaluation
        7. MLflow tracking and model registry
        """
        try:
            import numpy as np
            import pandas as pd
            import mlflow
            from mlflow.models import infer_signature
            import joblib
            import matplotlib.pyplot as plt
            from sklearn.compose import ColumnTransformer
            from sklearn.metrics import (
                make_scorer, fbeta_score, precision_recall_curve,
                average_precision_score, precision_score, recall_score,
                f1_score, confusion_matrix
            )
            from sklearn.model_selection import (
                train_test_split, RandomizedSearchCV, StratifiedKFold
            )
            from sklearn.preprocessing import OrdinalEncoder
            from xgboost import XGBClassifier
            from imblearn.over_sampling import SMOTE
            from imblearn.pipeline import Pipeline as ImbPipeline

            logger.info('Starting model training process')

            # Data ingestion and feature engineering
            df = self.ingest_data()
            data = self.create_features(df)

            X = data.drop(columns=['is_fraud'])
            y = data['is_fraud']

            # Class imbalance safeguards
            if y.sum() == 0:
                raise ValueError('No positive samples in training data')
            if y.sum() < 10:
                logger.warning('Low positive samples: %d. Consider additional data augmentation', y.sum())

            categorical_cols = X.select_dtypes(include=['object', 'string']).columns.tolist()
            numeric_cols = X.select_dtypes(include=[np.number]).columns.tolist()
            
            logger.info('Feature types - Numeric: %d, Categorical: %d', len(numeric_cols), len(categorical_cols))

            X_train, X_test, y_train, y_test = train_test_split(
                X, y,
                test_size=self.config.get('model', {}).get('test_size', 0.2),
                stratify=y,
                random_state=self.config.get('model', {}).get('seed', 42)
            )

            # Robustly start an MLflow run with retries to handle transient name-resolution/connectivity issues
            run = None
            max_mlflow_retries = self.config.get('api', {}).get('retries', 5)
            backoff = self.config.get('api', {}).get('backoff_factor', 2)
            for attempt in range(1, max_mlflow_retries + 1):
                try:
                    run = mlflow.start_run()
                    break
                except Exception as e:
                    logger.warning('MLflow start_run attempt %d/%d failed: %s', attempt, max_mlflow_retries, e)
                    if attempt == max_mlflow_retries:
                        raise
                    time.sleep(backoff ** (attempt - 1))

            try:
                mlflow.log_metrics({
                    'train_samples': X_train.shape[0],
                    'positive_samples': int(y_train.sum()),
                    'class_ratio': float(y_train.mean()),
                    'test_samples': X_test.shape[0],
                    'num_features': len(X_train.columns),
                    'num_categorical': len(categorical_cols),
                    'num_numeric': len(numeric_cols)
                })

                transformers = []
                if categorical_cols:
                    cat_cols_to_encode = categorical_cols[:5]
                    for col in cat_cols_to_encode:
                        transformers.append((
                            f'{col}_encoder',
                            OrdinalEncoder(
                                handle_unknown='use_encoded_value',
                                unknown_value=-1,
                                dtype=np.float32
                            ),
                            [col]
                        ))
                
                if transformers:
                    preprocessor = ColumnTransformer(transformers, remainder='passthrough')
                else:
                    from sklearn.preprocessing import FunctionTransformer
                    preprocessor = FunctionTransformer(func=lambda x: x, validate=False)

                xgb = XGBClassifier(
                    eval_metric='aucpr',
                    random_state=self.config.get('model', {}).get('seed', 42),
                    reg_lambda=1.0,
                    n_estimators=self.config.get('model', {}).get('params', {}).get('n_estimators', 100),
                    n_jobs=-1,
                    tree_method=self.config.get('model', {}).get('tree_method', 'hist')
                )

                # Use sequential processing (n_jobs=1) to avoid DB connection pool exhaustion
                # during cross-validation. Parallel joblib subprocesses consume all available connections.
                pipeline = ImbPipeline([
                    ('preprocessor', preprocessor),
                    ('smote', SMOTE(random_state=self.config.get('model', {}).get('seed', 42))),
                    ('classifier', xgb)
                ])

                param_dist = {
                    'classifier__max_depth': [3, 5, 7],
                    'classifier__learning_rate': [0.01, 0.05, 0.1],
                    'classifier__subsample': [0.6, 0.8, 1.0],
                    'classifier__colsample_bytree': [0.6, 0.8, 1.0],
                    'classifier__gamma': [0, 0.1, 0.3],
                    'classifier__reg_alpha': [0, 0.1, 0.5]
                }

                searcher = RandomizedSearchCV(
                    pipeline,
                    param_dist,
                    n_iter=20,
                    scoring=make_scorer(fbeta_score, beta=2, zero_division=0),
                    cv=StratifiedKFold(n_splits=3, shuffle=True),
                    n_jobs=1,
                    refit=True,
                    error_score='raise',
                    random_state=self.config.get('model', {}).get('seed', 42),
                    verbose=1
                )

                logger.info('Starting hyperparameter tuning...')
                searcher.fit(X_train, y_train)
                best_model = searcher.best_estimator_
                best_params = searcher.best_params_
                logger.info('Best hyperparameters: %s', best_params)

                train_proba = best_model.predict_proba(X_train)[:, 1]
                precision_arr, recall_arr, thresholds_arr = precision_recall_curve(y_train, train_proba)
                f1_scores = [2 * (p * r) / (p + r) if (p + r) > 0 else 0 for p, r in
                             zip(precision_arr[:-1], recall_arr[:-1])]
                best_threshold = thresholds_arr[np.argmax(f1_scores)] if len(thresholds_arr) > 0 else 0.5
                logger.info('Optimal threshold determined: %.4f', best_threshold)

                test_proba = best_model.predict_proba(X_test)[:, 1]
                y_pred = (test_proba >= best_threshold).astype(int)

                metrics = {
                    'auc_pr': float(average_precision_score(y_test, test_proba)),
                    'precision': float(precision_score(y_test, y_pred, zero_division=0)),
                    'recall': float(recall_score(y_test, y_pred, zero_division=0)),
                    'f1': float(f1_score(y_test, y_pred, zero_division=0)),
                    'threshold': float(best_threshold)
                }

                mlflow.log_metrics(metrics)
                mlflow.log_params(best_params)

                cm = confusion_matrix(y_test, y_pred)
                plt.figure(figsize=(6, 4))
                plt.imshow(cm, interpolation='nearest', cmap=plt.cm.Blues)
                plt.title('Confusion Matrix')
                plt.colorbar()
                tick_marks = np.arange(2)
                plt.xticks(tick_marks, ['Not Fraud', 'Fraud'])
                plt.yticks(tick_marks, ['Not Fraud', 'Fraud'])

                for i in range(2):
                    for j in range(2):
                        plt.text(j, i, format(cm[i, j], 'd'), ha='center', va='center', color='red')

                plt.tight_layout()
                cm_filename = 'confusion_matrix.png'
                plt.savefig(cm_filename)
                mlflow.log_artifact(cm_filename)
                plt.close()

                plt.figure(figsize=(10, 6))
                plt.plot(recall_arr, precision_arr, marker='.', label='Precision-Recall Curve')
                plt.xlabel('Recall')
                plt.ylabel('Precision')
                plt.title('Precision-Recall Curve')
                plt.legend()
                pr_filename = 'precision_recall_curve.png'
                plt.savefig(pr_filename)
                mlflow.log_artifact(pr_filename)
                plt.close()
            finally:
                try:
                    if run is not None:
                        mlflow.end_run()
                except Exception:
                    logger.debug('Failed to properly end MLflow run')

                signature = infer_signature(X_train, y_pred)
                mlflow.sklearn.log_model(
                    sk_model=best_model,
                    artifact_path='model',
                    signature=signature,
                    registered_model_name='fraud_detection_model'
                )

                os.makedirs('/app/models', exist_ok=True)
                joblib.dump(best_model, '/app/models/fraud_detection_model.pkl')

                logger.info('Training successfully completed with metrics: %s', metrics)
                
                # Explicit cleanup to release resources and database connections
                import gc
                del searcher, pipeline, X_train, X_test, y_train, y_test
                gc.collect()

                return best_model, metrics

        except Exception as e:
            logger.error('Training failed: %s', str(e), exc_info=True)
            raise


if __name__ == '__main__':
    # Configure logging and signal handlers only when running as a script
    logging.basicConfig(
        format="%(asctime)s - %(levelname)s - %(module)s - %(message)s",
        level=logging.INFO,
        handlers=[
            logging.FileHandler('./fraud_detection_model.log'),
            logging.StreamHandler()
        ]
    )
    signal.signal(signal.SIGTERM, _sigterm_handler)
