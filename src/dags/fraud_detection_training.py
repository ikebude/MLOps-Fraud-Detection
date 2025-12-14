"""
Lightweight shim module that imports FraudDetectionTraining from plugins.

This keeps the dags folder clean and ensures Airflow doesn't block on heavy imports
during DAG parsing. The actual implementation is in src/plugins/fraud_detection_training.py.
"""

from fraud_detection_training import FraudDetectionTraining

__all__ = ['FraudDetectionTraining']
