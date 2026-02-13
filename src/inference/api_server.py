"""
REST API server for Fraud Detection Inference Service

Exposes HTTP endpoints for:
- Health checks
- Running inference
- Retrieving inference results
- Prometheus metrics endpoint

Cumulative totals are persisted to file to survive restarts and provide real-time tracking.
"""
import os
import json
import logging
import pandas as pd
from flask import Flask, jsonify, request
from datetime import datetime
from main import FraudDetectionInference
from continuous_inference import ContinuousInferenceWorker
import threading
import sys
sys.path.insert(0, '/app')

from utils.prometheus_metrics import (
    inference_predictions_total, inference_prediction_latency,
    inference_errors_total, inference_data_points_total,
    inference_fraud_rate, inference_model_loaded,
    inference_cumulative_frauds, inference_cumulative_total,
    get_metrics_exposition, track_prediction_latency
)
from utils.logging_config import setup_structured_logging

# Configure structured JSON logging
logger = setup_structured_logging('inference-api', logging.INFO)

app = Flask(__name__)

# Global inference instance (initialized on startup)
inference_pipeline = None
latest_results = None
latest_results_timestamp = None
results_history_max = int(os.getenv('INFERENCE_RESULTS_HISTORY_MAX', '10000'))
continuous_worker = None  # Continuous inference worker for real-time processing

# Track cumulative totals for real-time stats - PERSISTED TO FILE
CUMULATIVE_STATS_FILE = '/app/cumulative_stats.json'
cumulative_lock = threading.Lock()

def _load_cumulative_stats():
    """Load cumulative stats from persistent file"""
    try:
        if os.path.exists(CUMULATIVE_STATS_FILE):
            with open(CUMULATIVE_STATS_FILE, 'r') as f:
                data = json.load(f)
                total = int(data.get('total_records', 0))
                fraud = int(data.get('fraud_detections', 0))
                logger.info('Loaded cumulative stats from file: total=%d, fraud=%d', total, fraud)
                return {
                    'total_records': total,
                    'fraud_detections': fraud,
                    'last_updated': data.get('last_updated')
                }
    except Exception as e:
        logger.warning('Failed to load cumulative stats: %s', str(e))
    return {'total_records': 0, 'fraud_detections': 0, 'last_updated': None}

def _save_cumulative_stats(total_records, fraud_detections):
    """Save cumulative stats to persistent file - THREAD SAFE"""
    try:
        with cumulative_lock:
            data = {
                'total_records': int(total_records),
                'fraud_detections': int(fraud_detections),
                'last_updated': datetime.now().isoformat()
            }
            # Write to temp file first, then rename (atomic operation)
            temp_file = CUMULATIVE_STATS_FILE + '.tmp'
            with open(temp_file, 'w') as f:
                json.dump(data, f)
            os.replace(temp_file, CUMULATIVE_STATS_FILE)
            logger.debug('Saved cumulative stats: total=%d, fraud=%d', total_records, fraud_detections)
    except Exception as e:
        logger.error('Failed to save cumulative stats: %s', str(e))

# Initialize cumulative stats from file at module load
_cumulative_stats = _load_cumulative_stats()
cumulative_total_records = _cumulative_stats['total_records']
cumulative_fraud_detections = _cumulative_stats['fraud_detections']
logger.info('Initialized cumulative stats: total=%d, fraud=%d', cumulative_total_records, cumulative_fraud_detections)


