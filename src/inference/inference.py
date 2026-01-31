#!/usr/bin/env python3
"""
Real-Time Fraud Detection Inference Script

This script performs real-time fraud detection on incoming transactions by:
1. Loading the trained model
2. Fetching new transactions from database
3. Engineering the same 62 features used in training
4. Making fraud predictions
5. Storing predictions back to database

Usage:
    # Single transaction inference
    python3 inference.py --transaction-id TXN_ABC123

    # Batch inference on recent transactions
    python3 inference.py --batch --limit 100

    # Continuous monitoring (real-time)
    python3 inference.py --monitor --interval 5

    # API mode (Flask REST API)
    python3 inference.py --api --port 5001

Requirements:
    pip install joblib psycopg2-binary pandas numpy scikit-learn flask
"""

import os
import sys
import json
import time
import logging
import argparse
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional, Tuple

import joblib
import numpy as np
import pandas as pd
from dotenv import load_dotenv

# Load environment
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('fraud_detection_inference')


class FraudDetectionInference:
    """
    Real-time fraud detection inference system.
    
    Loads trained model and performs predictions on new transactions
    by engineering the same 62 features used during training.
    """
    
    def __init__(self, model_path: str = None):
        """
        Initialize inference system.
        
        Args:
            model_path: Path to trained model pickle file
        """
        self.model_path = model_path or os.getenv(
            'MODEL_PATH', 
            '/app/models/fraud_detection_model.pkl'
        )
        
        # Try alternative path if primary doesn't exist
        if not os.path.exists(self.model_path):
            self.model_path = './models/fraud_detection_model.pkl'
        
        # Load model
        self.model = self._load_model()
        
        # Database connection
        self.db_conn = self._connect_db()
        
        logger.info("Fraud detection inference system initialized")
    
    def _load_model(self):
        """Load trained model from disk."""
        try:
            if not os.path.exists(self.model_path):
                raise FileNotFoundError(f"Model not found at {self.model_path}")
            
            model = joblib.load(self.model_path)
            logger.info(f"Model loaded successfully from {self.model_path}")
            return model
            
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            raise
    
    def _connect_db(self):
        """Establish database connection."""
        try:
            import psycopg2
            
            conn = psycopg2.connect(
                host=os.getenv('DB_HOST', 'localhost'),
                port=int(os.getenv('DB_PORT', 5432)),
                dbname=os.getenv('DB_NAME', 'postgres'),
                user=os.getenv('DB_USER', 'postgres'),
                password=os.getenv('DB_PASSWORD', '')
            )
            logger.info("Database connection established")
            return conn
            
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            return None
    
    def fetch_transaction(self, transaction_id: str) -> Optional[pd.DataFrame]:
        """
        Fetch a single transaction from database.
        
        Args:
            transaction_id: Transaction ID to fetch
            
        Returns:
            DataFrame with transaction data or None
        """
        if not self.db_conn:
            logger.error("No database connection")
            return None
        
        try:
            query = """
                SELECT 
                    transaction_id, order_id, user_id, full_name, email, phone_number,
                    gender, age, registration_date, account_status, session_id, timestamp,
                    action, device_id, ip_address, location, country, device_type, browser,
                    geo_location, session_duration, product_id, product_name, category,
                    price, discount, vendor_id, quantity, payment_method, payment_status,
                    amount, currency, delivery_address, return_request, refund_status,
                    rating, is_fraud, fraud_type
                FROM transactions
                WHERE transaction_id = %s
            """
            
            df = pd.read_sql_query(query, self.db_conn, params=(transaction_id,))
            
            if len(df) == 0:
                logger.warning(f"Transaction {transaction_id} not found")
                return None
            
            return df
            
        except Exception as e:
            logger.error(f"Failed to fetch transaction: {e}")
            return None
    
    def fetch_recent_transactions(self, limit: int = 100) -> Optional[pd.DataFrame]:
        """
        Fetch recent transactions for batch prediction.
        
        Args:
            limit: Maximum number of transactions to fetch
            
        Returns:
            DataFrame with transactions
        """
        if not self.db_conn:
            logger.error("No database connection")
            return None
        
        try:
            query = f"""
                SELECT 
                    transaction_id, order_id, user_id, full_name, email, phone_number,
                    gender, age, registration_date, account_status, session_id, timestamp,
                    action, device_id, ip_address, location, country, device_type, browser,
                    geo_location, session_duration, product_id, product_name, category,
                    price, discount, vendor_id, quantity, payment_method, payment_status,
                    amount, currency, delivery_address, return_request, refund_status,
                    rating, is_fraud, fraud_type
                FROM transactions
                ORDER BY timestamp DESC
                LIMIT {limit}
            """
            
            df = pd.read_sql_query(query, self.db_conn)
            logger.info(f"Fetched {len(df)} recent transactions")
            return df
            
        except Exception as e:
            logger.error(f"Failed to fetch transactions: {e}")
            return None
    
    def engineer_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Engineer the same 62 features used during training.
        
        This MUST match the feature engineering in fraud_detection_training.py
        
        Args:
            df: Raw transaction DataFrame
            
        Returns:
            DataFrame with engineered features
        """
        logger.info("Engineering features for inference...")
        
        df = df.copy()
        
        # Convert timestamps
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df['registration_date'] = pd.to_datetime(df['registration_date'])
        df = df.sort_values('timestamp').reset_index(drop=True)
        
        # ========== TEMPORAL FEATURES ==========
        df['account_age_days'] = (df['timestamp'] - df['registration_date']).dt.total_seconds() / 86400
        df['account_age_days'] = df['account_age_days'].clip(lower=0)
        
        df['transaction_velocity_1h'] = df.groupby('user_id')['timestamp'].transform(
            lambda x: x.rolling('1H').count()
        )
        df['transaction_velocity_24h'] = df.groupby('user_id')['timestamp'].transform(
            lambda x: x.rolling('24H').count()
        )
        
        df['payment_velocity_1h'] = df.groupby('user_id')['amount'].transform(
            lambda x: x.rolling(window=10, min_periods=1).sum()
        )
        df['payment_velocity_24h'] = df.groupby('user_id')['amount'].transform(
            lambda x: x.rolling(window=50, min_periods=1).sum()
        )
        
        df['has_discount'] = (df['discount'] > 0).astype(int)
        df['discount_velocity_24h'] = df.groupby('user_id')['has_discount'].transform(
            lambda x: x.rolling(window=20, min_periods=1).sum()
        )
        
        login_counts = df[df['action'] == 'login'].groupby('user_id').size()
        df['login_frequency'] = df['user_id'].map(login_counts).fillna(0)
        
        df['hour_of_day'] = df['timestamp'].dt.hour
        df['is_night_transaction'] = ((df['hour_of_day'] >= 22) | (df['hour_of_day'] <= 5)).astype(int)
        
        # ========== IDENTITY FEATURES ==========
        df['identity_mismatch_score'] = np.random.uniform(0, 0.3, len(df))
        df.loc[df['account_age_days'] < 7, 'identity_mismatch_score'] += 0.3
        df.loc[df['account_status'] == 'new', 'identity_mismatch_score'] += 0.2
        df['identity_mismatch_score'] = df['identity_mismatch_score'].clip(0, 1)
        
        df['identity_verification_score'] = 0.7
        df.loc[df['account_status'] == 'verified', 'identity_verification_score'] = 0.95
        df.loc[df['account_status'] == 'new', 'identity_verification_score'] = 0.3
        df.loc[df['account_status'] == 'suspended', 'identity_verification_score'] = 0.1
        
        df['sim_swap_probability'] = np.random.uniform(0, 0.1, len(df))
        df.loc[df['account_age_days'] < 3, 'sim_swap_probability'] += 0.4
        df['sim_swap_probability'] = df['sim_swap_probability'].clip(0, 1)
        
        df['phone_verified'] = (np.random.random(len(df)) > 0.3).astype(int)
        df.loc[df['account_status'] == 'verified', 'phone_verified'] = 1
        
        disposable_domains = ['tempmail', 'guerrillamail', '10minutemail', 'throwaway']
        df['email_disposable_flag'] = df['email'].str.contains('|'.join(disposable_domains), 
                                                               case=False, na=False).astype(int)
        
        df['identity_confidence_score'] = (
            df['identity_verification_score'] * 0.6 + 
            (1 - df['identity_mismatch_score']) * 0.4
        )
        
        # ========== DEVICE FEATURES ==========
        device_counts = df.groupby('device_id')['user_id'].nunique()
        df['device_user_count'] = df['device_id'].map(device_counts)
        df['device_fingerprint_score'] = 1 - (df['device_user_count'] - 1).clip(0, 10) / 10
        
        df['android_emulator_detection'] = (
            (df['device_type'] == 'Mobile') & 
            (np.random.random(len(df)) < 0.05)
        ).astype(int)
        
        trusted_browsers = ['Chrome', 'Firefox', 'Safari', 'Edge']
        df['browser_integrity_score'] = df['browser'].isin(trusted_browsers).astype(float)
        df['browser_integrity_score'] += np.random.uniform(-0.1, 0.1, len(df))
        df['browser_integrity_score'] = df['browser_integrity_score'].clip(0, 1)
        
        df['device_trust_score'] = (
            df['device_fingerprint_score'] * 0.5 +
            (1 - df['android_emulator_detection']) * 0.3 +
            df['browser_integrity_score'] * 0.2
        )
        
        df['device_change_rate'] = df.groupby('user_id')['device_id'].transform(
            lambda x: x.nunique() / len(x) if len(x) > 0 else 0
        )
        
        # ========== LOCATION FEATURES ==========
        df['ip_risk_score'] = np.random.uniform(0, 0.2, len(df))
        df.loc[df['ip_address'].str.startswith('100.'), 'ip_risk_score'] += 0.5
        df.loc[df['ip_address'].str.startswith('200.'), 'ip_risk_score'] += 0.5
        df['ip_risk_score'] = df['ip_risk_score'].clip(0, 1)
        
        df['ip_location_mismatch_flag'] = (np.random.random(len(df)) < 0.1).astype(int)
        df['location_distance_score'] = np.random.uniform(0, 0.3, len(df))
        df['proxy_detection_flag'] = (df['ip_risk_score'] > 0.6).astype(int)
        df['vpn_usage_flag'] = (np.random.random(len(df)) < 0.15).astype(int)
        
        # ========== PAYMENT FEATURES ==========
        user_payment_stats = df.groupby('user_id').agg({
            'payment_status': lambda x: (x == 'failed').sum() / len(x) if len(x) > 0 else 0
        }).rename(columns={'payment_status': 'failed_payment_ratio'})
        df = df.merge(user_payment_stats, left_on='user_id', right_index=True, how='left')
        df['failed_payment_ratio'] = df['failed_payment_ratio'].fillna(0)
        
        user_avg_amount = df.groupby('user_id')['amount'].transform('mean')
        df['current_order_value_ratio'] = df['amount'] / (user_avg_amount + 1)
        
        user_payment_methods = df.groupby('user_id')['payment_method'].transform('nunique')
        df['payment_method_anomaly'] = (user_payment_methods > 3).astype(int)
        
        df['is_linked_card'] = df['payment_method'].str.contains('Card', case=False).astype(int)
        
        df['bank_transfer_verification'] = (
            df['payment_method'].str.contains('Transfer', case=False) & 
            (df['payment_status'] == 'success')
        ).astype(int)
        
        df['partial_payment_requirement'] = (df['payment_status'] == 'pending').astype(int)
        
        df['payment_anomaly_score'] = (
            df['failed_payment_ratio'] * 0.4 +
            (df['current_order_value_ratio'] > 3).astype(float) * 0.3 +
            df['payment_method_anomaly'] * 0.3
        )
        
        # ========== NETWORK FEATURES ==========
        ip_user_count = df.groupby('ip_address')['user_id'].transform('nunique')
        device_user_count = df.groupby('device_id')['user_id'].transform('nunique')
        df['fraud_ring_score'] = ((ip_user_count > 5) | (device_user_count > 3)).astype(float) * 0.7
        
        vendor_fraud_rate = df.groupby('vendor_id')['is_fraud'].transform('mean')
        df['vendor_risk_score'] = vendor_fraud_rate.fillna(0.5)
        
        df['user_reputation_score'] = 0.7
        df.loc[df['account_status'] == 'verified', 'user_reputation_score'] = 0.9
        df.loc[df['account_status'] == 'new', 'user_reputation_score'] = 0.4
        df.loc[df['account_status'] == 'suspended', 'user_reputation_score'] = 0.1
        df['user_reputation_score'] -= df['failed_payment_ratio'] * 0.3
        df['user_reputation_score'] = df['user_reputation_score'].clip(0, 1)
        
        df['shared_ip_count'] = df.groupby('ip_address')['user_id'].transform('nunique')
        df['shared_phone_number_count'] = df.groupby('phone_number')['user_id'].transform('nunique')
        
        df['account_link_density'] = (
            (df['shared_ip_count'] - 1) + 
            (df['shared_phone_number_count'] - 1)
        ).clip(0, 20) / 20
        
        df['linked_accounts'] = (
            (df['shared_ip_count'] > 2) | 
            (df['shared_phone_number_count'] > 1)
        ).astype(int)
        
        # ========== BEHAVIORAL FEATURES ==========
        df['activity_timing_score'] = df['is_night_transaction'] * 0.6 + np.random.uniform(0, 0.4, len(df))
        df['activity_timing_score'] = df['activity_timing_score'].clip(0, 1)
        
        df['anomaly_frequency_score'] = (
            (df['transaction_velocity_1h'] > 5).astype(float) * 0.4 +
            (df['payment_velocity_1h'] > 100000).astype(float) * 0.3 +
            (df['session_duration'] < 60).astype(float) * 0.3
        )
        
        df['behavioral_consistency_score'] = 1 - df['anomaly_frequency_score']
        
        review_pattern = (
            (df['rating'].notna()) & 
            ((df['rating'] == 5) | (df['rating'] == 1)) &
            (df['account_age_days'] < 30)
        )
        df['fake_review_score'] = review_pattern.astype(float) * 0.6
        
        df['session_behavior_score'] = 1 - (
            (df['session_duration'] < 120).astype(float) * 0.5 +
            (df['action'] == 'purchase').astype(float) * 0.3
        )
        
        df['multi_device_login_flag'] = (df['device_change_rate'] > 0.5).astype(int)
        
        # ========== PRODUCT FEATURES ==========
        category_avg_price = df.groupby('category')['price'].transform('mean')
        df['product_price_anomaly_score'] = (
            (df['price'] / (category_avg_price + 1)) - 1
        ).abs().clip(0, 2) / 2
        
        df['high_value_product'] = (df['amount'] > df['amount'].quantile(0.9)).astype(int)
        df['bulk_purchase'] = (df['quantity'] > 3).astype(int)
        
        # ========== ADDRESS FEATURES ==========
        address_user_count = df.groupby('delivery_address')['user_id'].transform('nunique')
        df['address_risk_score'] = ((address_user_count > 3).astype(float) * 0.7).clip(0, 1)
        
        df['address_reuse_rate'] = df.groupby('user_id')['delivery_address'].transform(
            lambda x: 1 - (x.nunique() / len(x)) if len(x) > 0 else 0
        )
        
        df['shared_address_count'] = address_user_count
        
        df['rider_collusion_risk'] = (
            (df['shared_address_count'] > 5) & 
            (df['transaction_velocity_24h'] > 10)
        ).astype(float) * 0.8
        
        df['location_hopping_flag'] = (
            df.groupby('user_id')['location'].transform('nunique') > 3
        ).astype(int)
        
        # ========== DELIVERY/REFUND FEATURES ==========
        user_refund_rate = df.groupby('user_id')['return_request'].transform('mean')
        df['refund_abuse_score'] = user_refund_rate.fillna(0)
        
        df['delivery_delay_ratio'] = np.random.uniform(0, 0.3, len(df))
        
        df['failed_delivery_pattern'] = (
            (df['payment_status'] == 'failed') & 
            (df['action'] == 'purchase')
        ).astype(int)
        
        user_purchase_count = df[df['action'] == 'purchase'].groupby('user_id').size()
        user_refund_count = df[df['return_request']].groupby('user_id').size()
        refund_ratio = (user_refund_count / user_purchase_count).fillna(0)
        df['refund_to_purchase_ratio'] = df['user_id'].map(refund_ratio).fillna(0)
        
        df['return_inspection_score'] = np.where(
            df['return_request'],
            np.random.uniform(0.3, 0.9, len(df)),
            0
        )
        
        df['product_swap_probability'] = (
            df['return_request'].astype(float) * 
            np.random.uniform(0, 0.5, len(df))
        )
        
        df['delivery_dispute_rate'] = (
            (df['return_request']) & 
            (df['refund_status'].isin(['requested', 'approved']))
        ).astype(float)
        df['delivery_dispute_rate'] = df.groupby('user_id')['delivery_dispute_rate'].transform('mean').fillna(0)
        
        refund_severity_map = {
            'none': 0,
            'requested': 0.3,
            'approved': 0.6,
            'completed': 0.8,
            'denied': 0.2
        }
        df['refund_severity_score'] = df['refund_status'].map(refund_severity_map).fillna(0)
        
        df['serial_returner_flag'] = (df['refund_to_purchase_ratio'] > 0.3).astype(int)
        
        logger.info(f"Feature engineering complete: {len(df.columns)} columns")
        
        return df
    
    def predict(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """
        Make fraud predictions on transactions.
        
        Args:
            df: DataFrame with raw transactions
            
        Returns:
            List of prediction dictionaries
        """
        # Engineer features
        df_features = self.engineer_features(df)
        
        # Get feature columns (exclude metadata)
        feature_cols = [col for col in df_features.columns if col not in [
            'transaction_id', 'order_id', 'user_id', 'full_name', 'email',
            'phone_number', 'session_id', 'device_id', 'ip_address', 'product_id',
            'product_name', 'delivery_address', 'geo_location', 'vendor_id',
            'is_fraud', 'fraud_type', 'timestamp', 'registration_date'
        ]]
        
        X = df_features[feature_cols].fillna(0)
        
        # Make predictions
        try:
            fraud_proba = self.model.predict_proba(X)[:, 1]
            fraud_pred = self.model.predict(X)
            
            # Build results
            results = []
            for i, row in df_features.iterrows():
                result = {
                    'transaction_id': row['transaction_id'],
                    'user_id': row['user_id'],
                    'amount': float(row['amount']),
                    'currency': str(row.get('currency', 'NGN')),  # Default to NGN
                    'fraud_probability': float(fraud_proba[i]),
                    'fraud_prediction': int(fraud_pred[i]),
                    'fraud_label': 'FRAUD' if fraud_pred[i] == 1 else 'LEGITIMATE',
                    'risk_level': self._get_risk_level(fraud_proba[i]),
                    'timestamp': row['timestamp'].isoformat(),
                    'prediction_timestamp': datetime.now(timezone.utc).isoformat(),
                    'actual_fraud': int(row.get('is_fraud', -1))  # -1 if unknown
                }
                results.append(result)
            
            return results
            
        except Exception as e:
            logger.error(f"Prediction failed: {e}", exc_info=True)
            return []
    
    def run_inference(self, max_records: int = 10000, explain: bool = False, top_k: int = 5) -> pd.DataFrame:
        """
        Run inference on recent unscored transactions.
        
        Args:
            max_records: Maximum number of transactions to process
            explain: Whether to include feature importance explanations
            top_k: Number of top features to explain
            
        Returns:
            DataFrame with fraud predictions
        """
        if not self.db_conn:
            logger.error("No database connection")
            return pd.DataFrame()
        
        try:
            # Fetch recent transactions that haven't been scored yet
            query = f"""
                SELECT 
                    transaction_id, order_id, user_id, full_name, email, phone_number,
                    gender, age, registration_date, account_status, session_id, timestamp,
                    action, device_id, ip_address, location, country, device_type, browser,
                    geo_location, session_duration, product_id, product_name, category,
                    price, discount, vendor_id, quantity, payment_method, payment_status,
                    amount, currency, delivery_address, return_request, refund_status,
                    rating, is_fraud, fraud_type
                FROM transactions
                WHERE transaction_id NOT IN (SELECT transaction_id FROM fraud_predictions)
                ORDER BY timestamp DESC
                LIMIT {max_records}
            """
            
            df = pd.read_sql_query(query, self.db_conn)
            logger.info(f"Fetched {len(df)} new transactions for inference")
            
            if len(df) == 0:
                return pd.DataFrame()
            
            # Make predictions
            predictions = self.predict(df)
            
            # Save predictions to database
            if predictions:
                self.save_predictions(predictions)
                logger.info(f"Saved {len(predictions)} predictions")
            
            # Convert to DataFrame for API response
            if predictions:
                results_df = pd.DataFrame(predictions)
                return results_df
            else:
                return pd.DataFrame()
            
        except Exception as e:
            logger.error(f"Inference failed: {e}", exc_info=True)
            return pd.DataFrame()
    
    def _get_risk_level(self, probability: float) -> str:
        """Categorize risk level based on fraud probability."""
        if probability >= 0.8:
            return 'CRITICAL'
        elif probability >= 0.6:
            return 'HIGH'
        elif probability >= 0.4:
            return 'MEDIUM'
        elif probability >= 0.2:
            return 'LOW'
        else:
            return 'MINIMAL'
    
    def save_predictions(self, predictions: List[Dict]) -> bool:
        """
        Save predictions to database.
        
        Args:
            predictions: List of prediction dictionaries
            
        Returns:
            True if successful
        """
        if not self.db_conn or not predictions:
            return False
        
        try:
            # Create predictions table if not exists
            create_table_sql = """
            CREATE TABLE IF NOT EXISTS fraud_predictions (
                id SERIAL PRIMARY KEY,
                transaction_id VARCHAR(50) UNIQUE NOT NULL,
                user_id VARCHAR(50),
                amount DECIMAL(15, 2),
                fraud_probability FLOAT,
                fraud_prediction INTEGER,
                fraud_label VARCHAR(20),
                risk_level VARCHAR(20),
                prediction_timestamp TIMESTAMP DEFAULT NOW(),
                actual_fraud INTEGER
            );
            CREATE INDEX IF NOT EXISTS idx_pred_txn ON fraud_predictions(transaction_id);
            CREATE INDEX IF NOT EXISTS idx_pred_timestamp ON fraud_predictions(prediction_timestamp);
            """
            
            cur = self.db_conn.cursor()
            cur.execute(create_table_sql)
            self.db_conn.commit()
            
            # Insert predictions
            insert_sql = """
            INSERT INTO fraud_predictions 
            (transaction_id, user_id, amount, fraud_probability, fraud_prediction,
             fraud_label, risk_level, actual_fraud)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (transaction_id) DO UPDATE SET
                fraud_probability = EXCLUDED.fraud_probability,
                fraud_prediction = EXCLUDED.fraud_prediction,
                fraud_label = EXCLUDED.fraud_label,
                risk_level = EXCLUDED.risk_level,
                prediction_timestamp = NOW()
            """
            
            for pred in predictions:
                cur.execute(insert_sql, (
                    pred['transaction_id'],
                    pred['user_id'],
                    pred['amount'],
                    pred['fraud_probability'],
                    pred['fraud_prediction'],
                    pred['fraud_label'],
                    pred['risk_level'],
                    pred.get('actual_fraud', -1)
                ))
            
            self.db_conn.commit()
            cur.close()
            
            logger.info(f"Saved {len(predictions)} predictions to database")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save predictions: {e}")
            return False
    
    def monitor_continuous(self, interval: int = 5):
        """
        Continuously monitor for new transactions and predict.
        
        Args:
            interval: Check interval in seconds
        """
        logger.info(f"Starting continuous monitoring (interval: {interval}s)")
        logger.info("Press Ctrl+C to stop")
        
        last_checked = datetime.now(timezone.utc)
        
        try:
            while True:
                # Fetch new transactions since last check
                if self.db_conn:
                    query = """
                        SELECT * FROM transactions
                        WHERE timestamp > %s
                        ORDER BY timestamp ASC
                    """
                    
                    df = pd.read_sql_query(query, self.db_conn, params=(last_checked,))
                    
                    if len(df) > 0:
                        logger.info(f"Found {len(df)} new transactions")
                        
                        # Make predictions
                        predictions = self.predict(df)
                        
                        # Display results
                        for pred in predictions:
                            logger.info(
                                f"🔍 {pred['transaction_id']} | "
                                f"User: {pred['user_id']} | "
                                f"Amount: NGN {pred['amount']:,.2f} | "
                                f"Fraud Prob: {pred['fraud_probability']:.2%} | "
                                f"Prediction: {pred['fraud_label']} | "
                                f"Risk: {pred['risk_level']}"
                            )
                        
                        # Save to database
                        self.save_predictions(predictions)
                        
                        last_checked = df['timestamp'].max()
                
                time.sleep(interval)
                
        except KeyboardInterrupt:
            logger.info("Monitoring stopped by user")


def main():
    """Main entry point with CLI support."""
    parser = argparse.ArgumentParser(
        description='Nigerian E-commerce Fraud Detection - Inference'
    )
    
    parser.add_argument(
        '--transaction-id',
        type=str,
        help='Predict on single transaction ID'
    )
    
    parser.add_argument(
        '--batch',
        action='store_true',
        help='Batch prediction on recent transactions'
    )
    
    parser.add_argument(
        '--limit',
        type=int,
        default=100,
        help='Number of transactions for batch prediction (default: 100)'
    )
    
    parser.add_argument(
        '--monitor',
        action='store_true',
        help='Continuous monitoring mode'
    )
    
    parser.add_argument(
        '--interval',
        type=int,
        default=5,
        help='Monitoring interval in seconds (default: 5)'
    )
    
    parser.add_argument(
        '--model-path',
        type=str,
        help='Path to trained model file'
    )
    
    parser.add_argument(
        '--api',
        action='store_true',
        help='Start REST API server'
    )
    
    parser.add_argument(
        '--port',
        type=int,
        default=5001,
        help='API server port (default: 5001)'
    )
    
    args = parser.parse_args()
    
    # Initialize inference system
    try:
        inference = FraudDetectionInference(model_path=args.model_path)
    except Exception as e:
        logger.error(f"Failed to initialize inference system: {e}")
        sys.exit(1)
    
    # Single transaction prediction
    if args.transaction_id:
        logger.info(f"Predicting transaction: {args.transaction_id}")
        df = inference.fetch_transaction(args.transaction_id)
        
        if df is not None:
            predictions = inference.predict(df)
            
            if predictions:
                pred = predictions[0]
                print("\n" + "="*70)
                print("FRAUD DETECTION RESULT")
                print("="*70)
                print(f"Transaction ID:    {pred['transaction_id']}")
                print(f"User ID:           {pred['user_id']}")
                print(f"Amount:            NGN {pred['amount']:,.2f}")
                print(f"Fraud Probability: {pred['fraud_probability']:.2%}")
                print(f"Prediction:        {pred['fraud_label']}")
                print(f"Risk Level:        {pred['risk_level']}")
                print(f"Timestamp:         {pred['timestamp']}")
                if pred['actual_fraud'] != -1:
                    print(f"Actual Label:      {'FRAUD' if pred['actual_fraud'] == 1 else 'LEGITIMATE'}")
                print("="*70 + "\n")
                
                inference.save_predictions(predictions)
    
    # Batch prediction
    elif args.batch:
        logger.info(f"Batch prediction on {args.limit} recent transactions")
        df = inference.fetch_recent_transactions(limit=args.limit)
        
        if df is not None:
            predictions = inference.predict(df)
            
            if predictions:
                # Summary statistics
                fraud_count = sum(1 for p in predictions if p['fraud_prediction'] == 1)
                avg_prob = sum(p['fraud_probability'] for p in predictions) / len(predictions)
                
                print("\n" + "="*70)
                print("BATCH PREDICTION SUMMARY")
                print("="*70)
                print(f"Total Transactions:  {len(predictions):,}")
                print(f"Predicted Fraud:     {fraud_count} ({fraud_count/len(predictions)*100:.1f}%)")
                print(f"Avg Fraud Prob:      {avg_prob:.2%}")
                print("="*70)
                
                # Risk distribution
                risk_dist = {}
                for p in predictions:
                    risk_dist[p['risk_level']] = risk_dist.get(p['risk_level'], 0) + 1
                
                print("\nRisk Distribution:")
                for risk, count in sorted(risk_dist.items()):
                    print(f"  {risk:.<20} {count:>5} ({count/len(predictions)*100:.1f}%)")
                print("="*70 + "\n")
                
                inference.save_predictions(predictions)
    
    # Continuous monitoring
    elif args.monitor:
        inference.monitor_continuous(interval=args.interval)
    
    # API mode
    elif args.api:
        try:
            from flask import Flask, request, jsonify
            
            app = Flask(__name__)
            
            @app.route('/predict', methods=['POST'])
            def predict_api():
                """API endpoint for fraud prediction."""
                try:
                    data = request.json
                    transaction_id = data.get('transaction_id')
                    
                    if not transaction_id:
                        return jsonify({'error': 'transaction_id required'}), 400
                    
                    df = inference.fetch_transaction(transaction_id)
                    if df is None:
                        return jsonify({'error': 'Transaction not found'}), 404
                    
                    predictions = inference.predict(df)
                    if not predictions:
                        return jsonify({'error': 'Prediction failed'}), 500
                    
                    return jsonify(predictions[0])
                    
                except Exception as e:
                    return jsonify({'error': str(e)}), 500
            
            @app.route('/health', methods=['GET'])
            def health():
                """Health check endpoint."""
                return jsonify({'status': 'healthy', 'model_loaded': inference.model is not None})
            
            logger.info(f"Starting API server on port {args.port}")
            app.run(host='0.0.0.0', port=args.port)
            
        except ImportError:
            logger.error("Flask not installed. Install with: pip install flask")
            sys.exit(1)
    
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
