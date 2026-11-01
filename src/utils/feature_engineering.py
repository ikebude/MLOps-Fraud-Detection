import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)

class FeatureEngineer:
    """
    Unified feature engineering for both training and inference.
    Never reads the label (`is_fraud`), so training and serving compute the same thing.
    """

    def engineer_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Input: Raw DataFrame from Postgres or API payload.
        Output: DataFrame with the engineered columns added (the training script decides which are model inputs).
        """
        df = df.copy()
        
        # Convert timestamp to datetime
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df['registration_date'] = pd.to_datetime(df['registration_date'])
        
        # Sort by timestamp for velocity calculations (essential for batch/training)
        df = df.sort_values('timestamp').reset_index(drop=True)
        
        # ========== AMOUNT-BASED FEATURES ==========
        # 1. Account age in days
        df['account_age_days'] = (df['timestamp'] - df['registration_date']).dt.total_seconds() / 86400
        df['account_age_days'] = df['account_age_days'].clip(lower=0)
        
        # 2. Amount z-score
        amount_mean = df['amount'].mean()
        amount_std = df['amount'].std()
        df['amount_zscore'] = (df['amount'] - amount_mean) / (amount_std + 1e-6)
        
        # 3. Amount percentile rank
        df['amount_percentile'] = df['amount'].rank(pct=True)
        
        # 4. High value transaction flag (top 10%)
        amount_90th = df['amount'].quantile(0.90)
        df['is_high_value'] = (df['amount'] > amount_90th).astype(int)
        
        # 5. Amount to user's average ratio
        user_avg_amount = df.groupby('user_id')['amount'].transform('mean')
        df['amount_to_user_avg_ratio'] = df['amount'] / (user_avg_amount + 1)
        
        # 6. Amount to category average ratio
        category_avg_amount = df.groupby('category')['amount'].transform('mean')
        df['amount_to_category_avg_ratio'] = df['amount'] / (category_avg_amount + 1)
        
        # 7. Session-to-amount ratio
        df['session_amount_ratio'] = df['session_duration'] / (df['amount'] / 1000 + 1)
        
        # 8. Short session flag
        session_25th = df['session_duration'].quantile(0.25)
        df['is_short_session'] = (df['session_duration'] < (session_25th if pd.notnull(session_25th) else 30)).astype(int)
        
        # 9-10. Combined fraud risk indicators
        df['high_value_short_session'] = (df['is_high_value'] & df['is_short_session']).astype(int)
        df['fraud_risk_composite'] = (
            df['amount_zscore'].clip(-3, 3) / 6 * 0.4 +
            df['is_high_value'] * 0.3 +
            df['is_short_session'] * 0.2 +
            (df['payment_status'] == 'failed').astype(float) * 0.1
        ).clip(0, 1)
        
        # 11. Velocity features
        df['user_transaction_count'] = df.groupby('user_id')['transaction_id'].transform('count')
        df['user_total_amount'] = df.groupby('user_id')['amount'].transform('sum')
        df['user_avg_transaction'] = df['user_total_amount'] / (df['user_transaction_count'] + 1)
        
        # 12. Bulk purchase flag
        df['is_bulk_purchase'] = (df['quantity'] >= 3).astype(int)
        
        # 13. Hour of day
        df['hour_of_day'] = df['timestamp'].dt.hour
        
        # ========== IDENTITY FEATURES ==========
        # 14. Identity mismatch score
        df['identity_mismatch_score'] = 0.0
        df.loc[df['account_age_days'] < 7, 'identity_mismatch_score'] += 0.3
        df.loc[df['account_status'] == 'new', 'identity_mismatch_score'] += 0.2
        df['identity_mismatch_score'] = df['identity_mismatch_score'].clip(0, 1)
        
        # 15. Identity verification score
        df['identity_verification_score'] = 0.7
        df.loc[df['account_status'] == 'verified', 'identity_verification_score'] = 0.95
        df.loc[df['account_status'] == 'new', 'identity_verification_score'] = 0.3
        df.loc[df['account_status'] == 'suspended', 'identity_verification_score'] = 0.1
        
        # 16. Identity confidence score
        df['identity_confidence_score'] = (
            df['identity_verification_score'] * 0.6 + 
            (1 - df['identity_mismatch_score']) * 0.4
        )
        
        # ========== DEVICE FEATURES ==========
        # 17. Device fingerprint score
        device_counts = df.groupby('device_id')['user_id'].nunique()
        device_user_count = df['device_id'].map(device_counts).fillna(1)
        df['device_fingerprint_score'] = 1 - (device_user_count - 1).clip(0, 10) / 10
        
        # 18. Android emulator detection
        df['android_emulator_detection'] = (
            (df['device_type'] == 'Mobile') & 
            (df['device_id'].fillna('').str.contains('emu|emulator|android', case=False, na=False) |
             df['browser'].fillna('').str.contains('Android', case=False, na=False))
        ).astype(int)
        
        # 19. Browser integrity score
        trusted_browsers = ['Chrome', 'Firefox', 'Safari', 'Edge']
        df['browser_integrity_score'] = df['browser'].isin(trusted_browsers).astype(float).clip(0, 1)
        
        # 20. Device trust score
        df['device_trust_score'] = (
            df['device_fingerprint_score'] * 0.5 +
            (1 - df['android_emulator_detection']) * 0.3 +
            df['browser_integrity_score'] * 0.2
        )
        
        # 21. Device change rate
        df['device_change_rate'] = df.groupby('user_id')['device_id'].transform(
            lambda x: x.nunique() / len(x) if len(x) > 0 else 0
        )
        
        # ========== LOCATION FEATURES ==========
        # 22. IP risk score
        df['ip_risk_score'] = 0.0
        df.loc[df['ip_address'].fillna('').str.startswith('100.'), 'ip_risk_score'] += 0.5
        df.loc[df['ip_address'].fillna('').str.startswith('200.'), 'ip_risk_score'] += 0.5
        df['ip_risk_score'] = df['ip_risk_score'].clip(0, 1)
        
        # 23. Proxy detection flag
        df['proxy_detection_flag'] = (df['ip_risk_score'] > 0.6).astype(int)
        
        # 24. VPN usage flag
        df['vpn_usage_flag'] = (df['ip_risk_score'] > 0.4).astype(int)
        
        # ========== PAYMENT FEATURES ==========
        # 25. Failed payment ratio
        user_payment_stats = df.groupby('user_id').agg({
            'payment_status': lambda x: (x == 'failed').sum() / len(x) if len(x) > 0 else 0
        }).rename(columns={'payment_status': 'failed_payment_ratio'})
        df = df.merge(user_payment_stats, left_on='user_id', right_index=True, how='left')
        df['failed_payment_ratio'] = df['failed_payment_ratio'].fillna(0)
        
        # 26. Current order value ratio
        user_avg_amount = df.groupby('user_id')['amount'].transform('mean')
        df['current_order_value_ratio'] = df['amount'] / (user_avg_amount + 1)
        
        # 27. Payment method anomaly
        user_payment_methods = df.groupby('user_id')['payment_method'].transform('nunique')
        df['payment_method_anomaly'] = (user_payment_methods > 3).astype(int)
        
        # 28. Payment anomaly score
        df['payment_anomaly_score'] = (
            df['failed_payment_ratio'] * 0.4 +
            (df['current_order_value_ratio'] > 3).astype(float) * 0.3 +
            df['payment_method_anomaly'] * 0.3
        )
        
        # 29. Payment status risk
        df['payment_status_risk'] = (df['payment_status'].isin(['failed', 'pending'])).astype(int)
        
        # ========== NETWORK FEATURES ==========
        # 30. Fraud ring score
        ip_user_count = df.groupby('ip_address')['user_id'].transform('nunique')
        device_user_count_net = df.groupby('device_id')['user_id'].transform('nunique')
        df['fraud_ring_score'] = ((ip_user_count > 5) | (device_user_count_net > 3)).astype(float) * 0.7
        
        # 31. Vendor risk score. A vendor's past fraud rate needs labels known *before* each
        # transaction (point-in-time). It used to be the vendor's fraud rate over the whole frame,
        # including the row's own label and later rows: target leakage in training, and always 0 at
        # serving. Kept as a constant placeholder until a point-in-time label store exists.
        df['vendor_risk_score'] = 0.0
            
        # 32. User reputation score
        df['user_reputation_score'] = 0.7
        df.loc[df['account_status'] == 'verified', 'user_reputation_score'] = 0.9
        df.loc[df['account_status'] == 'new', 'user_reputation_score'] = 0.4
        df.loc[df['account_status'] == 'suspended', 'user_reputation_score'] = 0.1
        df['user_reputation_score'] -= df['failed_payment_ratio'] * 0.3
        df['user_reputation_score'] = df['user_reputation_score'].clip(0, 1)
        
        # 33-34. Shared counts
        df['shared_ip_count'] = df.groupby('ip_address')['user_id'].transform('nunique')
        df['shared_phone_number_count'] = df.groupby('phone_number')['user_id'].transform('nunique')
        
        # ========== BEHAVIORAL FEATURES ==========
        # 35. Activity timing score
        is_night = ((df['hour_of_day'] >= 22) | (df['hour_of_day'] <= 5)).astype(int)
        median_hour = df.groupby('user_id')['hour_of_day'].transform('median').fillna(df['hour_of_day'].median())
        hour_dev = (df['hour_of_day'] - median_hour).abs()
        hour_dev_norm = (hour_dev / 12).clip(0, 1)
        df['activity_timing_score'] = (is_night * 0.6 + hour_dev_norm * 0.4).clip(0, 1)
        
        # 36. Anomaly frequency score
        df['anomaly_frequency_score'] = (
            (df['user_transaction_count'] > 10).astype(float) * 0.4 +
            (df['amount'] > 100000).astype(float) * 0.3 +
            (df['is_short_session']).astype(float) * 0.3
        )
        
        # 37. Behavioral consistency score
        df['behavioral_consistency_score'] = 1 - df['anomaly_frequency_score']
        
        # 38. Session behavior score
        df['session_behavior_score'] = 1 - (
            (df['is_short_session']).astype(float) * 0.5 +
            (df['action'] == 'purchase').astype(float) * 0.3
        )
        
        # ========== PRODUCT/PRICE FEATURES ==========
        # 39. Product price anomaly score
        category_avg_price = df.groupby('category')['price'].transform('mean')
        df['product_price_anomaly_score'] = (
            (df['price'] / (category_avg_price + 1)) - 1
        ).abs().clip(0, 2) / 2
        
        # ========== ADDRESS FEATURES ==========
        # 40. Address reuse rate
        df['address_reuse_rate'] = df.groupby('user_id')['delivery_address'].transform(
            lambda x: 1 - (x.nunique() / len(x)) if len(x) > 0 else 0
        )
        
        # 41. Shared address count
        df['shared_address_count'] = df.groupby('delivery_address')['user_id'].transform('nunique')
        
        # ========== DELIVERY/REFUND FEATURES ==========
        # 42. Refund abuse score
        user_refund_rate = df.groupby('user_id')['return_request'].transform('mean').fillna(0)
        df['refund_abuse_score'] = user_refund_rate
        
        # 43. Failed delivery pattern
        df['failed_delivery_pattern'] = (
            (df['payment_status'] == 'failed') & 
            (df['action'] == 'purchase')
        ).astype(int)
        
        # 44. Refund to purchase ratio
        user_purchase_count = df[df['action'] == 'purchase'].groupby('user_id').size()
        user_refund_count = df[df['return_request'] == True].groupby('user_id').size()
        refund_ratio = (user_refund_count / user_purchase_count).fillna(0)
        df['refund_to_purchase_ratio'] = df['user_id'].map(refund_ratio).fillna(0)
        
        # 45. Delivery dispute rate
        df['delivery_dispute_rate'] = (
            (df['return_request'] == True) & 
            (df['refund_status'].isin(['requested', 'approved']))
        ).astype(float)
        df['delivery_dispute_rate'] = df.groupby('user_id')['delivery_dispute_rate'].transform('mean').fillna(0)
        
        # 46. Refund severity score
        refund_severity_map = {
            'none': 0, 'requested': 0.3, 'approved': 0.6, 'completed': 0.8, 'denied': 0.2
        }
        df['refund_severity_score'] = df['refund_status'].map(refund_severity_map).fillna(0)
        
        # ========== AGGREGATE FEATURES ==========
        df['month'] = df['timestamp'].dt.month
        df['price_discount_ratio'] = df['discount'] / (df['price'].abs() + 1)
        
        # AGGREGATION FEATURES
        df['amount_per_quantity'] = df['amount'] / (df['quantity'] + 1)
        df['vendor_avg_quantity'] = df.groupby('vendor_id')['quantity'].transform('mean').fillna(0)
        df['user_avg_session_duration'] = df.groupby('user_id')['session_duration'].transform('mean').fillna(0)
        df['product_popularity'] = df.groupby('product_id')['transaction_id'].transform('count') / max(1, len(df))
        df['vendor_unique_products'] = df.groupby('vendor_id')['product_id'].transform('nunique').fillna(0)
        df['country_avg_amount'] = df.groupby('country')['amount'].transform('mean').fillna(0)
        df['time_since_prev_txn_sec'] = df.groupby('user_id')['timestamp'].diff().dt.total_seconds().fillna(0)
        
        return df