def _append_results(results):
    """Append results and update cumulative totals - ALWAYS INCREMENTS, NEVER RESETS"""
    global latest_results, latest_results_timestamp, cumulative_total_records, cumulative_fraud_detections
    
    if not hasattr(results, 'to_dict'):
        return

    # Update cumulative totals - ALWAYS ADD, NEVER RESET
    if hasattr(results, 'columns') and 'fraud_prediction' in results.columns:
        new_count = len(results)
        new_fraud = int(results['fraud_prediction'].sum())
        
        # CRITICAL: Always add to cumulative, never replace
        # This ensures totals keep growing even if latest_results is truncated
        old_total = cumulative_total_records
        old_fraud = cumulative_fraud_detections
        
        cumulative_total_records += new_count
        cumulative_fraud_detections += new_fraud
        
        # Persist to file immediately (thread-safe)
        _save_cumulative_stats(cumulative_total_records, cumulative_fraud_detections)
        
        logger.info('Cumulative updated: total=%d (+%d from %d), fraud=%d (+%d from %d)', 
                   cumulative_total_records, new_count, old_total, 
                   cumulative_fraud_detections, new_fraud, old_fraud)

    # Update latest_results for recent history (separate from cumulative - this can be truncated)
    if latest_results is None or not hasattr(latest_results, 'to_dict'):
        latest_results = results
    else:
        latest_results = pd.concat([latest_results, results], ignore_index=True)
        if len(latest_results) > results_history_max:
            # Truncate latest_results but DON'T affect cumulative
            latest_results = latest_results.tail(results_history_max).reset_index(drop=True)
            logger.debug('Truncated latest_results to %d (cumulative unchanged: %d)', 
                        len(latest_results), cumulative_total_records)

    latest_results_timestamp = datetime.now()


def initialize_inference():
    """Initialize the inference pipeline and start continuous inference worker"""
    global inference_pipeline, cumulative_total_records, cumulative_fraud_detections, continuous_worker
    try:
        inference_pipeline = FraudDetectionInference()
        logger.info('Inference pipeline initialized successfully')
        
        # Reload cumulative stats from file (in case it was updated)
        _cumulative_stats = _load_cumulative_stats()
        cumulative_total_records = _cumulative_stats['total_records']
        cumulative_fraud_detections = _cumulative_stats['fraud_detections']
        
        logger.info('Cumulative stats ready: total=%d, fraud=%d', 
                  cumulative_total_records, cumulative_fraud_detections)
        
        # Start continuous inference worker for real-time processing
        if inference_pipeline.model is not None:
            poll_interval = float(os.getenv('CONTINUOUS_INFERENCE_INTERVAL', '0.2'))  # Default 0.2s for true real-time (5Hz)
            continuous_worker = ContinuousInferenceWorker(inference_pipeline, poll_interval=poll_interval)
            # Pass the _append_results function to the worker
            continuous_worker._append_results_func = _append_results
            continuous_worker.start()
            logger.info('Continuous inference worker started (polling every %ds)', poll_interval)
        else:
            logger.warning('Model not loaded, skipping continuous inference worker startup')
        
        return True
    except Exception as e:
        logger.error('Failed to initialize inference pipeline: %s', str(e))
        return False


@app.route('/', methods=['GET'])
def root():
    """Root endpoint - returns API info"""
    return jsonify({
        'service': 'Fraud Detection Inference API',
        'version': '1.0.0',
        'status': 'running',
        'endpoints': {
            'health': '/health or /inference/health',
            'predict': '/predict or /inference/predict (POST)',
            'predict_from_api': '/predict_from_api or /inference/predict_from_api (POST)',
            'results': '/results or /inference/results (GET)',
            'stats': '/stats or /inference/stats (GET)'
        }
    }), 200


