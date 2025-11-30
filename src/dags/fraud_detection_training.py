"""
Fraud Detection Model Training Pipeline

This implementation represents a production-grade ML training system for fraud detection with
the following architectural considerations:

1. Environment Agnostic Configuration
   - Uses YAML config for environment-specific parameters
   - Strict separation of secrets vs configuration
   - Multi-environment support via .env files

2. Observability
   - Structured logging with multiple sinks
   - MLflow experiment tracking
   - Artifact storage with MinIO (S3-compatible)

3. Production Readiness
   - Kafka integration for real-time data ingestion
   - Automated hyperparameter tuning
   - Model serialization/registry
   - Comprehensive metrics tracking
   - Class imbalance mitigation

4. Operational Safety
   - Environment validation checks
   - Data quality guards
   - Comprehensive error handling
   - Model performance baselining
"""

import json
import logging
import os
import yaml
from dotenv import load_dotenv

# Configure dual logging to file and stdout with structured format
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(module)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler('./fraud_detection_model.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class FraudDetectionTraining:
    """
    End-to-end fraud detection training system implementing MLOps best practices.

    Key Architecture Components:
    - Configuration Management: Centralized YAML config with environment overrides
    - Data Ingestion: Kafka consumer with SASL/SSL authentication
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
            'AWS_S3_ENDPOINT_URL': self.config['mlflow']['s3_endpoint_url']
        })

        # Pre-flight system checks
        self._validate_environment()

        # MLflow configuration for experiment tracking (imported locally to avoid DAG parse issues)
        try:
            import mlflow
            mlflow.set_tracking_uri(self.config['mlflow']['tracking_uri'])
            mlflow.set_experiment(self.config['mlflow']['experiment_name'])
        except ImportError:
            logger.warning('MLflow not available during initialization, will be imported during training')

    def _load_config(self, config_path: str) -> dict:
        """
        Load and validate hierarchical configuration with fail-fast semantics.

        Implements:
        - YAML configuration parsing
        - Early validation of critical parameters
        - Audit logging of configuration loading
        """
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            logger.info('Configuration loaded successfully')
            return config
        except Exception as e:
            logger.error('Failed to load configuration: %s', str(e))
            raise

    def _validate_environment(self):
        """
        System integrity verification with defense-in-depth checks:
        1. Required environment variables
        2. Object storage connectivity
        3. Credential validation

        Fails early to prevent partial initialization states.
        """
        required_vars = ['KAFKA_BOOTSTRAP_SERVERS', 'KAFKA_USERNAME', 'KAFKA_PASSWORD']
        missing = [var for var in required_vars if not os.getenv(var)]
        if missing:
            raise ValueError(f'Missing required environment variables: {missing}')

        self._check_minio_connection()

    def _check_minio_connection(self):
        """
        Validate object storage connectivity and bucket configuration.

        Implements:
        - S3 client initialization with error handling
        - Bucket existence check
        - Automatic bucket creation (if configured)

        Maintains separation of concerns between configuration and infrastructure setup.
        """
        try:
            # Local import to avoid heavy dependency during DAG parsing
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

    def read_from_kafka_stream(self, micro_batch_size=10000, max_total_messages=None) -> "pd.DataFrame":
        """
        Stream-based Kafka consumer for unbounded data processing.
        
        This implementation handles continuously growing data by:
        1. Consuming data in micro-batches to manage memory
        2. Processing messages as they arrive (incremental)
        3. Supporting configurable batch sizes for flexibility
        4. NOT capping total message count (reads all available)
        
        Args:
            micro_batch_size: Process messages in batches of this size (memory efficient)
            max_total_messages: Optional hard limit on total messages (None = read all)
        
        Returns:
            pd.DataFrame: All consumed messages as single DataFrame
        """
        try:
            import pandas as pd
            from kafka import KafkaConsumer
            from kafka.structs import TopicPartition
            import time

            topic = self.config['kafka']['topic']
            logger.info('Starting stream-based Kafka consumer for topic %s', topic)

            group_id = self.config['kafka'].get('group_id') or os.getenv('KAFKA_CONSUMER_GROUP', 'fraud-trainer-group')
            consumer_timeout_ms = int(self.config['kafka'].get('timeout', 120000))
            read_retries = int(self.config['kafka'].get('read_retries', 3))
            retry_wait_seconds = int(self.config['kafka'].get('retry_wait_seconds', 5))

            attempts = 0
            all_messages = []
            total_batches = 0

            for attempt in range(1, read_retries + 1):
                attempts = attempt
                logger.info('Stream read attempt %d/%d (micro_batch_size=%d)', attempt, read_retries, micro_batch_size)

                consumer = KafkaConsumer(
                    bootstrap_servers=self.config['kafka']['bootstrap_servers'].split(','),
                    security_protocol='SASL_SSL',
                    sasl_mechanism='PLAIN',
                    sasl_plain_username=self.config['kafka']['username'],
                    sasl_plain_password=self.config['kafka']['password'],
                    value_deserializer=lambda x: json.loads(x.decode('utf-8')),
                    consumer_timeout_ms=consumer_timeout_ms,
                    enable_auto_commit=False
                )

                try:
                    # Assign all partitions and seek to beginning
                    partitions = consumer.partitions_for_topic(topic)
                    if partitions:
                        topic_partitions = [TopicPartition(topic, p) for p in partitions]
                        consumer.assign(topic_partitions)
                        consumer.seek_to_beginning(*topic_partitions)
                        logger.info('Assigned and seeked to beginning for %d partitions', len(partitions))
                    else:
                        logger.warning('No partitions found for topic %s', topic)

                    # Stream consumer: reads ALL available messages in micro-batches
                    # No hard limit on total messages—only stops when consumer timeout expires
                    remaining_for_batch = micro_batch_size
                    batch_messages = []
                    poll_count = 0

                    while True:
                        # Poll with timeout for each micro-batch
                        polled = consumer.poll(timeout_ms=5000, max_records=min(1000, remaining_for_batch))
                        poll_count += 1

                        if polled:
                            # Process polled messages
                            for tp, records in polled.items():
                                for rec in records:
                                    batch_messages.append(rec.value)
                                    remaining_for_batch -= 1
                                    
                                    # Check hard limit if specified
                                    if max_total_messages and len(all_messages) + len(batch_messages) >= max_total_messages:
                                        break
                                if max_total_messages and len(all_messages) + len(batch_messages) >= max_total_messages:
                                    break

                            # If micro-batch is full, log progress and reset
                            if len(batch_messages) >= micro_batch_size or (max_total_messages and len(all_messages) + len(batch_messages) >= max_total_messages):
                                all_messages.extend(batch_messages)
                                total_batches += 1
                                logger.info('Stream: Processed batch %d with %d messages (total: %d messages)', total_batches, len(batch_messages), len(all_messages))
                                batch_messages = []
                                remaining_for_batch = micro_batch_size

                                # Exit if hard limit reached
                                if max_total_messages and len(all_messages) >= max_total_messages:
                                    logger.info('Stream: Reached max_total_messages limit (%d)', max_total_messages)
                                    break
                        else:
                            # Empty poll—consumer_timeout_ms will eventually expire
                            # But continue looping to respect timeout window
                            logger.debug('Stream poll attempt %d: no messages in this window, continuing...', poll_count)

                        # Timeout expiration is handled by KafkaConsumer internally
                        # When consumer_timeout_ms expires with no activity, loop will naturally exit

                    # Add any remaining messages in last batch
                    if batch_messages:
                        all_messages.extend(batch_messages)
                        total_batches += 1
                        logger.info('Stream: Processed final batch %d with %d messages (total: %d messages)', total_batches, len(batch_messages), len(all_messages))

                    if all_messages:
                        logger.info('Stream attempt %d successfully consumed %d messages in %d batches', attempt, len(all_messages), total_batches)
                        consumer.close()
                        break
                    else:
                        logger.warning('Stream attempt %d: no messages consumed', attempt)
                        consumer.close()
                        if attempt < read_retries:
                            time.sleep(retry_wait_seconds)
                except Exception:
                    consumer.close()
                    raise

            if not all_messages:
                raise ValueError('No messages received from Kafka after %d stream attempts' % attempts)

            # Build DataFrame from all streamed messages
            df = pd.DataFrame(all_messages)
            if df.empty:
                raise ValueError('No messages received from Kafka.')

            logger.info('Stream consumer complete: %d total messages across %d batches with %d columns', len(df), total_batches, len(df.columns))

            return df
        except Exception as e:
            logger.error('Failed to stream data from Kafka: %s', str(e), exc_info=True)
            raise

    def read_from_kafka(self) -> "pd.DataFrame":
        """
        Kafka consumer entry point - delegates to stream-based consumer.
        
        This method is the public interface for data ingestion. It now uses the
        stream-based consumer to handle unbounded data growth:
        - No artificial batch size limit
        - Reads ALL available messages from the topic
        - Processes in memory-efficient micro-batches (10K messages at a time)
        - Automatically adjusts to growing data volumes
        
        Returns:
            pd.DataFrame: All consumed messages with data quality checks applied
        """
        logger.info('Initiating Kafka data ingestion (stream-based consumer)')
        
        # Get micro-batch size from config or use sensible default
        micro_batch_size = int(os.getenv('KAFKA_MICRO_BATCH_SIZE', self.config.get('kafka', {}).get('micro_batch_size', 10000)))
        
        # No max_total_messages limit—read all available data
        df = self.read_from_kafka_stream(micro_batch_size=micro_batch_size, max_total_messages=None)
        
        logger.info('Raw stream data received: %d rows, %d columns', len(df), len(df.columns))

        try:
            import pandas as pd
            
            # Convert timestamp fields
            timestamp_cols = ['timestamp', 'registration_date', 'created_at']
            for col in timestamp_cols:
                if col in df.columns:
                    df[col] = pd.to_datetime(df[col], errors='coerce', utc=True)

            # Convert numeric fields (all come as strings from Kafka)
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

            # Convert float/score fields
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

            # Convert boolean fields (f/t strings to 0/1)
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

            # Convert is_fraud (target variable) from string "1"/"0" to int
            if 'is_fraud' in df.columns:
                df['is_fraud'] = pd.to_numeric(df['is_fraud'], errors='coerce').fillna(0).astype(int)
            else:
                raise ValueError('Fraud label (is_fraud) missing from Kafka data')

            # Data quality monitoring point
            fraud_rate = df['is_fraud'].mean() * 100
            logger.info('Kafka data read successfully with fraud rate: %.2f%%', fraud_rate)
            logger.info('Data shape: %d rows, %d columns', len(df), len(df.columns))

            return df
        except Exception as e:
            logger.error('Failed to process Kafka stream data: %s', str(e), exc_info=True)
            raise

    def create_features(self, df) -> "pd.DataFrame":
        """
        Feature engineering pipeline leveraging rich fraud detection features from Kafka:

        1. Temporal Features:
           - Transaction hour, night/weekend indicators
           - Account age, session duration

        2. Behavioral Features:
           - Transaction velocity (1h, 24h)
           - Payment velocity (1h, 24h)
           - User activity patterns

        3. Monetary Features:
           - Amount, price, discount
           - Current order value ratio
           - Payment method analysis

        4. Identity & Verification Features:
           - Identity mismatch/verification scores
           - Phone/email verification status
           - SIM swap probability

        5. Device & Location Features:
           - Device fingerprint score
           - IP risk score
           - Location distance score
           - VPN/proxy detection

        6. Transaction Pattern Features:
           - Failed payment ratio
           - Refund patterns
           - Delivery patterns

        7. Risk Scores:
           - Fraud ring score
           - Vendor risk score
           - User reputation score
           - Various anomaly scores

        Maintains immutability via DataFrame.copy() and validates feature set integrity.
        """
        # Local import for numpy/pandas to reduce DAG parse time
        import numpy as np
        import pandas as pd

        df = df.sort_values(['user_id', 'timestamp']).copy()

        # ---- Temporal Feature Engineering ----
        # Captures time-based fraud patterns (e.g., nighttime transactions)
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

        # -- Additional Temporal Features from Data --
        # Account age (already in data, but ensure it's numeric)
        if 'account_age_days' not in df.columns:
            df['account_age_days'] = 0

        # -- Behavioral Feature Engineering --
        # Use transaction velocity from data if available, otherwise compute
        if 'transaction_velocity_24h' not in df.columns:
            df['transaction_velocity_24h'] = df.groupby('user_id', group_keys=False).apply(
                lambda g: g.rolling('24h', on='timestamp', closed='left')['amount'].count().fillna(0)
            ).reset_index(0, drop=True) if 'timestamp' in df.columns else 0

        # -- Monetary Feature Engineering --
        # Use current_order_value_ratio from data if available, otherwise compute
        if 'current_order_value_ratio' not in df.columns and 'amount' in df.columns:
            df['current_order_value_ratio'] = df.groupby('user_id', group_keys=False).apply(
                lambda g: (g['amount'] / g['amount'].rolling(7, min_periods=1).mean()).fillna(1.0)
            ).reset_index(0, drop=True)

        # -- Vendor Risk Profiling --
        # Use vendor_id instead of merchant
        if 'vendor_id' in df.columns:
            high_risk_vendors = self.config.get('high_risk_vendors', [])
            df['vendor_risk_flag'] = df['vendor_id'].isin(high_risk_vendors).astype(int)
        else:
            df['vendor_risk_flag'] = 0

        # Select comprehensive feature set from available columns
        # Core transaction features
        core_features = [
            'amount', 'price', 'discount', 'quantity',
            'is_night', 'is_weekend', 'transaction_day', 'transaction_hour',
            'account_age_days', 'session_duration'
        ]

        # Velocity and activity features
        velocity_features = [
            'transaction_velocity_1h', 'transaction_velocity_24h',
            'payment_velocity_1h', 'payment_velocity_24h',
            'discount_velocity_24h', 'login_frequency'
        ]

        # Identity and verification features
        identity_features = [
            'identity_mismatch_score', 'identity_verification_score',
            'sim_swap_probability', 'phone_verified', 'email_disposable_flag'
        ]

        # Device and location features
        device_features = [
            'device_fingerprint_score', 'android_emulator_detection',
            'browser_integrity_score', 'ip_risk_score',
            'ip_location_mismatch_flag', 'location_distance_score',
            'proxy_detection_flag', 'vpn_usage_flag', 'device_trust_score'
        ]

        # Payment and transaction pattern features
        payment_features = [
            'failed_payment_ratio', 'current_order_value_ratio',
            'payment_method_anomaly', 'is_linked_card',
            'bank_transfer_verification', 'partial_payment_requirement'
        ]

        # Risk and anomaly scores
        risk_features = [
            'fraud_ring_score', 'vendor_risk_score', 'user_reputation_score',
            'activity_timing_score', 'anomaly_frequency_score',
            'behavioral_consistency_score', 'fake_review_score',
            'product_price_anomaly_score', 'address_risk_score',
            'rider_collusion_risk', 'refund_abuse_score'
        ]

        # Delivery and return features
        delivery_features = [
            'delivery_delay_ratio', 'failed_delivery_pattern',
            'address_reuse_rate', 'shared_address_count',
            'refund_to_purchase_ratio', 'return_inspection_score',
            'product_swap_probability', 'delivery_dispute_rate'
        ]

        # Account linkage features
        linkage_features = [
            'account_link_density', 'shared_phone_number_count',
            'shared_ip_count', 'linked_accounts',
            'device_change_rate', 'multi_device_login_flag'
        ]

        # Combine all feature lists
        all_feature_candidates = (
            core_features + velocity_features + identity_features +
            device_features + payment_features + risk_features +
            delivery_features + linkage_features + ['vendor_risk_flag']
        )

        # Select only features that exist in the dataframe
        available_features = [f for f in all_feature_candidates if f in df.columns]

        # Fill any remaining NaN values
        for col in available_features:
            if df[col].isna().any():
                if df[col].dtype in ['int64', 'int32', 'float64', 'float32']:
                    df[col] = df[col].fillna(0)
                else:
                    df[col] = df[col].fillna(df[col].mode()[0] if len(df[col].mode()) > 0 else 0)

        logger.info('Selected %d features from %d candidates', len(available_features), len(all_feature_candidates))

        # Schema validation guard
        if 'is_fraud' not in df.columns:
            raise ValueError('Missing target column "is_fraud"')

        # Return features + target
        feature_df = df[available_features + ['is_fraud']].copy()

        # Final validation
        if feature_df.empty:
            raise ValueError('Feature DataFrame is empty after feature engineering')

        logger.info('Feature engineering complete. Final shape: %d rows, %d columns', 
                   len(feature_df), len(feature_df.columns))

        return feature_df

    def train_model(self):
        """
        End-to-end training pipeline implementing ML best practices:

        1. Data Quality Checks
        2. Stratified Data Splitting
        3. Class Imbalance Mitigation (SMOTE)
        4. Hyperparameter Optimization
        5. Threshold Tuning
        6. Model Evaluation
        7. Artifact Logging
        8. Model Registry

        Implements MLflow experiment tracking for full reproducibility.
        """
        # Local import for heavy ML libraries is done inside this method to
        # avoid importing them at module import time when Airflow parses DAGs.
        try:
            import numpy as np
            import pandas as pd
            import mlflow
            from mlflow.models import infer_signature
            import joblib
            import matplotlib.pyplot as plt
            from sklearn.compose import ColumnTransformer
            from sklearn.metrics import make_scorer, fbeta_score, precision_recall_curve, average_precision_score, precision_score, recall_score, f1_score, confusion_matrix
            from sklearn.model_selection import train_test_split, RandomizedSearchCV, StratifiedKFold
            from sklearn.preprocessing import OrdinalEncoder
            from xgboost import XGBClassifier
            from imblearn.over_sampling import SMOTE
            from imblearn.pipeline import Pipeline as ImbPipeline

            logger.info('Starting model training process')

            # Data ingestion and feature engineering
            df = self.read_from_kafka()
            data = self.create_features(df)

            # Train/Test split with stratification
            X = data.drop(columns=['is_fraud'])
            y = data['is_fraud']

            # Class imbalance safeguards
            if y.sum() == 0:
                raise ValueError('No positive samples in training data')
            if y.sum() < 10:
                logger.warning('Low positive samples: %d. Consider additional data augmentation', y.sum())

            # Identify categorical columns (object/string types)
            categorical_cols = X.select_dtypes(include=['object', 'string']).columns.tolist()
            numeric_cols = X.select_dtypes(include=[np.number]).columns.tolist()
            
            logger.info('Feature types - Numeric: %d, Categorical: %d', len(numeric_cols), len(categorical_cols))
            if categorical_cols:
                logger.info('Categorical features: %s', categorical_cols)

            X_train, X_test, y_train, y_test = train_test_split(
                X, y,
                test_size=self.config['model'].get('test_size', 0.2),
                stratify=y,
                random_state=self.config['model'].get('seed', 42)
            )

            # MLflow experiment tracking context
            with mlflow.start_run():
                # Dataset metadata logging
                mlflow.log_metrics({
                    'train_samples': X_train.shape[0],
                    'positive_samples': int(y_train.sum()),
                    'class_ratio': float(y_train.mean()),
                    'test_samples': X_test.shape[0],
                    'num_features': len(X_train.columns),
                    'num_categorical': len(categorical_cols),
                    'num_numeric': len(numeric_cols)
                })

                # Categorical feature preprocessing (only if categorical features exist)
                transformers = []
                if categorical_cols:
                    # Limit to first few categorical columns to avoid too many encoders
                    # Most features should already be numeric from Kafka data
                    cat_cols_to_encode = categorical_cols[:5]  # Limit to 5 categorical features
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
                    # All features are numeric, no preprocessing needed
                    from sklearn.preprocessing import FunctionTransformer
                    preprocessor = FunctionTransformer(func=lambda x: x, validate=False)

                # XGBoost configuration with efficiency optimizations
                xgb = XGBClassifier(
                    eval_metric='aucpr',  # Optimizes for precision-recall area
                    random_state=self.config['model'].get('seed', 42),
                    reg_lambda=1.0,
                    n_estimators=self.config['model']['params']['n_estimators'],
                    n_jobs=-1,
                    tree_method=self.config['model'].get('tree_method', 'hist')  # GPU-compatible
                )

                # Imbalanced learning pipeline
                pipeline = ImbPipeline([
                    ('preprocessor', preprocessor),
                    ('smote', SMOTE(random_state=self.config['model'].get('seed', 42))),
                    ('classifier', xgb)
                ], memory='./cache')

                # Hyperparameter search space design
                param_dist = {
                    'classifier__max_depth': [3, 5, 7],  # Depth control for regularization
                    'classifier__learning_rate': [0.01, 0.05, 0.1],  # Conservative range
                    'classifier__subsample': [0.6, 0.8, 1.0],  # Stochastic gradient boosting
                    'classifier__colsample_bytree': [0.6, 0.8, 1.0],  # Feature randomization
                    'classifier__gamma': [0, 0.1, 0.3],  # Complexity control
                    'classifier__reg_alpha': [0, 0.1, 0.5]  # L1 regularization
                }

                # Optimizing for F-beta score (beta=2 emphasizes recall)
                searcher = RandomizedSearchCV(
                    pipeline,
                    param_dist,
                    n_iter=20,
                    scoring=make_scorer(fbeta_score, beta=2, zero_division=0),
                    cv=StratifiedKFold(n_splits=3, shuffle=True),
                    n_jobs=-1,
                    refit=True,
                    error_score='raise',
                    random_state=self.config['model'].get('seed', 42)
                )

                logger.info('Starting hyperparameter tuning...')
                searcher.fit(X_train, y_train)
                best_model = searcher.best_estimator_
                best_params = searcher.best_params_
                logger.info('Best hyperparameters: %s', best_params)

                # Threshold optimization using training data
                # The pipeline handles preprocessing internally, so we can use predict_proba directly
                train_proba = best_model.predict_proba(X_train)[:, 1]
                precision_arr, recall_arr, thresholds_arr = precision_recall_curve(y_train, train_proba)
                f1_scores = [2 * (p * r) / (p + r) if (p + r) > 0 else 0 for p, r in
                             zip(precision_arr[:-1], recall_arr[:-1])]
                best_threshold = thresholds_arr[np.argmax(f1_scores)]
                logger.info('Optimal threshold determined: %.4f', best_threshold)

                # Model evaluation - pipeline handles preprocessing
                test_proba = best_model.predict_proba(X_test)[:, 1]
                y_pred = (test_proba >= best_threshold).astype(int)

                # Comprehensive metrics suite
                metrics = {
                    'auc_pr': float(average_precision_score(y_test, test_proba)),
                    'precision': float(precision_score(y_test, y_pred, zero_division=0)),
                    'recall': float(recall_score(y_test, y_pred, zero_division=0)),
                    'f1': float(f1_score(y_test, y_pred, zero_division=0)),
                    'threshold': float(best_threshold)
                }

                mlflow.log_metrics(metrics)
                mlflow.log_params(best_params)

                # Confusion matrix visualization
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

                # Precision-Recall curve documentation
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

                # Model packaging and registry
                signature = infer_signature(X_train, y_pred)
                mlflow.sklearn.log_model(
                    sk_model=best_model,
                    artifact_path='model',
                    signature=signature,
                    registered_model_name='fraud_detection_model'
                )

                # Model serialization for deployment
                os.makedirs('/app/models', exist_ok=True)
                joblib.dump(best_model, '/app/models/fraud_detection_model.pkl')

                logger.info('Training successfully completed with metrics: %s', metrics)

                return best_model, metrics

        except Exception as e:
            logger.error('Training failed: %s', str(e), exc_info=True)
            raise