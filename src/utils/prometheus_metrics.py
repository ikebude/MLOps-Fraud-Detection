"""
Prometheus Metrics Utilities

Centralized metrics collection for fraud detection services.
Provides pre-configured counters, histograms, and gauges.
"""

from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry, generate_latest
from prometheus_client.core import REGISTRY
import time
from functools import wraps
from typing import Callable, Any


# Initialize collectors with descriptive help text
inference_predictions_total = Counter(
    'fraud_detection_predictions_total',
    'Total number of fraud detection predictions',
    ['prediction_type'],  # 'fraud' or 'legitimate'
    registry=REGISTRY
)

inference_prediction_latency = Histogram(
    'fraud_detection_prediction_latency_seconds',
    'Time taken to generate fraud detection predictions',
    buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0),
    registry=REGISTRY
)

inference_errors_total = Counter(
    'fraud_detection_inference_errors_total',
    'Total number of inference errors',
    ['error_type'],
    registry=REGISTRY
)

inference_data_points_total = Counter(
    'fraud_detection_data_points_processed_total',
    'Total number of transactions processed for inference',
    registry=REGISTRY
)

inference_fraud_rate = Gauge(
    'fraud_detection_fraud_rate',
    'Current fraud detection rate (fraud_count / total_count)',
    registry=REGISTRY
)

inference_model_loaded = Gauge(
    'fraud_detection_model_loaded',
    'Whether the fraud detection model is loaded (1=yes, 0=no)',
    registry=REGISTRY
)

inference_cumulative_frauds = Gauge(
    'fraud_detection_cumulative_fraud_count',
    'Cumulative count of fraud detections',
    registry=REGISTRY
)

inference_cumulative_total = Gauge(
    'fraud_detection_cumulative_total_count',
    'Cumulative count of total predictions',
    registry=REGISTRY
)

# Training metrics
training_accuracy = Gauge(
    'fraud_detection_training_accuracy',
    'Model accuracy from latest training',
    registry=REGISTRY
)

training_precision = Gauge(
    'fraud_detection_training_precision',
    'Model precision from latest training',
    registry=REGISTRY
)

training_recall = Gauge(
    'fraud_detection_training_recall',
    'Model recall from latest training',
    registry=REGISTRY
)

training_f1_score = Gauge(
    'fraud_detection_training_f1_score',
    'Model F1 score from latest training',
    registry=REGISTRY
)

training_roc_auc = Gauge(
    'fraud_detection_training_roc_auc',
    'Model ROC AUC from latest training',
    registry=REGISTRY
)

training_duration_seconds = Histogram(
    'fraud_detection_training_duration_seconds',
    'Time taken for training pipeline',
    buckets=(60, 300, 600, 1200, 3600),
    registry=REGISTRY
)

training_feature_engineering_duration = Histogram(
    'fraud_detection_feature_engineering_duration_seconds',
    'Time taken for feature engineering',
    buckets=(10, 30, 60, 120, 300),
    registry=REGISTRY
)

training_model_training_duration = Histogram(
    'fraud_detection_model_training_duration_seconds',
    'Time taken for model training',
    buckets=(60, 300, 600, 1200, 3600),
    registry=REGISTRY
)

training_errors_total = Counter(
    'fraud_detection_training_errors_total',
    'Total number of training errors',
    ['error_type'],
    registry=REGISTRY
)

training_runs_total = Counter(
    'fraud_detection_training_runs_total',
    'Total number of training runs',
    ['status'],  # 'success' or 'failure'
    registry=REGISTRY
)


# API/Dashboard metrics
dashboard_request_duration = Histogram(
    'fraud_detection_dashboard_request_duration_seconds',
    'Duration of dashboard API requests',
    ['endpoint'],
    buckets=(0.1, 0.5, 1.0, 2.5, 5.0),
    registry=REGISTRY
)

dashboard_request_errors = Counter(
    'fraud_detection_dashboard_request_errors_total',
    'Total dashboard API request errors',
    ['endpoint', 'status_code'],
    registry=REGISTRY
)


def track_prediction_latency(func: Callable) -> Callable:
    """
    Decorator to track prediction latency.
    
    Usage:
        @track_prediction_latency
        def generate_predictions(data):
            ...
    """
    @wraps(func)
    def wrapper(*args, **kwargs) -> Any:
        with inference_prediction_latency.time():
            return func(*args, **kwargs)
    return wrapper


def track_request_duration(endpoint: str) -> Callable:
    """
    Decorator to track request duration for dashboard endpoints.
    
    Usage:
        @track_request_duration('/inference/results')
        def get_results():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            with dashboard_request_duration.labels(endpoint=endpoint).time():
                return func(*args, **kwargs)
        return wrapper
    return decorator


def get_metrics_exposition() -> str:
    """
    Get all metrics in Prometheus text format.
    
    Returns:
        Prometheus metrics in text format
    """
    return generate_latest(REGISTRY).decode('utf-8')
