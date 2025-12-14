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

        # Load pre-trained fraud detection model
        self.model = self._load_model(self.config['model']['path'])

        # Classification threshold (tuned during training)
        self.threshold = float(self.config['model'].get('threshold', 0.5))

        logger.info('Inference pipeline initialized with config: %s', config_path)
        logger.info('Using API: %s', self.api_url[:60] + '...')
        logger.info('Classification threshold: %.4f', self.threshold)

    def _load_model(self, model_path: str):
        """
        Load pre-trained fraud detection model from disk.

        Args:
            model_path (str): Path to serialized model file (joblib format)

        Returns:
            model: Loaded scikit-learn/XGBoost pipeline

        Raises:
            Exception: If model loading fails
        """
        try:
            model = joblib.load(model_path)
            logger.info('Model loaded successfully from %s', model_path)
            return model
        except FileNotFoundError:
            logger.error('Model file not found at %s. Have you trained the model yet?', model_path)
            raise FileNotFoundError(f'Model file not found: {model_path}')
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
            # Get fraud probabilities from model
            probabilities = self.model.predict_proba(X)[:, 1]

            # Apply classification threshold
            predictions = (probabilities >= self.threshold).astype(int)

            # Calculate confidence as max probability across classes
            confidence = np.max(self.model.predict_proba(X), axis=1)

            logger.info('Generated predictions for %d records', len(X))
            logger.info('Fraud predictions: %d (%.2f%%)', 
                       predictions.sum(), 100 * predictions.mean())

            return predictions, probabilities, confidence

        except Exception as e:
            logger.error('Prediction failed: %s', str(e))
            raise

    def run_inference(self, max_records: int = None) -> pd.DataFrame:
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
            # Step 1: Ingest data from API
            df = self.ingest_data(max_records=max_records)
            logger.info('Data ingestion: %d records in %.2f seconds', 
                       len(df), (datetime.now() - start_time).total_seconds())

            # Step 2: Preprocess data types
            df = self.preprocess_data(df)

            # Step 3: Engineer features
            df = self.engineer_features(df)

            # Step 4: Select features for model
            # Get feature names from trained model
            feature_cols = self.model.feature_names_in_.tolist()
            missing_cols = [col for col in feature_cols if col not in df.columns]
            if missing_cols:
                logger.warning('Missing features: %s. Will use zeros for these columns.', missing_cols)
                for col in missing_cols:
                    df[col] = 0

            X = df[feature_cols]

            # Step 5: Generate predictions
            predictions, probabilities, confidence = self.predict(X)

            # Step 6: Combine results
            results = df[['transaction_id', 'user_id', 'amount', 'timestamp'] 
                        if all(c in df.columns for c in ['transaction_id', 'user_id', 'amount', 'timestamp'])
                        else df.columns[:4]].copy()

            results['fraud_prediction'] = predictions
            results['fraud_probability'] = probabilities
            results['confidence'] = confidence
            results['prediction_timestamp'] = datetime.now()
            results['threshold'] = self.threshold

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