@app.route('/health', methods=['GET'])
@app.route('/inference/health', methods=['GET'])
def health_check():
    """Health check endpoint with model status"""
    try:
        model_loaded = inference_pipeline is not None and inference_pipeline.model is not None
        inference_model_loaded.set(1 if model_loaded else 0)
        
        status = 'healthy' if model_loaded else 'degraded'
        return jsonify({
            'status': status,
            'model_loaded': model_loaded,
            'model_version': getattr(inference_pipeline, 'model_version', None),
            'timestamp': datetime.now().isoformat()
        }), 200
    except Exception as e:
        logger.error('Health check failed: %s', str(e), exc_info=True)
        return jsonify({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 503


@app.route('/inference/run', methods=['POST'])
@app.route('/run', methods=['POST'])
def run_inference():
    """Run inference on transactions"""
    global latest_results, latest_results_timestamp, cumulative_total_records, cumulative_fraud_detections
    
    if inference_pipeline is None:
        return jsonify({
            'error': 'Inference pipeline not initialized'
        }), 500
    
    if inference_pipeline.model is None:
        return jsonify({
            'error': 'Model not loaded. Please train the model first.',
            'status': 'model_unavailable'
        }), 503
    
    try:
        # Get params from request body or use defaults
        max_records = 10000
        explain = False
        top_k = 5
        if request.is_json and request.json:
            max_records = request.json.get('max_records', 10000)
            explain = bool(request.json.get('explain', False))
            top_k = int(request.json.get('top_k', 5))
        
        logger.info('Running inference with max_records=%d (current cumulative: %d)', 
                   max_records, cumulative_total_records)
        
        # Run inference
        results = inference_pipeline.run_inference(max_records=max_records, explain=explain, top_k=top_k)
        
        # Store latest results
        if isinstance(results, dict) and results.get('status') == 'model_unavailable':
            return jsonify(results), 503
        
        # This will update cumulative totals and persist to file
        _append_results(results)
        
        # Convert DataFrame to JSON-serializable format
        if hasattr(results, 'to_dict'):
            results_dict = results.to_dict('records')
        else:
            results_dict = results
        
        # Calculate summary statistics for this batch
        if hasattr(results, 'columns') and 'fraud_prediction' in results.columns:
            fraud_count = int(results['fraud_prediction'].sum())
        elif isinstance(results, dict) and 'fraud_prediction' in results:
            fraud_count = int(results.get('fraud_prediction', 0))
        else:
            fraud_count = 0
        total_count = len(results) if hasattr(results, '__len__') else 0
        fraud_rate = 100 * fraud_count / total_count if total_count > 0 else 0
        
        logger.info('Inference complete: batch=%d, fraud=%d, cumulative_total=%d', 
                   total_count, fraud_count, cumulative_total_records)
        
        return jsonify({
            'status': 'success',
            'total_records': total_count,  # This batch
            'cumulative_total_records': cumulative_total_records,  # Total ever processed
            'fraud_detections': fraud_count,  # This batch
            'cumulative_fraud_detections': cumulative_fraud_detections,  # Total ever
            'fraud_rate': round(fraud_rate, 2),
            'timestamp': latest_results_timestamp.isoformat(),
            'results': results_dict[:100] if len(results_dict) > 100 else results_dict,
            'total_results': len(results_dict)
        }), 200
        
    except Exception as e:
        logger.error('Inference failed: %s', str(e), exc_info=True)
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500


@app.route('/inference/predict', methods=['POST'])
@app.route('/predict', methods=['POST'])
def predict_realtime():
    """Run real-time inference on provided payload"""
    global latest_results, latest_results_timestamp, cumulative_total_records, cumulative_fraud_detections

    if inference_pipeline is None:
        return jsonify({
            'error': 'Inference pipeline not initialized'
        }), 500

    if inference_pipeline.model is None:
        return jsonify({
            'error': 'Model not loaded. Please train the model first.',
            'status': 'model_unavailable'
        }), 503

    if not request.is_json:
        return jsonify({
            'error': 'Request must be JSON',
            'status': 'invalid_request'
        }), 400

    try:
        payload = request.get_json()
        explain = bool(payload.get('explain', False)) if isinstance(payload, dict) else False
        top_k = int(payload.get('top_k', 5)) if isinstance(payload, dict) else 5
        start_time = datetime.now()
        results = inference_pipeline.predict_from_payload(payload, explain=explain, top_k=top_k)

        if isinstance(results, dict) and results.get('status') == 'model_unavailable':
            return jsonify(results), 503

        # Update cumulative totals
        _append_results(results)

        # Convert DataFrame to JSON-serializable format
        if hasattr(results, 'to_dict'):
            results_dict = results.to_dict('records')
        else:
            results_dict = results

        fraud_count = 0
        if hasattr(results, 'columns') and 'fraud_prediction' in results.columns:
            fraud_count = int(results['fraud_prediction'].sum())
        total_count = len(results_dict) if hasattr(results_dict, '__len__') else 0
        fraud_rate = 100 * fraud_count / total_count if total_count > 0 else 0
        latency_ms = int((datetime.now() - start_time).total_seconds() * 1000)

        return jsonify({
            'status': 'success',
            'total_records': total_count,
            'cumulative_total_records': cumulative_total_records,
            'fraud_detections': fraud_count,
            'cumulative_fraud_detections': cumulative_fraud_detections,
            'fraud_rate': round(fraud_rate, 2),
            'latency_ms': latency_ms,
            'timestamp': latest_results_timestamp.isoformat() if latest_results_timestamp else None,
            'results': results_dict
        }), 200

    except Exception as e:
        logger.error('Realtime inference failed: %s', str(e), exc_info=True)
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500


@app.route('/inference/predict_from_api', methods=['POST'])
@app.route('/predict_from_api', methods=['POST'])
def predict_from_api():
    """Run real-time inference by pulling a small batch from the Fraud API."""
    global latest_results, latest_results_timestamp, cumulative_total_records, cumulative_fraud_detections

    if inference_pipeline is None:
        return jsonify({
            'error': 'Inference pipeline not initialized'
        }), 500

    if inference_pipeline.model is None:
        return jsonify({
            'error': 'Model not loaded. Please train the model first.',
            'status': 'model_unavailable'
        }), 503

    try:
        max_records = 1
        explain = False
        top_k = 5
        if request.is_json and request.json:
            max_records = int(request.json.get('max_records', 1))
            explain = bool(request.json.get('explain', False))
            top_k = int(request.json.get('top_k', 5))

        start_time = datetime.now()
        results = inference_pipeline.run_inference(max_records=max_records, explain=explain, top_k=top_k)

        if isinstance(results, dict) and results.get('status') == 'model_unavailable':
            return jsonify(results), 503

        # Update cumulative totals
        _append_results(results)

        if hasattr(results, 'to_dict'):
            results_dict = results.to_dict('records')
        else:
            results_dict = results

        fraud_count = 0
        if hasattr(results, 'columns') and 'fraud_prediction' in results.columns:
            fraud_count = int(results['fraud_prediction'].sum())
        total_count = len(results_dict) if hasattr(results_dict, '__len__') else 0
        fraud_rate = 100 * fraud_count / total_count if total_count > 0 else 0
        latency_ms = int((datetime.now() - start_time).total_seconds() * 1000)

        return jsonify({
            'status': 'success',
            'total_records': total_count,
            'cumulative_total_records': cumulative_total_records,
            'fraud_detections': fraud_count,
            'cumulative_fraud_detections': cumulative_fraud_detections,
            'fraud_rate': round(fraud_rate, 2),
            'latency_ms': latency_ms,
            'timestamp': latest_results_timestamp.isoformat() if latest_results_timestamp else None,
            'results': results_dict
        }), 200

    except Exception as e:
        logger.error('Realtime inference (from API) failed: %s', str(e), exc_info=True)
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500


@app.route('/inference/results', methods=['GET'])
@app.route('/results', methods=['GET'])
def get_results():
    """Get latest inference results"""
    if latest_results is None:
        return jsonify({
            'error': 'No inference results available. Run inference first.',
            'status': 'no_results'
        }), 404
    
    try:
        # Convert DataFrame to JSON-serializable format
        if hasattr(latest_results, 'to_dict'):
            results_dict = latest_results.to_dict('records')
        else:
            results_dict = latest_results
        
        # Get pagination parameters
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 100))
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        
        paginated_results = results_dict[start_idx:end_idx]
        
        return jsonify({
            'status': 'success',
            'timestamp': latest_results_timestamp.isoformat() if latest_results_timestamp else None,
            'total_records': len(results_dict),  # Current results in memory
            'cumulative_total_records': cumulative_total_records,  # Total ever processed
            'page': page,
            'per_page': per_page,
            'total_pages': (len(results_dict) + per_page - 1) // per_page,
            'results': paginated_results
        }), 200
        
    except Exception as e:
        logger.error('Error retrieving results: %s', str(e))
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500


