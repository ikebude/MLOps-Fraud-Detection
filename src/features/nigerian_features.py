#!/usr/bin/env python3
"""
Nigerian Market-Specific Fraud Feature Engineering

This module extracts features critical to Nigerian e-commerce:
- Pay on Delivery (PoD) - 95% of transactions
- Phone number based tracking
- Delivery partner integration
- Mobile money patterns
- Seller-side marketplace fraud

Author: MLOps Team
Date: 2026-03-07
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import psycopg2
from psycopg2 import pool
from dotenv import load_dotenv
import redis

load_dotenv()
logger = logging.getLogger(__name__)

class NigerianMarketFeatureEngine:
    """
    Extract Nigerian e-commerce specific fraud features
    """
    
    def __init__(self):
        """Initialize feature engine with DB and cache connections"""
        self.db_pool = self._init_db_pool()
        self.redis_client = redis.Redis(
            host=os.getenv('REDIS_HOST', 'localhost'),
            port=int(os.getenv('REDIS_PORT', 6379)),
            decode_responses=True
        )
        self.phone_blacklist = set()
        self._load_blacklists()
    
    def _init_db_pool(self):
        """Create database connection pool"""
        return pool.ThreadedConnectionPool(
            minconn=2,
            maxconn=10,
            host=os.getenv('DB_HOST', 'postgres'),
            port=int(os.getenv('DB_PORT', 5432)),
            database=os.getenv('DB_NAME', 'transactions_db'),
            user=os.getenv('DB_USER', 'fraud_producer'),
            password=os.getenv('DB_PASSWORD', 'producer_password')
        )
    
    def _load_blacklists(self):
        """Load known fraud phone numbers and addresses from cache"""
        try:
            cached = self.redis_client.get('fraud_phone_blacklist')
            if cached:
                self.phone_blacklist = set(cached.split(','))
            else:
                # Load from DB if not cached
                conn = self.db_pool.getconn()
                cur = conn.cursor()
                cur.execute("SELECT phone_number FROM fraud_phone_blacklist WHERE is_active = true")
                self.phone_blacklist = set([row[0] for row in cur.fetchall()])
                cur.close()
                conn.close()
                
                # Cache for 24 hours
                self.redis_client.setex(
                    'fraud_phone_blacklist',
                    86400,
                    ','.join(self.phone_blacklist)
                )
        except Exception as e:
            logger.warning(f"Could not load blacklist: {e}")
    
    # ========================
    # PoD FEATURES (CRITICAL)
    # ========================
    
    def extract_pod_features(self, order: Dict) -> Dict[str, float]:
        """
        Extract Pay on Delivery features
        PoD is 95% of Nigerian e-commerce - CRITICAL for accuracy
        """
        if order.get('payment_method') != 'POD':
            return {}
        
        features = {}
        phone = order.get('phone_number')
        delivery_addr = order.get('delivery_address')
        
        if not phone:
            return features
        
        try:
            # Phone-based features (CRITICAL)
            features['pod_phone_txn_count_24h'] = self._count_phone_transactions(
                phone, hours=24
            )
            features['pod_phone_txn_count_7d'] = self._count_phone_transactions(
                phone, hours=168
            )
            features['pod_phone_failed_deliveries_7d'] = self._count_failed_deliveries(
                phone, days=7
            )
            features['pod_phone_failed_delivery_rate'] = self._get_failure_rate(
                phone, days=30
            )
            features['pod_phone_first_seen_age_days'] = self._get_phone_age(phone)
            features['pod_phone_is_blacklisted'] = 1.0 if phone in self.phone_blacklist else 0.0
            features['pod_phone_linked_accounts'] = self._count_linked_accounts(phone)
            
            # Delivery address clustering
            if delivery_addr:
                features['pod_address_txn_count_7d'] = self._count_address_transactions(
                    delivery_addr, days=7
                )
                features['pod_address_unique_phones'] = self._count_unique_phones_at_address(
                    delivery_addr, days=30
                )
                features['pod_address_cluster_risk_score'] = self._calculate_address_risk(
                    delivery_addr
                )
                features['pod_shipping_address_matches_billing'] = 1.0 if self._addresses_match(
                    order.get('billing_address'), delivery_addr
                ) else 0.0
            
            # Order acceptance patterns
            features['pod_customer_accept_rate'] = self._get_accept_rate(
                order['customer_id'], method='POD'
            )
            features['pod_customer_chargeback_rate'] = self._get_chargeback_rate(
                order['customer_id'], method='POD'
            )
            
            # Time-based patterns
            hour = self._get_hour_from_timestamp(order.get('created_at'))
            features['pod_order_at_high_risk_hour'] = 1.0 if hour in [22, 23, 0, 1, 2, 3, 4, 5] else 0.0
            
            # Amount patterns for PoD
            avg_amount = self._get_average_amount_for_phone(phone, days=30)
            current_amount = float(order.get('amount', 0))
            features['pod_amount_vs_avg_ratio'] = (
                current_amount / avg_amount if avg_amount > 0 else 1.0
            )
            features['pod_amount_exceeds_typical_threshold'] = 1.0 if current_amount > 200000 else 0.0
            
        except Exception as e:
            logger.error(f"Error extracting PoD features: {e}")
        
        return features
    
    # ===========================
    # DELIVERY PARTNER FEATURES
    # ===========================
    
    def extract_delivery_partner_features(self, order: Dict) -> Dict[str, float]:
        """Track delivery partner performance and patterns"""
        features = {}
        partner_id = order.get('delivery_partner_id')
        
        if not partner_id:
            return features
        
        try:
            features['delivery_partner_dispute_rate'] = self._get_delivery_partner_dispute_rate(
                partner_id
            )
            features['delivery_partner_is_verified'] = 1.0 if self._is_delivery_partner_verified(
                partner_id
            ) else 0.0
            features['delivery_partner_avg_cases_per_day'] = self._get_partner_volume(
                partner_id, days=7
            )
            features['delivery_partner_average_delivery_time'] = self._get_avg_delivery_time(
                partner_id
            )
        except Exception as e:
            logger.error(f"Error extracting delivery partner features: {e}")
        
        return features
    
    # ===========================
    # MOBILE MONEY FEATURES
    # ===========================
    
    def extract_mobile_money_features(self, transaction: Dict) -> Dict[str, float]:
        """Mobile money special cases (MTN, Airtel, Glo)"""
        if transaction.get('payment_method') not in ['MOBILE_MONEY', 'USSD']:
            return {}
        
        features = {}
        provider = transaction.get('mobile_provider', 'UNKNOWN')
        phone = transaction.get('phone_number')
        
        try:
            features['mobile_money_is_international'] = 1.0 if self._is_cross_border(
                transaction
            ) else 0.0
            features['mobile_money_is_new_recipient'] = 1.0 if not self._has_previous_transfer(
                phone, transaction.get('recipient')
            ) else 0.0
            features['mobile_money_self_transfer'] = 1.0 if self._is_self_transfer(
                transaction
            ) else 0.0
            features['mobile_money_provider_mismatch'] = 1.0 if self._has_provider_mismatch(
                transaction
            ) else 0.0
            features['mobile_money_in_velocity_window'] = self._count_mm_transactions_window(
                phone, minutes=5
            )
        except Exception as e:
            logger.error(f"Error extracting mobile money features: {e}")
        
        return features
    
    # ===========================
    # SELLER-SIDE MARKETPLACE
    # ===========================
    
    def extract_seller_fraud_features(self, seller_id: str, order: Dict) -> Dict[str, float]:
        """Detect marketplace seller-side fraud"""
        features = {}
        
        try:
            seller = self._get_seller(seller_id)
            
            features['seller_account_age_days'] = self._get_account_age(seller_id)
            features['seller_listing_velocity_24h'] = self._count_seller_listings(
                seller_id, hours=24
            )
            features['seller_product_image_reuse_count'] = self._count_duplicate_images(
                seller_id
            )
            features['seller_ai_generated_images_flag'] = 1.0 if self._has_ai_images(
                seller_id
            ) else 0.0
            features['seller_chargeback_rate'] = self._get_seller_chargeback_rate(seller_id)
            features['seller_return_rate'] = self._get_seller_return_rate(seller_id)
            features['seller_order_fulfillment_time_avg'] = self._get_fulfillment_time(seller_id)
            features['seller_is_verified_vendor'] = 1.0 if self._is_verified_seller(
                seller_id
            ) else 0.0
            
        except Exception as e:
            logger.error(f"Error extracting seller features: {e}")
        
        return features
    
    # ===========================
    # HELPER METHODS
    # ===========================
    
    def _count_phone_transactions(self, phone: str, hours: int = 24) -> float:
        """Count transactions by phone number in time window"""
        try:
            cached = self.redis_client.get(f"phone_txn_count:{phone}:{hours}h")
            if cached:
                return float(cached)
            
            conn = self.db_pool.getconn()
            cur = conn.cursor()
            cur.execute("""
                SELECT COUNT(*) FROM transactions 
                WHERE phone_number = %s 
                AND created_at >= NOW() - INTERVAL '%s hours'
            """, (phone, hours))
            count = float(cur.fetchone()[0])
            cur.close()
            conn.close()
            
            # Cache for 5 minutes
            self.redis_client.setex(
                f"phone_txn_count:{phone}:{hours}h",
                300,
                str(count)
            )
            return count
        except Exception as e:
            logger.warning(f"Error counting phone transactions: {e}")
            return 0.0
    
    def _count_failed_deliveries(self, phone: str, days: int) -> float:
        """Count failed/unfulfilled deliveries by phone"""
        try:
            conn = self.db_pool.getconn()
            cur = conn.cursor()
            cur.execute("""
                SELECT COUNT(*) FROM transactions 
                WHERE phone_number = %s 
                AND delivery_status IN ('FAILED', 'REJECTED', 'CANCELLED')
                AND created_at >= NOW() - INTERVAL '%s days'
            """, (phone, days))
            count = float(cur.fetchone()[0])
            cur.close()
            conn.close()
            return count
        except Exception as e:
            logger.warning(f"Error counting failed deliveries: {e}")
            return 0.0
    
    def _get_failure_rate(self, phone: str, days: int) -> float:
        """Calculate delivery failure rate for phone"""
        try:
            conn = self.db_pool.getconn()
            cur = conn.cursor()
            cur.execute("""
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN delivery_status IN ('FAILED', 'REJECTED', 'CANCELLED') 
                        THEN 1 ELSE 0 END) as failed
                FROM transactions 
                WHERE phone_number = %s 
                AND created_at >= NOW() - INTERVAL '%s days'
            """, (phone, days))
            total, failed = cur.fetchone()
            cur.close()
            conn.close()
            
            if total == 0:
                return 0.0
            return float(failed) / float(total)
        except Exception as e:
            logger.warning(f"Error calculating failure rate: {e}")
            return 0.0
    
    def _get_phone_age(self, phone: str) -> float:
        """Days since first transaction from this phone"""
        try:
            conn = self.db_pool.getconn()
            cur = conn.cursor()
            cur.execute("""
                SELECT EXTRACT(DAY FROM NOW() - MIN(created_at)) as age_days
                FROM transactions 
                WHERE phone_number = %s
            """, (phone,))
            row = cur.fetchone()
            age = float(row[0]) if row and row[0] else 0
            cur.close()
            conn.close()
            return age
        except Exception as e:
            logger.warning(f"Error getting phone age: {e}")
            return 0.0
    
    def _count_linked_accounts(self, phone: str) -> float:
        """Count unique customer accounts using this phone"""
        try:
            conn = self.db_pool.getconn()
            cur = conn.cursor()
            cur.execute("""
                SELECT COUNT(DISTINCT customer_id) FROM transactions 
                WHERE phone_number = %s
            """, (phone,))
            count = float(cur.fetchone()[0])
            cur.close()
            conn.close()
            return count
        except Exception as e:
            logger.warning(f"Error counting linked accounts: {e}")
            return 1.0  # At least 1 (the customer itself)
    
    def _count_address_transactions(self, address: str, days: int) -> float:
        """Count transactions to a specific address"""
        try:
            conn = self.db_pool.getconn()
            cur = conn.cursor()
            cur.execute("""
                SELECT COUNT(*) FROM transactions 
                WHERE delivery_address = %s 
                AND created_at >= NOW() - INTERVAL '%s days'
            """, (address, days))
            count = float(cur.fetchone()[0])
            cur.close()
            conn.close()
            return count
        except Exception as e:
            logger.warning(f"Error counting address transactions: {e}")
            return 0.0
    
    def _count_unique_phones_at_address(self, address: str, days: int) -> float:
        """Count unique phone numbers shipping to this address"""
        try:
            conn = self.db_pool.getconn()
            cur = conn.cursor()
            cur.execute("""
                SELECT COUNT(DISTINCT phone_number) FROM transactions 
                WHERE delivery_address = %s 
                AND created_at >= NOW() - INTERVAL '%s days'
            """, (address, days))
            count = float(cur.fetchone()[0])
            cur.close()
            conn.close()
            return count
        except Exception as e:
            logger.warning(f"Error counting unique phones: {e}")
            return 1.0
    
    def _calculate_address_risk(self, address: str) -> float:
        """Calculate fraud risk score for an address"""
        try:
            # Address with many transactions = higher risk of bulk fraud
            txn_count = self._count_address_transactions(address, days=30)
            unique_phones = self._count_unique_phones_at_address(address, days=30)
            
            if txn_count == 0:
                return 0.0
            
            # High phone reuse = fraud ring indicator
            phone_reuse_ratio = txn_count / unique_phones if unique_phones > 0 else 1.0
            
            # Scale to 0-1
            risk_score = min(phone_reuse_ratio / 5.0, 1.0)
            return risk_score
        except Exception as e:
            logger.warning(f"Error calculating address risk: {e}")
            return 0.0
    
    def _addresses_match(self, addr1: str, addr2: str) -> bool:
        """Check if two addresses match (fuzzy)"""
        if not addr1 or not addr2:
            return False
        
        # Simple string similarity (in production use fuzzy matching)
        return addr1.lower().strip() == addr2.lower().strip()
    
    def _get_accept_rate(self, customer_id: str, method: str = None) -> float:
        """Rate at which customer accepts/receives delivered items"""
        try:
            conn = self.db_pool.getconn()
            cur = conn.cursor()
            
            if method:
                cur.execute("""
                    SELECT 
                        COUNT(*) as total,
                        SUM(CASE WHEN delivery_status = 'DELIVERED' THEN 1 ELSE 0 END) as accepted
                    FROM transactions 
                    WHERE customer_id = %s 
                    AND payment_method = %s
                    AND created_at >= NOW() - INTERVAL '30 days'
                """, (customer_id, method))
            else:
                cur.execute("""
                    SELECT 
                        COUNT(*) as total,
                        SUM(CASE WHEN delivery_status = 'DELIVERED' THEN 1 ELSE 0 END) as accepted
                    FROM transactions 
                    WHERE customer_id = %s 
                    AND created_at >= NOW() - INTERVAL '30 days'
                """, (customer_id,))
            
            total, accepted = cur.fetchone()
            cur.close()
            conn.close()
            
            if total == 0:
                return 1.0  # New customer - assume good
            return float(accepted) / float(total)
        except Exception as e:
            logger.warning(f"Error getting accept rate: {e}")
            return 0.5  # Unknown = medium risk
    
    def _get_chargeback_rate(self, customer_id: str, method: str = None) -> float:
        """Chargeback rate for customer"""
        try:
            conn = self.db_pool.getconn()
            cur = conn.cursor()
            
            if method:
                cur.execute("""
                    SELECT 
                        COUNT(*) as total,
                        SUM(CASE WHEN has_chargeback = true THEN 1 ELSE 0 END) as chargebacks
                    FROM transactions 
                    WHERE customer_id = %s 
                    AND payment_method = %s
                    AND created_at >= NOW() - INTERVAL '90 days'
                """, (customer_id, method))
            else:
                cur.execute("""
                    SELECT 
                        COUNT(*) as total,
                        SUM(CASE WHEN has_chargeback = true THEN 1 ELSE 0 END) as chargebacks
                    FROM transactions 
                    WHERE customer_id = %s 
                    AND created_at >= NOW() - INTERVAL '90 days'
                """, (customer_id,))
            
            total, chargebacks = cur.fetchone()
            cur.close()
            conn.close()
            
            if total == 0:
                return 0.0
            return float(chargebacks) / float(total)
        except Exception as e:
            logger.warning(f"Error getting chargeback rate: {e}")
            return 0.0
    
    def _get_hour_from_timestamp(self, ts: str) -> int:
        """Extract hour from timestamp"""
        try:
            if isinstance(ts, str):
                dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
            else:
                dt = ts
            return dt.hour
        except:
            return 12
    
    def _get_average_amount_for_phone(self, phone: str, days: int) -> float:
        """Average transaction amount for a phone"""
        try:
            conn = self.db_pool.getconn()
            cur = conn.cursor()
            cur.execute("""
                SELECT AVG(amount) FROM transactions 
                WHERE phone_number = %s 
                AND created_at >= NOW() - INTERVAL '%s days'
            """, (phone, days))
            avg = cur.fetchone()[0]
            cur.close()
            conn.close()
            return float(avg) if avg else 50000.0
        except Exception as e:
            logger.warning(f"Error getting average amount: {e}")
            return 50000.0
    
    def _get_delivery_partner_dispute_rate(self, partner_id: str) -> float:
        """Dispute rate for delivery partner"""
        # TODO: Integrate with delivery partner API
        return 0.0
    
    def _is_delivery_partner_verified(self, partner_id: str) -> bool:
        """Check if delivery partner is officially verified"""
        # TODO: Check partner verification status
        return False
    
    def _get_partner_volume(self, partner_id: str, days: int) -> float:
        """Average cases per day for delivery partner"""
        # TODO: Query partner volume
        return 0.0
    
    def _get_avg_delivery_time(self, partner_id: str) -> float:
        """Average delivery time in hours"""
        # TODO: Calculate from delivery tracking
        return 24.0
    
    def _is_cross_border(self, transaction: Dict) -> bool:
        """Check if money leaving Nigeria"""
        return transaction.get('receiver_country') != 'NG'
    
    def _has_previous_transfer(self, sender: str, recipient: str) -> bool:
        """Check if sender has previously transferred to recipient"""
        # TODO: Implement
        return False
    
    def _is_self_transfer(self, transaction: Dict) -> bool:
        """Check if transferring to own account"""
        return transaction.get('sender_id') == transaction.get('receiver_id')
    
    def _has_provider_mismatch(self, transaction: Dict) -> bool:
        """Check for provider mismatch"""
        # TODO: Implement
        return False
    
    def _count_mm_transactions_window(self, phone: str, minutes: int) -> float:
        """Count mobile money transactions in time window"""
        # TODO: Implement
        return 0.0
    
    def _get_seller(self, seller_id: str) -> Dict:
        """Get seller details"""
        # TODO: Implement
        return {}
    
    def _get_account_age(self, seller_id: str) -> float:
        """Days since seller account created"""
        # TODO: Implement
        return 0.0
    
    def _count_seller_listings(self, seller_id: str, hours: int) -> float:
        """New listings in time window"""
        # TODO: Implement
        return 0.0
    
    def _count_duplicate_images(self, seller_id: str) -> float:
        """Count duplicate product images"""
        # TODO: Implement with reverse image search
        return 0.0
    
    def _has_ai_images(self, seller_id: str) -> bool:
        """Detect AI-generated product images"""
        # TODO: Implement with AI detection
        return False
    
    def _get_seller_chargeback_rate(self, seller_id: str) -> float:
        """Seller chargeback rate"""
        # TODO: Implement
        return 0.0
    
    def _get_seller_return_rate(self, seller_id: str) -> float:
        """Seller return rate"""
        # TODO: Implement
        return 0.0
    
    def _get_fulfillment_time(self, seller_id: str) -> float:
        """Average fulfillment time in hours"""
        # TODO: Implement
        return 24.0
    
    def _is_verified_seller(self, seller_id: str) -> bool:
        """Check if seller is officially verified"""
        # TODO: Implement
        return False


# Singleton instance
_feature_engine = None

def get_nigerian_feature_engine():
    """Get or create singleton instance"""
    global _feature_engine
    if _feature_engine is None:
        _feature_engine = NigerianMarketFeatureEngine()
    return _feature_engine
