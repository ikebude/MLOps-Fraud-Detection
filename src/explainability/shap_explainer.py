#!/usr/bin/env python3
"""
SHAP Explainability Service for Moniguard

Generates human-readable explanations for fraud decisions using SHAP values.
Integrates with the fraud detection API to provide analysts with clear reasoning.

Author: MLOps Team
Date: 2026-03-07
"""

import os
import logging
import joblib
import numpy as np
import json
from typing import Dict, List, Any, Optional
from datetime import datetime
import redis
from dotenv import load_dotenv

import shap
from flask import Flask, jsonify, request

load_dotenv()
logger = logging.getLogger(__name__)

class SHAPExplainer:
    """
    SHAP-based explainability service for fraud detection decisions
    """
    
    def __init__(self, model_path: str = None):
        """Initialize explainer with trained model"""
        self.model_path = model_path or os.getenv(
            'MODEL_PATH',
            '/app/models/fraud_detection_model.pkl'
        )
        
        # Load model
        self.model = self._load_model()
        
        # Initialize explainer (TreeExplainer for XGBoost/Random Forest)
        self.explainer = None
        self._init_explainer()
        
        # Redis for caching explanations
        self.redis_client = redis.Redis(
            host=os.getenv('REDIS_HOST', 'localhost'),
            port=int(os.getenv('REDIS_PORT', 6379)),
            decode_responses=True
        )
        
        # Feature names and descriptions
        self.feature_descriptions = self._load_feature_descriptions()
    
    def _load_model(self):
        """Load trained model from disk"""
        try:
            if not os.path.exists(self.model_path):
                raise FileNotFoundError(f"Model not found at {self.model_path}")
            
            model = joblib.load(self.model_path)
            logger.info(f"Model loaded from {self.model_path}")
            return model
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            raise
    
    def _init_explainer(self):
        """Initialize SHAP explainer"""
        try:
            # For tree-based models (XGBoost, Random Forest, LightGBM)
            if hasattr(self.model, 'feature_importances_'):
                # Use TreeExplainer for tree-based models
                self.explainer = shap.TreeExplainer(self.model)
                logger.info("TreeExplainer initialized")
            else:
                # Fallback to KernelExplainer for other models
                logger.warning("Using KernelExplainer - will be slower")
                # You could use a sample of background data here
                self.explainer = None
        except Exception as e:
            logger.error(f"Failed to initialize SHAP explainer: {e}")
            self.explainer = None
    
    def _load_feature_descriptions(self) -> Dict[str, str]:
        """Load human-readable feature descriptions"""
        return {
            # Generic features
            'amount': 'Transaction Amount (₦)',
            'customer_age_days': 'Customer Account Age (days)',
            'is_high_value': 'High-Value Transaction Flag',
            'ip_country_mismatch': 'IP Location Mismatch',
            'device_age_days': 'Device Age (days)',
            'is_new_device': 'New Device Flag',
            'has_vpn': 'VPN/Proxy Detected',
            
            # PoD Specific
            'pod_phone_txn_count_24h': 'Phone Transactions (24h)',
            'pod_phone_txn_count_7d': 'Phone Transactions (7d)',
            'pod_phone_failed_deliveries_7d': 'Failed Deliveries from Phone (7d)',
            'pod_phone_failed_delivery_rate': 'Phone Delivery Failure Rate',
            'pod_phone_is_blacklisted': 'Phone Number Blacklisted',
            'pod_phone_linked_accounts': 'Accounts Using This Phone',
            'pod_address_txn_count_7d': 'Transactions to Address (7d)',
            'pod_address_unique_phones': 'Unique Phones to Address',
            'pod_address_cluster_risk_score': 'Address Cluster Risk Score',
            'pod_customer_accept_rate': 'Customer Delivery Accept Rate',
            'pod_customer_chargeback_rate': 'Customer Chargeback Rate',
            'pod_order_at_high_risk_hour': 'Order During High-Risk Hours',
            'pod_amount_vs_avg_ratio': 'Amount vs Customer Average',
            'pod_amount_exceeds_typical_threshold': 'Amount > ₦200k',
            
            # Mobile Money
            'mobile_money_is_international': 'International Transfer',
            'mobile_money_is_new_recipient': 'New Recipient',
            'mobile_money_self_transfer': 'Self-Transfer',
            'mobile_money_in_velocity_window': 'Multiple Transfers in 5min',
            
            # Seller Fraud
            'seller_account_age_days': 'Seller Account Age (days)',
            'seller_listing_velocity_24h': 'Seller New Listings (24h)',
            'seller_chargeback_rate': 'Seller Chargeback Rate',
            'seller_is_verified_vendor': 'Verified Vendor',
        }
    
    def explain_transaction(self, features_dict: Dict, case_id: str = None) -> Dict[str, Any]:
        """
        Generate SHAP explanation for a transaction
        
        Args:
            features_dict: Dictionary of features for the transaction
            case_id: Optional case ID for caching
        
        Returns:
            Dictionary with explanation data
        """
        # Check cache
        if case_id:
            cached = self.redis_client.get(f"shap_explanation:{case_id}")
            if cached:
                return json.loads(cached)
        
        try:
            # Convert to feature array
            feature_array = self._dict_to_array(features_dict)
            
            # Get fraud probability from model
            fraud_probability = float(self.model.predict_proba(
                feature_array.reshape(1, -1)
            )[0, 1])
            
            # Get SHAP values
            if self.explainer:
                shap_values = self.explainer.shap_values(feature_array.reshape(1, -1))
                if isinstance(shap_values, list):
                    shap_values = shap_values[1]  # Fraud class
                shap_values = shap_values[0]
            else:
                logger.warning("SHAP explainer not available")
                shap_values = np.zeros(len(features_dict))
            
            # Build explanation
            explanation = {
                'fraud_probability': fraud_probability,
                'base_value': float(self.explainer.expected_value[1]) if self.explainer else 0.5,
                'top_factors': self._extract_top_factors(
                    shap_values, features_dict, fraud_probability
                ),
                'all_factors': self._extract_all_factors(
                    shap_values, features_dict
                ),
                'risk_category': self._categorize_risk(fraud_probability),
                'timestamp': datetime.now().isoformat(),
            }
            
            # Cache for 1 hour
            if case_id:
                self.redis_client.setex(
                    f"shap_explanation:{case_id}",
                    3600,
                    json.dumps(explanation, default=str)
                )
            
            return explanation
            
        except Exception as e:
            logger.error(f"Error explaining transaction: {e}")
            return {
                'fraud_probability': 0.0,
                'top_factors': [],
                'error': str(e)
            }
    
    def _dict_to_array(self, features_dict: Dict) -> np.ndarray:
        """Convert feature dictionary to array in correct order"""
        # TODO: Get feature order from model
        # For now, assuming features are in a standard order
        return np.array(list(features_dict.values()))
    
    def _extract_top_factors(
        self,
        shap_values: np.ndarray,
        features_dict: Dict,
        fraud_probability: float,
        top_n: int = 5
    ) -> List[Dict[str, Any]]:
        """Extract top N factors influencing decision"""
        factors = []
        feature_names = list(features_dict.keys())
        feature_values = list(features_dict.values())
        
        # Pair SHAP values with features
        factor_data = []
        for i, (name, value, shap_val) in enumerate(zip(
            feature_names, feature_values, shap_values
        )):
            factor_data.append({
                'name': name,
                'value': value,
                'shap_value': shap_val,
                'abs_shap_value': abs(shap_val),
                'description': self.feature_descriptions.get(name, name),
            })
        
        # Sort by absolute SHAP value (impact)
        factor_data.sort(key=lambda x: x['abs_shap_value'], reverse=True)
        
        # Convert to explainable format
        for factor in factor_data[:top_n]:
            # Interpret impact
            if factor['shap_value'] > 0:
                impact = "Increases Fraud Risk"
                impact_icon = "⬆️"
                impact_level = "INCREASES"
            else:
                impact = "Decreases Fraud Risk"
                impact_icon = "⬇️"
                impact_level = "DECREASES"
            
            # Format value based on data type
            if isinstance(factor['value'], float):
                formatted_value = f"{factor['value']:.2f}"
            elif isinstance(factor['value'], bool):
                formatted_value = "Yes" if factor['value'] else "No"
            else:
                formatted_value = str(factor['value'])
            
            # Create human-readable factor
            factors.append({
                'feature': factor['name'],
                'description': factor['description'],
                'value': formatted_value,
                'raw_value': factor['value'],
                'shap_contribution': float(factor['shap_value']),
                'impact': impact,
                'impact_icon': impact_icon,
                'impact_level': impact_level,
                'strength': self._categorize_strength(abs(factor['shap_value'])),
                'reasoning': self._generate_reasoning(
                    factor['name'],
                    factor['value'],
                    factor['shap_value'],
                    fraud_probability
                ),
            })
        
        return factors
    
    def _extract_all_factors(
        self,
        shap_values: np.ndarray,
        features_dict: Dict
    ) -> List[Dict[str, Any]]:
        """Extract all factors for detailed view"""
        factors = []
        feature_names = list(features_dict.keys())
        feature_values = list(features_dict.values())
        
        for name, value, shap_val in zip(feature_names, feature_values, shap_values):
            factors.append({
                'feature': name,
                'value': value,
                'shap_value': float(shap_val),
                'description': self.feature_descriptions.get(name, name),
            })
        
        return sorted(factors, key=lambda x: abs(x['shap_value']), reverse=True)
    
    def _categorize_risk(self, fraud_probability: float) -> str:
        """Categorize fraud risk level"""
        if fraud_probability >= 0.8:
            return "CRITICAL"
        elif fraud_probability >= 0.6:
            return "HIGH"
        elif fraud_probability >= 0.4:
            return "MEDIUM"
        elif fraud_probability >= 0.2:
            return "LOW"
        else:
            return "MINIMAL"
    
    def _categorize_strength(self, shap_value: float) -> str:
        """Categorize SHAP value strength"""
        if shap_value > 0.3:
            return "VERY STRONG"
        elif shap_value > 0.15:
            return "STRONG"
        elif shap_value > 0.05:
            return "MODERATE"
        else:
            return "WEAK"
    
    def _generate_reasoning(
        self,
        feature_name: str,
        feature_value: Any,
        shap_value: float,
        fraud_probability: float
    ) -> str:
        """Generate human-readable reasoning for a factor"""
        direction = "increases" if shap_value > 0 else "decreases"
        strength = "significantly" if abs(shap_value) > 0.2 else "moderately"
        
        # Nigerian-specific reasoning
        nigerian_reasoning = {
            'pod_phone_failed_deliveries_7d': (
                f"This phone has {feature_value} failed deliveries in the past week, "
                f"which {direction} fraud risk. Multiple failed deliveries often indicate "
                "fraud rings testing delivery addresses."
            ),
            'pod_phone_txn_count_24h': (
                f"This phone placed {feature_value} orders in 24 hours. "
                f"High velocity is typical of fraud rings. This {strength} {direction}s fraud risk."
            ),
            'pod_address_cluster_risk_score': (
                f"The delivery address cluster has a risk score of {feature_value:.2f}. "
                "Multiple phone numbers ordering to the same address is a classic fraud pattern."
            ),
            'pod_amount_exceeds_typical_threshold': (
                f"This {'is' if feature_value == 1 else 'is not'} a high-value order (>₦200k). "
                "Fraudsters typically test addresses with high-value items to maximize loss."
            ),
            'pod_order_at_high_risk_hour': (
                f"This order was placed {'during' if feature_value == 1 else 'outside'} "
                "high-risk hours (10pm-5am). Night orders have higher fraud rates."
            ),
            'pod_phone_is_blacklisted': (
                f"This phone number is {'on' if feature_value == 1 else 'not on'} our fraud blacklist. "
                "Blacklisted numbers have confirmed fraud history."
            ),
        }
        
        # Return Nigerian-specific reasoning if available
        if feature_name in nigerian_reasoning:
            return nigerian_reasoning[feature_name]
        
        # Default generic reasoning
        return (
            f"This factor {strength} {direction}s fraud risk based on historical patterns. "
            f"High fraud probability ({fraud_probability:.1%}) combined with this factor suggests caution."
        )


