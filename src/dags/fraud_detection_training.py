"""
Lightweight shim module that imports FraudDetectionTraining from plugins.

This keeps the dags folder clean and ensures Airflow doesn't block on heavy imports
during DAG parsing. The actual implementation is in src/plugins/fraud_detection_training.py.
"""

import sys
import os

# Add plugins directory to path if not already there
plugins_path = '/opt/airflow/plugins'
if plugins_path not in sys.path:
    sys.path.insert(0, plugins_path)

# Import from plugins folder
from fraud_detection_training import FraudDetectionTraining

__all__ = ['FraudDetectionTraining']





