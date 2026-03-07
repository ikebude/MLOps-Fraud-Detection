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

# Structured logging
try:
    from utils.logging_config import setup_structured_logging
    logger = setup_structured_logging('fraud-detection-inference', logging.INFO)
except Exception:
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
        self._ensure_schema()
        
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

    def _ensure_schema(self):
        """Ensure database schema is correct, adding missing columns if needed."""
        if not self.db_conn:
            return

        try:
            cur = self.db_conn.cursor()
            
            # Create table if not exists (base schema)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS fraud_predictions (
                    id SERIAL PRIMARY KEY,
                    transaction_id VARCHAR(50) UNIQUE NOT NULL,
                    user_id VARCHAR(50),
                    amount DECIMAL(15, 2),
                    fraud_probability FLOAT,
                    fraud_prediction INTEGER,
                    fraud_label VARCHAR(20),
                    risk_level VARCHAR(20),
                    actual_fraud INTEGER DEFAULT 0,
                    prediction_timestamp TIMESTAMP DEFAULT NOW()
                );
            """)
            
            # Add indices if not exist
            cur.execute("CREATE INDEX IF NOT EXISTS idx_pred_txn ON fraud_predictions(transaction_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_pred_timestamp ON fraud_predictions(prediction_timestamp);")
            
            # Determine existing columns to add missing ones (migration logic)
            cur.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'fraud_predictions';
            """)
            existing_columns = {row[0] for row in cur.fetchall()}
            
            # Add missing columns safely
            alter_statements = []
            if 'fraud_label' not in existing_columns:
                alter_statements.append("ALTER TABLE fraud_predictions ADD COLUMN IF NOT EXISTS fraud_label VARCHAR(20);")
            if 'risk_level' not in existing_columns:
                alter_statements.append("ALTER TABLE fraud_predictions ADD COLUMN IF NOT EXISTS risk_level VARCHAR(20);")
            if 'actual_fraud' not in existing_columns:
                alter_statements.append("ALTER TABLE fraud_predictions ADD COLUMN IF NOT EXISTS actual_fraud INTEGER DEFAULT 0;")
            
            for stmt in alter_statements:
                try:
                    cur.execute(stmt)
                    logger.info(f"Executed schema migration: {stmt}")
                except Exception as e:
                    logger.warning(f"Schema migration failed (might already exist): {e}")
            
            self.db_conn.commit()
            cur.close()
            logger.info("Database schema verified")
            
        except Exception as e:
            logger.error(f"Schema verification failed: {e}")
            if self.db_conn:
                self.db_conn.rollback()
    
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
        Perform complete feature engineering to create 74 fraud detection features.
        (54 engineered + 20 raw producers = 74 total)
        Matches fraud_detection_training.py logic exactly.
        
        Args:
            df: Raw transaction DataFrame
            
        Returns:
            DataFrame with engineered features
        """
        logger.info("Starting feature engineering for features...")
        
        df = df.copy()
        
        # Convert timestamp to datetime
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df['registration_date'] = pd.to_datetime(df['registration_date'])
        
        # Sort by timestamp for velocity calculations
        df = df.sort_values('timestamp').reset_index(drop=True)
        
        # ========== AMOUNT-BASED FEATURES (STRONGEST SIGNAL) ==========
        # Data analysis shows fraud amount avg=113,805 vs legitimate avg=42,506 (2.7x)
        
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
        
        # 35. Product price anomaly score
        category_avg_price = df.groupby('category')['price'].transform('mean')
        df['product_price_anomaly_score'] = (
            (df['price'] / (category_avg_price + 1)) - 1
        ).abs().clip(0, 2) / 2
        
        # ========== ADDRESS FEATURES (2) ==========
        
        # 36. Address reuse rate
        df['address_reuse_rate'] = df.groupby('user_id')['delivery_address'].transform(
            lambda x: 1 - (x.nunique() / len(x)) if len(x) > 0 else 0
        )
        
        # 37. Shared address count
        df['shared_address_count'] = df.groupby('delivery_address')['user_id'].transform('nunique')
        
        # ========== DELIVERY/REFUND FEATURES (5) ==========
        
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
                AND timestamp > NOW() - INTERVAL '1 hour'
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
            cur = self.db_conn.cursor()
            
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
            if self.db_conn:
                self.db_conn.rollback()
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





