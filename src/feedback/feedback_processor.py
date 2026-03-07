#!/usr/bin/env python3
"""
Analyst Feedback Automation & Auto-Labeling Service

Automatically processes analyst decisions and feeds them back into the ML pipeline.
Enables continuous model improvement without manual data preparation.

Author: MLOps Team
Date: 2026-03-07
"""

import os
import logging
import psycopg2
from psycopg2 import pool
import redis
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dotenv import load_dotenv
import requests

load_dotenv()
logger = logging.getLogger(__name__)

class AnalystFeedbackProcessor:
    """
    Process analyst decisions and automatically create training examples
    """
    
    def __init__(self):
        """Initialize feedback processor"""
        self.db_pool = self._init_db_pool()
        self.redis_client = redis.Redis(
            host=os.getenv('REDIS_HOST', 'localhost'),
            port=int(os.getenv('REDIS_PORT', 6379)),
            decode_responses=True
        )
        self.airflow_url = os.getenv('AIRFLOW_WEBSERVER_URL', 'http://airflow-webserver:8080')
        
        # Decision to label mapping
        self.decision_label_map = {
            'APPROVE': 0,  # Legitimate
            'REJECT': 1,   # Fraud
            'CALL_VERIFIED': 0,  # Verified as legitimate
            'CALLED_NO_ANSWER': 1,  # Suspicious
            'ESCALATED': None,  # Unknown, requires follow-up
        }
        
        # Initialize feedback warehouse
        self._ensure_feedback_table()
    
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
    
    def _ensure_feedback_table(self):
        """Create feedback warehouse table if not exists"""
        try:
            conn = self.db_pool.getconn()
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS analyst_feedback (
                    id SERIAL PRIMARY KEY,
                    case_id VARCHAR(255) NOT NULL,
                    transaction_id VARCHAR(255) NOT NULL,
                    analyst_id VARCHAR(255) NOT NULL,
                    original_fraud_score FLOAT,
                    analyst_decision VARCHAR(50),
                    label SMALLINT,
                    confidence FLOAT DEFAULT 1.0,
                    features_json JSONB,
                    feedback_timestamp TIMESTAMP DEFAULT NOW(),
                    created_at TIMESTAMP DEFAULT NOW(),
                    UNIQUE(case_id, analyst_id)
                );
                
                CREATE INDEX IF NOT EXISTS idx_feedback_timestamp 
                ON analyst_feedback(feedback_timestamp);
                
                CREATE INDEX IF NOT EXISTS idx_feedback_label 
                ON analyst_feedback(label);
            """)
            conn.commit()
            cur.close()
            conn.close()
            logger.info("Feedback table verified")
        except Exception as e:
            logger.error(f"Error creating feedback table: {e}")
    
    def process_analyst_decision(self, decision_event: Dict[str, Any]) -> bool:
        """
        Process analyst decision and create training example
        
        Args:
            decision_event: {
                'case_id': 'FRD-12345',
                'transaction_id': 'TXN-ABC123',
                'analyst_id': 'chioma_001',
                'decision': 'REJECT',  # APPROVE, REJECT, CALL_VERIFIED, etc.
                'timestamp': '2026-03-07T10:30:00Z'
            }
        
        Returns:
            True if processed successfully
        """
        try:
            case_id = decision_event.get('case_id')
            logger.info(f"Processing analyst decision for {case_id}")
            
            # Get case from database
            case = self._get_case_from_database(case_id)
            if not case:
                logger.warning(f"Case not found: {case_id}")
                return False
            
            # Extract features from original transaction
            features = self._extract_features_from_case(case)
            
            # Map decision to label
            decision = decision_event.get('decision')
            label = self._decision_to_label(decision)
            
            # Determine confidence
            confidence = self._determine_confidence(decision)
            
            # Store in feedback warehouse
            feedback_record = {
                'case_id': case_id,
                'transaction_id': case.get('transaction_id'),
                'analyst_id': decision_event.get('analyst_id'),
                'original_fraud_score': case.get('fraud_probability', 0.0),
                'analyst_decision': decision,
                'label': label,
                'confidence': confidence,
                'features_json': features,
                'feedback_timestamp': decision_event.get('timestamp', datetime.now().isoformat()),
            }
            
            # Store feedback record
            self._store_feedback_record(feedback_record)
            
            # Update case metadata with feedback
            self._update_case_with_feedback(case_id, label)
            
            # Check if should trigger retraining
            self._check_retraining_trigger()
            
            logger.info(f"Successfully processed feedback for {case_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error processing analyst decision: {e}")
            return False
    
    def _get_case_from_database(self, case_id: str) -> Optional[Dict]:
        """Retrieve case details from database"""
        try:
            conn = self.db_pool.getconn()
            cur = conn.cursor()
            cur.execute("""
                SELECT 
                    transaction_id, customer_id, amount, fraud_probability,
                    features_json, created_at, analyst_id, decision
                FROM fraud_predictions
                WHERE case_id = %s
            """, (case_id,))
            
            row = cur.fetchone()
            cur.close()
            conn.close()
            
            if not row:
                return None
            
            return {
                'case_id': case_id,
                'transaction_id': row[0],
                'customer_id': row[1],
                'amount': row[2],
                'fraud_probability': row[3],
                'features_json': row[4],
                'created_at': row[5],
                'analyst_id': row[6],
                'previous_decision': row[7],
            }
        except Exception as e:
            logger.error(f"Error retrieving case: {e}")
            return None
    
    def _extract_features_from_case(self, case: Dict) -> Dict[str, Any]:
        """Extract features from case for training"""
        features = {}
        
        try:
            # If features stored as JSON
            if case.get('features_json'):
                features = json.loads(case['features_json'])
            else:
                # Rebuild features from transaction
                conn = self.db_pool.getconn()
                cur = conn.cursor()
                cur.execute("""
                    SELECT * FROM transactions WHERE transaction_id = %s
                """, (case['transaction_id'],))
                
                txn = cur.fetchone()
                cur.close()
                conn.close()
                
                if txn:
                    features = self._build_features_from_transaction(txn)
        
        except Exception as e:
            logger.error(f"Error extracting features: {e}")
        
        return features
    
    def _build_features_from_transaction(self, txn) -> Dict:
        """Build feature dictionary from transaction"""
        # TODO: Implement based on your feature engineering logic
        return {}
    
    def _decision_to_label(self, decision: str) -> Optional[int]:
        """Convert analyst decision to ML label"""
        return self.decision_label_map.get(decision)
    
    def _determine_confidence(self, decision: str) -> float:
        """Determine confidence in analyst decision"""
        confidence_map = {
            'APPROVE': 0.95,  # High confidence
            'REJECT': 0.95,   # High confidence
            'CALL_VERIFIED': 0.98,  # Very high confidence (customer confirmed)
            'CALLED_NO_ANSWER': 0.80,  # Medium confidence (assumption)
            'ESCALATED': 0.5,  # Low confidence (needs follow-up)
        }
        return confidence_map.get(decision, 0.7)
    
    def _store_feedback_record(self, record: Dict):
        """Store feedback in warehouse"""
        try:
            conn = self.db_pool.getconn()
            cur = conn.cursor()
            
            cur.execute("""
                INSERT INTO analyst_feedback (
                    case_id, transaction_id, analyst_id, original_fraud_score,
                    analyst_decision, label, confidence, features_json,
                    feedback_timestamp
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (case_id, analyst_id) DO UPDATE SET
                    label = EXCLUDED.label,
                    analyst_decision = EXCLUDED.analyst_decision,
                    feedback_timestamp = NOW()
            """, (
                record['case_id'],
                record['transaction_id'],
                record['analyst_id'],
                record['original_fraud_score'],
                record['analyst_decision'],
                record['label'],
                record['confidence'],
                json.dumps(record['features_json']),
                record['feedback_timestamp'],
            ))
            
            conn.commit()
            cur.close()
            conn.close()
            logger.info(f"Stored feedback for {record['case_id']}")
            
        except Exception as e:
            logger.error(f"Error storing feedback: {e}")
    
    def _update_case_with_feedback(self, case_id: str, label: Optional[int]):
        """Update case record with feedback labels"""
        try:
            if label is None:
                return
            
            conn = self.db_pool.getconn()
            cur = conn.cursor()
            
            cur.execute("""
                UPDATE fraud_predictions
                SET analyst_label = %s, updated_at = NOW()
                WHERE case_id = %s
            """, (label, case_id))
            
            conn.commit()
            cur.close()
            conn.close()
            
        except Exception as e:
            logger.error(f"Error updating case: {e}")
    
    def _check_retraining_trigger(self):
        """Check if conditions met for automatic model retraining"""
        try:
            # Get feedback statistics
            stats = self._get_feedback_statistics()
            
            # Trigger 1: Feedback volume threshold
            if stats['feedback_24h'] > 1000:
                logger.info(f"Retraining trigger: High feedback volume ({stats['feedback_24h']} in 24h)")
                self._trigger_retraining(reason="high_feedback_volume")
                return
            
            # Trigger 2: Model accuracy degradation
            if self._detect_accuracy_degradation():
                logger.warning("Retraining trigger: Model accuracy degradation detected")
                self._trigger_retraining(reason="accuracy_degradation")
                return
            
            # Trigger 3: Feature drift
            if self._detect_feature_drift():
                logger.warning("Retraining trigger: Feature drift detected")
                self._trigger_retraining(reason="feature_drift")
                return
            
            # Trigger 4: Scheduled (e.g., weekly)
            if self._should_retrain_scheduled():
                logger.info("Retraining trigger: Scheduled retraining")
                self._trigger_retraining(reason="scheduled")
                return
            
        except Exception as e:
            logger.error(f"Error checking retraining trigger: {e}")
    
    def _get_feedback_statistics(self) -> Dict[str, int]:
        """Get feedback statistics"""
        try:
            conn = self.db_pool.getconn()
            cur = conn.cursor()
            
            # Feedback in last 24 hours
            cur.execute("""
                SELECT COUNT(*) FROM analyst_feedback
                WHERE feedback_timestamp >= NOW() - INTERVAL '24 hours'
                AND label IS NOT NULL
            """)
            feedback_24h = cur.fetchone()[0]
            
            # Total feedback
            cur.execute("SELECT COUNT(*) FROM analyst_feedback WHERE label IS NOT NULL")
            feedback_total = cur.fetchone()[0]
            
            # Model accuracy on feedback data
            cur.execute("""
                SELECT COUNT(*), 
                       SUM(CASE WHEN original_fraud_score > 0.5 = label THEN 1 ELSE 0 END)
                FROM analyst_feedback
                WHERE feedback_timestamp >= NOW() - INTERVAL '7 days'
            """)
            total, correct = cur.fetchone()
            accuracy = float(correct) / float(total) if total > 0 else 0
            
            cur.close()
            conn.close()
            
            return {
                'feedback_24h': feedback_24h,
                'feedback_total': feedback_total,
                'recent_accuracy': accuracy,
            }
            
        except Exception as e:
            logger.error(f"Error getting feedback statistics: {e}")
            return {'feedback_24h': 0, 'feedback_total': 0, 'recent_accuracy': 0}
    
    def _detect_accuracy_degradation(self) -> bool:
        """Detect if model accuracy has degraded"""
        try:
            # Compare recent predictions vs analyst feedback
            conn = self.db_pool.getconn()
            cur = conn.cursor()
            
            cur.execute("""
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN (original_fraud_score > 0.5) = label THEN 1 ELSE 0 END) as correct
                FROM analyst_feedback
                WHERE feedback_timestamp >= NOW() - INTERVAL '7 days'
            """)
            
            total, correct = cur.fetchone()
            cur.close()
            conn.close()
            
            if total == 0:
                return False
            
            accuracy = float(correct) / float(total)
            threshold = 0.90  # Retrain if accuracy drops below 90%
            
            is_degraded = accuracy < threshold
            logger.info(f"Model accuracy on feedback: {accuracy:.2%} (threshold: {threshold:.2%})")
            
            return is_degraded
            
        except Exception as e:
            logger.error(f"Error detecting accuracy degradation: {e}")
            return False
    
    def _detect_feature_drift(self) -> bool:
        """Detect if feature distributions have drifted"""
        try:
            # Compare feature statistics from recent data vs training data
            # TODO: Implement actual feature drift detection
            # Could use:
            # - Kolmogorov-Smirnov test
            # - Wasserstein distance
            # - Jensen-Shannon divergence
            
            return False
            
        except Exception as e:
            logger.error(f"Error detecting feature drift: {e}")
            return False
    
    def _should_retrain_scheduled(self) -> bool:
        """Check if scheduled retraining should happen"""
        try:
            # Get last retraining timestamp
            last_retrain = self.redis_client.get('last_retraining_timestamp')
            
            if not last_retrain:
                # No previous retraining, schedule one
                return False
            
            last_retrain_dt = datetime.fromisoformat(last_retrain)
            days_since = (datetime.now() - last_retrain_dt).days
            
            # Retrain weekly
            return days_since >= 7
            
        except Exception as e:
            logger.error(f"Error checking scheduled retraining: {e}")
            return False
    
    def _trigger_retraining(self, reason: str = "manual"):
        """Trigger Airflow DAG for model retraining"""
        try:
            # Get current training data count
            conn = self.db_pool.getconn()
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM analyst_feedback WHERE label IS NOT NULL")
            training_examples = cur.fetchone()[0]
            cur.close()
            conn.close()
            
            logger.info(f"Triggering model retraining with {training_examples} examples")
            
            # Trigger Airflow DAG
            dag_id = 'fraud_detection_training_dag'
            conf = {
                'reason': reason,
                'training_examples': training_examples,
                'triggered_at': datetime.now().isoformat(),
            }
            
            # POST to Airflow API
            response = requests.post(
                f"{self.airflow_url}/api/v1/dags/{dag_id}/dagRuns",
                json={'conf': conf},
                headers={'Content-Type': 'application/json'},
                timeout=10
            )
            
            if response.status_code in [200, 201]:
                logger.info(f"Successfully triggered {dag_id}")
                # Store retraining timestamp
                self.redis_client.set(
                    'last_retraining_timestamp',
                    datetime.now().isoformat()
                )
            else:
                logger.error(f"Failed to trigger Airflow DAG: {response.text}")
            
        except Exception as e:
            logger.error(f"Error triggering retraining: {e}")
    
    def get_feedback_summary(self) -> Dict[str, Any]:
        """Get summary of feedback and model impact"""
        try:
            conn = self.db_pool.getconn()
            cur = conn.cursor()
            
            # Overall statistics
            cur.execute("""
                SELECT 
                    COUNT(*) as total_feedback,
                    SUM(CASE WHEN label = 0 THEN 1 ELSE 0 END) as legitimate,
                    SUM(CASE WHEN label = 1 THEN 1 ELSE 0 END) as fraudulent,
                    AVG(confidence) as avg_confidence
                FROM analyst_feedback
            """)
            total, legit, fraud, avg_conf = cur.fetchone()
            
            # Model accuracy vs expert judgement
            cur.execute("""
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN (original_fraud_score > 0.5) = label THEN 1 ELSE 0 END) as correct
                FROM analyst_feedback
            """)
            total_pred, correct_pred = cur.fetchone()
            
            cur.close()
            conn.close()
            
            accuracy = float(correct_pred) / float(total_pred) if total_pred > 0 else 0
            fraud_rate = float(fraud) / float(total) if total > 0 else 0
            
            return {
                'total_feedback': total or 0,
                'legitimate_cases': legit or 0,
                'fraudulent_cases': fraud or 0,
                'fraud_rate': fraud_rate,
                'average_confidence': avg_conf or 0,
                'model_accuracy_on_feedback': accuracy,
                'summary': f"{total or 0} analyst decisions processed, {fraud or 0} fraud cases confirmed"
            }
            
        except Exception as e:
            logger.error(f"Error getting feedback summary: {e}")
            return {}


# Singleton
_feedback_processor = None

def get_feedback_processor() -> AnalystFeedbackProcessor:
    """Get or create processor instance"""
    global _feedback_processor
    if _feedback_processor is None:
        _feedback_processor = AnalystFeedbackProcessor()
    return _feedback_processor


if __name__ == '__main__':
    processor = get_feedback_processor()
    
    # Example: Process analyst decision
    example_event = {
        'case_id': 'FRD-12345',
        'transaction_id': 'TXN-ABC123',
        'analyst_id': 'chioma_001',
        'decision': 'REJECT',
        'timestamp': datetime.now().isoformat(),
    }
    
    processor.process_analyst_decision(example_event)
    
    # Get summary
    summary = processor.get_feedback_summary()
    print(json.dumps(summary, indent=2))
