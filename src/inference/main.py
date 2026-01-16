"""
Fraud Detection Inference Service

This script reads transaction data from the Fraud Detection API,
applies a pre-trained XGBoost model to detect fraudulent transactions,
and logs predictions with confidence scores.

Data Flow:
1. Fetch transactions from FRAUD_API_URL with pagination
2. Apply feature engineering (same features used in training)
3. Load the trained fraud detection model
4. Generate predictions and probability scores
5. Log results to console and optionally to database/file
6. Return fraud detection results with confidence metrics

The inference pipeline is designed for batch processing and can be:
- Scheduled periodically via Airflow
- Called via REST API endpoint
- Run as a standalone batch job
"""

import json
import logging
import os
import sys
from datetime import datetime
from typing import Dict, List, Tuple, Optional

import joblib
import numpy as np
import pandas as pd
import requests
import yaml
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Configure structured logging with timestamps and level indicators
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler('./fraud_detection_inference.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class FraudDetectionInference:
    """
    Fraud detection inference pipeline for HTTP API-based data sources.

    This class handles the complete inference workflow:
    - Configuration management from YAML
    - API data ingestion with resilient pagination
    - Feature engineering (matching training pipeline)
    - Model loading and prediction
    - Results aggregation and reporting

    Architecture Design:
    - Stateless: No message queue dependencies (unlike Kafka approach)
    - Batch processing: Handles paginated API responses efficiently
    - Feature parity: Uses identical feature engineering as training pipeline
    - Model compatibility: Works with sklearn/XGBoost pipeline serialized via joblib

    Attributes:
        config (dict): Configuration parameters from YAML
        model: Loaded scikit-learn/XGBoost pipeline
        api_url (str): Fraud Detection API endpoint
        max_batch_size (int): Maximum records per API request
    """

    def __init__(self, config_path: str = '/app/config.yaml'):
        """
        Initialize inference pipeline with configuration.

        Args:
            config_path (str): Path to YAML configuration file
        """
        # Load environment variables from .env file
        load_dotenv(dotenv_path='/app/.env')

        # Load configuration from YAML
        self.config = self._load_config(config_path)

        # Initialize API and model parameters
        self.api_url = os.getenv('FRAUD_API_URL', self.config['api']['url'])
        self.max_batch_size = int(os.getenv('FRAUD_API_MAX_BATCH_SIZE', 
                                            self.config['api'].get('max_batch_size', 10000)))

        # Load pre-trained fraud detection model (lazy-loaded on first use)
        self.model = None
        self.model_version = None
        self.model_source = None
        self.last_model_refresh = None
        self.model_path = self.config['model']['path']
        self.model_refresh_seconds = int(
            os.getenv(
                'MLFLOW_MODEL_REFRESH_SECONDS',
                self.config.get('mlflow', {}).get('refresh_seconds', 60)
            )
        )
        self._load_model_if_exists()

        # Classification threshold (tuned during training)
        self.threshold = float(self.config['model'].get('threshold', 0.5))

        logger.info('Inference pipeline initialized with config: %s', config_path)
        logger.info('Using API: %s', self.api_url[:60] + '...')
        logger.info('Classification threshold: %.4f', self.threshold)

    def _load_model_if_exists(self):
        """
        Attempt to load model from MLflow first, then fall back to local file.
        This allows the service to start even if training hasn't completed yet.
        """
        self.refresh_model(force=True)
        if self.model is None:
            self._load_local_model()

    def _load_local_model(self):
        try:
            if os.path.exists(self.model_path):
                self.model = joblib.load(self.model_path)
                self.model_version = 'local'
                self.model_source = 'local'
                logger.info('Model loaded successfully from local path: %s', self.model_path)
            else:
                logger.warning('Model file not found at %s. Service is ready but model inference unavailable. Please run the Airflow training DAG.', self.model_path)
        except Exception as e:
            logger.warning('Error loading model from local path: %s. Service will start but inference unavailable.', str(e))

    def refresh_model(self, force: bool = False) -> bool:
        """
        Refresh model from MLflow if a newer version is available.
        Returns True if a new model was loaded.
        """
        now = datetime.now()
        if not force and self.last_model_refresh:
            elapsed = (now - self.last_model_refresh).total_seconds()
            if elapsed < self.model_refresh_seconds:
                return False

        self.last_model_refresh = now

        try:
            import mlflow
            mlflow.set_tracking_uri(self.config['mlflow']['tracking_uri'])

            registered_model_name = self.config['mlflow'].get('registered_model_name', 'fraud_detection_model')
            client = mlflow.tracking.MlflowClient()
            latest_versions = client.get_latest_versions(
                registered_model_name,
                stages=["None", "Staging", "Production"]
            )

            if not latest_versions:
                logger.warning('No model versions found in MLflow for %s', registered_model_name)
                return False

            latest = latest_versions[0]
            latest_version = str(latest.version)
            if self.model is not None and str(self.model_version) == latest_version:
                return False

            model_uri = f"models:/{registered_model_name}/{latest_version}"
            logger.info('Loading model from MLflow: %s', model_uri)
            try:
                self.model = mlflow.sklearn.load_model(model_uri)
            except Exception as load_error:
                # If MLflow load fails (version mismatch), try downloading artifact directly
                logger.warning('MLflow sklearn.load_model failed: %s. Trying direct artifact download...', str(load_error))
                try:
                    import tempfile
                    import shutil
                    with tempfile.TemporaryDirectory() as tmpdir:
                        mlflow.artifacts.download_artifacts(artifact_uri=model_uri, dst_path=tmpdir)
                        # Look for model.pkl in downloaded artifacts
                        model_file = os.path.join(tmpdir, 'model.pkl')
                        if not os.path.exists(model_file):
                            # Try finding any .pkl file
                            for root, dirs, files in os.walk(tmpdir):
                                for f in files:
                                    if f.endswith('.pkl'):
                                        model_file = os.path.join(root, f)
                                        break
                        if os.path.exists(model_file):
                            self.model = joblib.load(model_file)
                            logger.info('Model loaded via direct artifact download')
                        else:
                            raise FileNotFoundError('No model.pkl found in MLflow artifacts')
                except Exception as fallback_error:
                    logger.error('Both MLflow load methods failed. Original: %s, Fallback: %s', str(load_error), str(fallback_error))
                    raise load_error
            
            self.model_version = latest_version
            self.model_source = 'mlflow'
            logger.info('Model loaded successfully from MLflow (version %s)', latest_version)

            try:
                os.makedirs(os.path.dirname(self.model_path), exist_ok=True)
                joblib.dump(self.model, self.model_path)
                logger.info('Model cached to local path: %s', self.model_path)
            except Exception as e:
                logger.warning('Failed to cache model locally: %s', str(e))

            return True

        except ImportError:
            logger.warning('MLflow not available. Skipping refresh.')
            return False
        except Exception as e:
            logger.warning('Error accessing MLflow: %s', str(e))
            return False

    def _load_model(self, model_path: str):
        """
        Load pre-trained fraud detection model from disk.

        Args:
            model_path (str): Path to serialized model file (joblib format)

        Returns:
            model: Loaded scikit-learn/XGBoost pipeline, or None if not found

        Raises:
            Exception: If model loading fails (but FileNotFoundError is handled)
        """
        try:
            model = joblib.load(model_path)
            logger.info('Model loaded successfully from %s', model_path)
            return model
        except FileNotFoundError:
            logger.warning('Model file not found at %s. Have you trained the model yet?', model_path)
            return None
        except Exception as e:
            logger.error('Error loading model: %s', str(e))
            raise

    @staticmethod
    def _load_config(config_path: str) -> dict:
        """
        Load YAML configuration file.

        Args:
            config_path (str): Path to configuration file

        Returns:
            dict: Parsed configuration parameters

        Raises:
            Exception: If file loading or parsing fails
        """
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            logger.info('Configuration loaded successfully from %s', config_path)
            return config
        except FileNotFoundError:
            logger.error('Configuration file not found: %s', config_path)
            raise
        except yaml.YAMLError as e:
            logger.error('Error parsing YAML configuration: %s', str(e))
            raise
        except Exception as e:
            logger.error('Unexpected error loading configuration: %s', str(e))
            raise

    def fetch_transactions_from_api(self, offset: int = 0, limit: int = None) -> Tuple[List[Dict], bool]:
        """
        Fetch transaction data from Fraud Detection API with pagination.

        Handles multiple API response shapes:
        - JSON array of records
        - JSON object with 'data' or 'transactions' key containing array
        - Single record (wrapped in array)

        Implements exponential backoff for transient failures.

        Args:
            offset (int): Starting record offset for pagination
            limit (int): Maximum records to fetch (defaults to max_batch_size)

        Returns:
            Tuple[List[Dict], bool]: (records fetched, end_of_data_reached)

        Raises:
            Exception: If API call fails after retries
        """
        if limit is None:
            limit = self.max_batch_size

        session = requests.Session()
        retries = Retry(total=5, backoff_factor=2, status_forcelist=(500, 502, 503, 504))
        session.mount('https://', HTTPAdapter(max_retries=retries))
        session.mount('http://', HTTPAdapter(max_retries=retries))

        try:
            params = {'offset': offset, 'limit': limit}
            logger.debug('Fetching from API with params: %s', params)

            response = session.get(self.api_url, params=params, timeout=60)
            response.raise_for_status()

            payload = response.json()

            # Normalize response shape
            if isinstance(payload, dict):
                if 'data' in payload and isinstance(payload['data'], list):
                    records = payload['data']
                elif 'transactions' in payload and isinstance(payload['transactions'], list):
                    records = payload['transactions']
                else:
                    lists = [v for v in payload.values() if isinstance(v, list)]
                    records = lists[0] if lists else [payload]
            elif isinstance(payload, list):
                records = payload
            else:
                records = [payload]

            # Determine if we've reached end of data
            end_of_data = len(records) < limit

            logger.info('Fetched %d records from API (offset=%d, end_of_data=%s)', 
                       len(records), offset, end_of_data)

            return records, end_of_data

        except requests.exceptions.RequestException as e:
            logger.error('API request failed: %s', str(e))
            raise

    def ingest_data(self, max_records: int = None) -> pd.DataFrame:
        """
        Ingest transaction data from API via pagination until exhausted or max reached.

        Args:
            max_records (int): Optional hard limit on total records to fetch

        Returns:
            pd.DataFrame: Aggregated transaction data

        Raises:
            Exception: If data ingestion fails
        """
        all_records = []
        offset = 0
        max_records = max_records or int(os.getenv('FRAUD_API_INFERENCE_MAX_RECORDS', 10000))

        logger.info('Starting data ingestion from API (max_records=%d)', max_records)

        while True:
            try:
                records, end_of_data = self.fetch_transactions_from_api(offset=offset)

                if not records:
                    logger.info('No records returned from API at offset %d', offset)
                    break

                all_records.extend(records)

                # Stop if we've reached max records or end of API data
                if len(all_records) >= max_records:
                    all_records = all_records[:max_records]
                    logger.info('Reached max_records limit (%d)', max_records)
                    break

                if end_of_data:
                    logger.info('Reached end of API data at total records: %d', len(all_records))
                    break

                offset += len(records)

            except Exception as e:
                logger.error('Data ingestion failed at offset %d: %s', offset, str(e))
                if all_records:
                    logger.info('Proceeding with %d records ingested so far', len(all_records))
                    break
                else:
                    raise

        if not all_records:
            raise ValueError('No transaction data received from API')

        # Convert to DataFrame
        df = pd.DataFrame(all_records)
        logger.info('Data ingestion complete: %d rows, %d columns', len(df), len(df.columns))

        return df

    def preprocess_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Apply data type conversions matching training pipeline.

        Converts:
        - Timestamps to datetime objects
        - Numeric strings to numbers
        - Boolean strings to integers
        - Handles missing values gracefully

        Args:
            df (pd.DataFrame): Raw transaction data

        Returns:
            pd.DataFrame: Preprocessed data with correct dtypes
        """
        try:
            df = df.copy()

            # Convert timestamp fields
            timestamp_cols = ['timestamp', 'registration_date', 'created_at']
            for col in timestamp_cols:
                if col in df.columns:
                    df[col] = pd.to_datetime(df[col], errors='coerce', utc=True)

            # Convert integer/numeric fields
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

            # Convert boolean fields (string 't'/'f' to 0/1)
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

            logger.info('Data preprocessing complete. Shape: %d rows, %d columns', len(df), len(df.columns))
            return df

        except Exception as e:
            logger.error('Data preprocessing failed: %s', str(e))
            raise

    def engineer_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Apply feature engineering matching training pipeline.

        Constructs features from raw transaction data for model input:
        - Temporal features (hour, day, weekend)
        - Account age and session duration
        - Transaction velocity patterns
        - Payment and delivery patterns
        - Risk scores from data

        Args:
            df (pd.DataFrame): Preprocessed transaction data

        Returns:
            pd.DataFrame: Features ready for model prediction
        """
        try:
            df = df.copy()

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

            # Fill missing numeric defaults
            for col in ['account_age_days', 'session_duration']:
                if col not in df.columns:
                    df[col] = 0

            # Behavioral features (use pre-computed values from API data)
            for col in ['transaction_velocity_24h', 'payment_velocity_24h', 
                       'discount_velocity_24h', 'login_frequency', 'complaint_frequency']:
                if col not in df.columns:
                    df[col] = 0

            # Financial features
            for col in ['amount', 'price', 'discount', 'quantity', 'current_order_value_ratio']:
                if col not in df.columns:
                    df[col] = 0.0

            # Risk and score features
            risk_cols = [
                'identity_mismatch_score', 'identity_verification_score', 'sim_swap_probability',
                'device_fingerprint_score', 'product_price_anomaly_score', 'browser_integrity_score',
                'failed_payment_ratio', 'avg_order_value', 'address_risk_score',
                'location_distance_score', 'address_reuse_rate', 'delivery_delay_ratio',
                'rider_collusion_risk', 'refund_abuse_score', 'refund_to_purchase_ratio',
                'return_inspection_score', 'product_swap_probability', 'fraud_ring_score',
                'account_link_density', 'device_change_rate', 'device_trust_score',
                'ip_risk_score', 'user_reputation_score', 'activity_timing_score',
                'anomaly_frequency_score', 'behavioral_consistency_score', 'vendor_risk_score',
                'fake_review_score', 'delivery_dispute_rate'
            ]
            for col in risk_cols:
                if col not in df.columns:
                    df[col] = 0.0

            # Categorical/boolean features
            bool_cols = [
                'return_request', 'phone_verified', 'android_emulator_detection',
                'unusual_discount_flag', 'cart_tampering_detection', 'payment_method_anomaly',
                'is_linked_card', 'bank_transfer_verification', 'partial_payment_requirement',
                'ip_location_mismatch_flag', 'failed_delivery_pattern', 'otp_delivery_verification',
                'gps_delivery_confirmation', 'serial_number_mismatch', 'multi_device_login_flag',
                'proxy_detection_flag', 'vpn_usage_flag', 'rating_burst_detection',
                'email_disposable_flag'
            ]
            for col in bool_cols:
                if col not in df.columns:
                    df[col] = 0

            # Shared/linked account features
            for col in ['shared_address_count', 'shared_phone_number_count', 'shared_ip_count', 'linked_accounts']:
                if col not in df.columns:
                    df[col] = 0

            logger.info('Feature engineering complete. Total features: %d', len(df.columns))
            return df

        except Exception as e:
            logger.error('Feature engineering failed: %s', str(e))
            raise

    def _clean_feature_name(self, name: str) -> str:
        if '__' in name:
            return name.split('__', 1)[1]
        return name

    def _compute_explanations(self, X: pd.DataFrame, top_k: int = 5):
        """
        Compute per-record top feature contributions using XGBoost pred_contribs.
        Returns list of lists (per row) with {feature, contribution, value}.
        """
        try:
            import xgboost as xgb
        except Exception:
            logger.warning('xgboost not available for explainability.')
            return None

        model = self.model
        if model is None:
            return None

        feature_names = list(X.columns)
        data_for_model = X
        classifier = None

        if hasattr(model, 'named_steps') and 'classifier' in model.named_steps:
            classifier = model.named_steps['classifier']
            if 'preprocessor' in model.named_steps:
                preprocessor = model.named_steps['preprocessor']
                try:
                    data_for_model = preprocessor.transform(X)
                except Exception as e:
                    logger.warning('Preprocessor transform failed for explainability: %s', str(e))
                    return None
                try:
                    if hasattr(preprocessor, 'get_feature_names_out'):
                        feature_names = list(preprocessor.get_feature_names_out())
                except Exception:
                    pass
        else:
            classifier = model

        if not hasattr(classifier, 'get_booster'):
            logger.warning('Classifier does not support pred_contribs.')
            return None

        try:
            dmatrix = xgb.DMatrix(data_for_model, feature_names=feature_names)
            contribs = classifier.get_booster().predict(dmatrix, pred_contribs=True)
        except Exception as e:
            logger.warning('Failed to compute pred_contribs: %s', str(e))
            return None

        if contribs is None or len(contribs) == 0:
            return None

        explanations = []
        for row_idx in range(contribs.shape[0]):
            row_contribs = contribs[row_idx][:-1]  # drop bias
            if row_contribs.size == 0:
                explanations.append([])
                continue
            top_idx = np.argsort(np.abs(row_contribs))[-top_k:][::-1]
            row_expl = []
            for idx in top_idx:
                feat_name = feature_names[idx] if idx < len(feature_names) else f'f{idx}'
                raw_name = self._clean_feature_name(str(feat_name))
                value = X.iloc[row_idx].get(raw_name, None) if hasattr(X, 'iloc') else None
                row_expl.append({
                    'feature': raw_name,
                    'contribution': float(row_contribs[idx]),
                    'value': None if value is None else (float(value) if isinstance(value, (int, float, np.floating)) else value)
                })
            explanations.append(row_expl)

        return explanations

    def predict(self, X: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Generate fraud predictions for input features.

        Args:
            X (pd.DataFrame): Feature matrix for prediction

        Returns:
            Tuple containing:
            - predictions (np.ndarray): Binary predictions (0=legitimate, 1=fraud)
            - probabilities (np.ndarray): Fraud class probabilities
            - confidence (np.ndarray): Confidence scores (max probability)
        """
        try:
            if self.model is None:
                raise RuntimeError('Model not loaded. Please train the model first by running the Airflow DAG.')
            
            # Get fraud probabilities from model
            prob_matrix = self.model.predict_proba(X)
            probabilities = prob_matrix[:, 1]

            # Apply classification threshold
            predictions = (probabilities >= self.threshold).astype(int)

            # Calculate confidence as max probability across classes
            confidence = np.max(prob_matrix, axis=1)

            logger.info('Generated predictions for %d records', len(X))
            logger.info('Fraud predictions: %d (%.2f%%)', 
                       predictions.sum(), 100 * predictions.mean())

            return predictions, probabilities, confidence

        except Exception as e:
            logger.error('Prediction failed: %s', str(e))
            raise

    def predict_from_payload(self, payload, explain: bool = False, top_k: int = 5) -> pd.DataFrame:
        """
        Run real-time predictions on provided payload records.

        Accepts:
        - list[dict]: raw transaction records
        - dict with "records": list[dict]
        - single dict: treated as one record
        """
        self.refresh_model()
        if self.model is None:
            logger.warning('Model not available for realtime prediction.')
            return {
                'status': 'model_unavailable',
                'message': 'Model not trained yet. Please run the Airflow training DAG first.',
                'data': []
            }

        if payload is None:
            raise ValueError('Payload is required')

        if isinstance(payload, dict) and 'records' in payload:
            records = payload['records']
        elif isinstance(payload, dict):
            records = [payload]
        elif isinstance(payload, list):
            records = payload
        else:
            raise ValueError('Payload must be a dict, list, or dict with "records"')

        if not records:
            raise ValueError('No records provided')

        df = pd.DataFrame(records)
        df = self.preprocess_data(df)
        df = self.engineer_features(df)

        feature_cols = self.model.feature_names_in_.tolist()
        missing_cols = [col for col in feature_cols if col not in df.columns]
        if missing_cols:
            logger.warning('Missing features: %s. Using zeros for these columns.', missing_cols)
            for col in missing_cols:
                df[col] = 0

        X = df[feature_cols]
        predictions, probabilities, confidence = self.predict(X)

        results = df.copy()
        results['fraud_prediction'] = predictions
        results['fraud_probability'] = probabilities
        results['confidence'] = confidence
        results['prediction_timestamp'] = datetime.now()
        results['threshold'] = self.threshold
        if explain:
            explanations = self._compute_explanations(X, top_k=top_k)
            if explanations is not None:
                results['top_features'] = explanations

        return results

    def run_inference(self, max_records: int = None, explain: bool = False, top_k: int = 5) -> pd.DataFrame:
        """
        Execute complete inference pipeline: ingest → preprocess → engineer → predict.

        Args:
            max_records (int): Optional limit on records to process

        Returns:
            pd.DataFrame: Results with predictions and probabilities
        """
        logger.info('Starting fraud detection inference pipeline')
        start_time = datetime.now()

        try:
            # Step 1: Refresh model (if a newer version exists)
            self.refresh_model()

            # Step 2: Ingest data from API
            df = self.ingest_data(max_records=max_records)
            logger.info('Data ingestion: %d records in %.2f seconds', 
                       len(df), (datetime.now() - start_time).total_seconds())

            # Check if model is available before proceeding
            if self.model is None:
                logger.warning('Model not available. Please train the model first by running the Airflow training DAG.')
                logger.warning('Inference service is running but model predictions are unavailable.')
                return {
                    'status': 'model_unavailable',
                    'message': 'Model not trained yet. Please run the Airflow training DAG first.',
                    'data': []
                }

            # Step 3: Preprocess data types
            df = self.preprocess_data(df)

            # Step 4: Engineer features
            df = self.engineer_features(df)

            # Step 5: Select features for model
            # Get feature names from trained model
            feature_cols = self.model.feature_names_in_.tolist()
            missing_cols = [col for col in feature_cols if col not in df.columns]
            if missing_cols:
                logger.warning('Missing features: %s. Will use zeros for these columns.', missing_cols)
                for col in missing_cols:
                    df[col] = 0

            X = df[feature_cols]

            # Step 6: Generate predictions
            predictions, probabilities, confidence = self.predict(X)

            # Step 7: Combine results
            results = df[['transaction_id', 'user_id', 'amount', 'timestamp'] 
                        if all(c in df.columns for c in ['transaction_id', 'user_id', 'amount', 'timestamp'])
                        else df.columns[:4]].copy()

            results['fraud_prediction'] = predictions
            results['fraud_probability'] = probabilities
            results['confidence'] = confidence
            results['prediction_timestamp'] = datetime.now()
            results['threshold'] = self.threshold
            if explain:
                explanations = self._compute_explanations(X, top_k=top_k)
                if explanations is not None:
                    results['top_features'] = explanations

            # Log summary statistics
            elapsed = (datetime.now() - start_time).total_seconds()
            logger.info('Inference complete in %.2f seconds', elapsed)
            logger.info('Results: %d records, %d frauds (%.2f%%), %.2f records/sec',
                       len(results), predictions.sum(), 100 * predictions.mean(),
                       len(results) / elapsed if elapsed > 0 else 0)

            return results

        except Exception as e:
            logger.error('Inference pipeline failed: %s', str(e), exc_info=True)
            raise

    def save_results(self, results: pd.DataFrame, output_path: str = None) -> str:
        """
        Save inference results to JSON file.

        Args:
            results (pd.DataFrame): Results dataframe
            output_path (str): Output file path (defaults to timestamped file)

        Returns:
            str: Path to saved file
        """
        try:
            if output_path is None:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                output_path = f'fraud_predictions_{timestamp}.json'

            # Convert datetime columns to strings for JSON serialization
            results_copy = results.copy()
            for col in results_copy.select_dtypes(include=['datetime64']).columns:
                results_copy[col] = results_copy[col].astype(str)

            with open(output_path, 'w') as f:
                json.dump(results_copy.to_dict('records'), f, indent=2)

            logger.info('Results saved to %s', output_path)
            return output_path

        except Exception as e:
            logger.error('Error saving results: %s', str(e))
            raise


def main():
    """Main entry point for inference pipeline."""
    try:
        # Initialize inference pipeline
        inference = FraudDetectionInference(config_path='/app/config.yaml')

        # Run inference pipeline
        results = inference.run_inference(max_records=int(os.getenv('FRAUD_API_INFERENCE_MAX_RECORDS', 10000)))

        # Save results
        output_file = inference.save_results(results)

        # Display summary
        fraud_count = results['fraud_prediction'].sum()
        total_count = len(results)
        fraud_rate = 100 * fraud_count / total_count if total_count > 0 else 0

        logger.info('=' * 60)
        logger.info('INFERENCE SUMMARY')
        logger.info('=' * 60)
        logger.info('Total records: %d', total_count)
        logger.info('Fraud detections: %d (%.2f%%)', fraud_count, fraud_rate)
        logger.info('Results saved to: %s', output_file)
        logger.info('=' * 60)

        return 0

    except Exception as e:
        logger.error('Fatal error in inference pipeline: %s', str(e), exc_info=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())