@app.route('/inference/stats', methods=['GET'])
@app.route('/stats', methods=['GET'])
def get_stats():
    """Get inference statistics - ALWAYS returns cumulative totals for real-time tracking"""
    global cumulative_total_records, cumulative_fraud_detections
    
    try:
        # CRITICAL: Always reload from file to ensure we have latest persisted value
        # This ensures consistency even if multiple processes or restarts occurred
        _cumulative_stats = _load_cumulative_stats()
        total_count = _cumulative_stats['total_records']
        fraud_count = _cumulative_stats['fraud_detections']
        
        # Update global variables
        cumulative_total_records = total_count
        cumulative_fraud_detections = fraud_count
        
        # Update Prometheus metrics
        inference_cumulative_total.set(total_count)
        inference_cumulative_frauds.set(fraud_count)
        fraud_rate = float(fraud_count) / float(total_count) if total_count > 0 else 0.0
        inference_fraud_rate.set(fraud_rate)
        
        # Calculate averages from latest_results if available (for recent performance metrics)
        avg_probability = 0.0
        avg_confidence = 0.0
        if latest_results is not None and hasattr(latest_results, 'to_dict') and len(latest_results) > 0:
            try:
                avg_probability = float(latest_results['fraud_probability'].mean())
                avg_confidence = float(latest_results['confidence'].mean())
            except:
                pass
        
        # Calculate fraud rate from cumulative totals
        fraud_rate_pct = round(100 * fraud_count / total_count if total_count > 0 else 0, 2)
        
        logger.info('Stats requested: cumulative_total=%d, cumulative_fraud=%d, rate=%.2f%%', 
                    total_count, fraud_count, fraud_rate_pct)
        
        return jsonify({
            'status': 'success',
            'timestamp': latest_results_timestamp.isoformat() if latest_results_timestamp else datetime.now().isoformat(),
            'total_records': total_count,  # ALWAYS cumulative, never limited to 1000
            'fraud_detections': fraud_count,  # ALWAYS cumulative
            'fraud_rate': fraud_rate_pct,
            'avg_fraud_probability': round(avg_probability, 4),
            'avg_confidence': round(avg_confidence, 4),
            'model_version': getattr(inference_pipeline, 'model_version', None),
            'model_source': getattr(inference_pipeline, 'model_source', None)
        }), 200
        
    except Exception as e:
        inference_errors_total.labels(error_type='stats_retrieval').inc()
        logger.error('Error retrieving stats: %s', str(e), exc_info=True)
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500