# Flask API creation function
def create_shap_api(explainer: SHAPExplainer) -> Flask:
    """Create Flask API for SHAP explanations"""
    app = Flask(__name__)
    
    @app.route('/health', methods=['GET'])
    def health():
        return jsonify({'status': 'healthy', 'service': 'shap-explainer'})
    
    @app.route('/api/explain/<case_id>', methods=['GET'])
    def get_explanation(case_id: str):
        """Get SHAP explanation for a case"""
        try:
            # Get case details from database
            # TODO: Implement database lookup
            case = {
                'case_id': case_id,
                # Features would be loaded from database
            }
            
            # Return explanation
            return jsonify(explainer.explain_transaction(case))
        except Exception as e:
            logger.error(f"Error getting explanation: {e}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/explain', methods=['POST'])
    def explain_features():
        """Explain transaction with provided features"""
        try:
            data = request.json
            features = data.get('features', {})
            case_id = data.get('case_id')
            
            explanation = explainer.explain_transaction(features, case_id)
            return jsonify(explanation)
        except Exception as e:
            logger.error(f"Error explaining features: {e}")
            return jsonify({'error': str(e)}), 500
    
    return app


if __name__ == '__main__':
    # Initialize explainer
    explainer = SHAPExplainer()
    
    # Create and run API
    app = create_shap_api(explainer)
    app.run(host='0.0.0.0', port=5002, debug=False)