@app.route('/metrics', methods=['GET'])
def get_metrics():
    """Prometheus metrics endpoint - exposes all collected metrics"""
    try:
        return get_metrics_exposition(), 200, {'Content-Type': 'text/plain; version=0.0.4'}
    except Exception as e:
        logger.error('Error generating metrics: %s', str(e), exc_info=True)
        return jsonify({'error': str(e)}), 500





if __name__ == '__main__':
    # Initialize inference pipeline
    if not initialize_inference():
        logger.error('Failed to initialize inference pipeline. Exiting.')
        exit(1)
    
    # Get port from environment variable (handle Kubernetes service URLs)
    port_env = os.getenv('INFERENCE_PORT', '8000')
    # Extract port number if it's a URL like "tcp://10.0.184.235:8000"
    if ':' in port_env and not port_env.startswith('tcp://'):
        port = int(port_env.split(':')[-1]) if ':' in port_env else int(port_env)
    elif port_env.startswith('tcp://'):
        # Extract port from tcp://host:port format
        port = int(port_env.split(':')[-1])
    else:
        port = int(port_env)
    debug = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    
    logger.info('Starting inference API server on port %d', port)
    logger.info('Cumulative stats file: %s', CUMULATIVE_STATS_FILE)
    logger.info('Initial cumulative: total=%d, fraud=%d', cumulative_total_records, cumulative_fraud_detections)
    app.run(host='0.0.0.0', port=port, debug=debug)
