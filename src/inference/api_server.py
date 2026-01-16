"""
REST API server for Fraud Detection Inference Service

Exposes HTTP endpoints for:
- Health checks
- Running inference
- Retrieving inference results
"""

import os
import json
import logging
import pandas as pd
from flask import Flask, jsonify, request
from datetime import datetime
from main import FraudDetectionInference

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Global inference instance (initialized on startup)
inference_pipeline = None
latest_results = None
latest_results_timestamp = None
results_history_max = int(os.getenv('INFERENCE_RESULTS_HISTORY_MAX', '1000'))


def _append_results(results):
    global latest_results, latest_results_timestamp
    if not hasattr(results, 'to_dict'):
        return

    if latest_results is None or not hasattr(latest_results, 'to_dict'):
        latest_results = results
    else:
        latest_results = pd.concat([latest_results, results], ignore_index=True)
        if len(latest_results) > results_history_max:
            latest_results = latest_results.tail(results_history_max).reset_index(drop=True)

    latest_results_timestamp = datetime.now()


def initialize_inference():
    """Initialize the inference pipeline"""
    global inference_pipeline
    try:
        inference_pipeline = FraudDetectionInference(config_path='/app/config.yaml')
        logger.info('Inference pipeline initialized successfully')
        return True
    except Exception as e:
        logger.error('Failed to initialize inference pipeline: %s', str(e))
        return False


@app.route('/health', methods=['GET'])
@app.route('/inference/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    try:
        model_loaded = inference_pipeline.model is not None if inference_pipeline else False
        return jsonify({
            'status': 'healthy',
            'model_loaded': model_loaded,
            'model_version': getattr(inference_pipeline, 'model_version', None),
            'timestamp': datetime.now().isoformat()
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 503


@app.route('/inference/run', methods=['POST'])
@app.route('/run', methods=['POST'])
def run_inference():
    """Run inference on transactions"""
    global latest_results, latest_results_timestamp
    
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
        
        logger.info('Running inference with max_records=%d', max_records)
        
        # Run inference
        results = inference_pipeline.run_inference(max_records=max_records, explain=explain, top_k=top_k)
        
        # Store latest results
        if isinstance(results, dict) and results.get('status') == 'model_unavailable':
            return jsonify(results), 503
        
        _append_results(results)
        
        # Convert DataFrame to JSON-serializable format
        if hasattr(results, 'to_dict'):
            results_dict = results.to_dict('records')
        else:
            results_dict = results
        
        # Calculate summary statistics
        if hasattr(results, 'columns') and 'fraud_prediction' in results.columns:
            fraud_count = int(results['fraud_prediction'].sum())
        elif isinstance(results, dict) and 'fraud_prediction' in results:
            fraud_count = int(results.get('fraud_prediction', 0))
        else:
            fraud_count = 0
        total_count = len(results) if hasattr(results, '__len__') else 0
        fraud_rate = 100 * fraud_count / total_count if total_count > 0 else 0
        
        return jsonify({
            'status': 'success',
            'total_records': total_count,
            'fraud_detections': fraud_count,
            'fraud_rate': round(fraud_rate, 2),
            'timestamp': latest_results_timestamp.isoformat(),
            'results': results_dict[:100] if len(results_dict) > 100 else results_dict,  # Limit to first 100 for response
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
    global latest_results, latest_results_timestamp

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
            'fraud_detections': fraud_count,
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
    global latest_results, latest_results_timestamp

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
            'fraud_detections': fraud_count,
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
            'total_records': len(results_dict),
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
    """Get inference statistics"""
    if latest_results is None:
        return jsonify({
            'error': 'No inference results available',
            'status': 'no_results'
        }), 404
    
    try:
        if hasattr(latest_results, 'to_dict'):
            fraud_count = int(latest_results['fraud_prediction'].sum())
            total_count = len(latest_results)
            avg_probability = float(latest_results['fraud_probability'].mean())
            avg_confidence = float(latest_results['confidence'].mean())
        else:
            fraud_count = 0
            total_count = 0
            avg_probability = 0.0
            avg_confidence = 0.0
        
        return jsonify({
            'status': 'success',
            'timestamp': latest_results_timestamp.isoformat() if latest_results_timestamp else None,
            'total_records': total_count,
            'fraud_detections': fraud_count,
            'fraud_rate': round(100 * fraud_count / total_count if total_count > 0 else 0, 2),
            'avg_fraud_probability': round(avg_probability, 4),
            'avg_confidence': round(avg_confidence, 4),
            'model_version': getattr(inference_pipeline, 'model_version', None),
            'model_source': getattr(inference_pipeline, 'model_source', None)
        }), 200
        
    except Exception as e:
        logger.error('Error retrieving stats: %s', str(e))
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500


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
    app.run(host='0.0.0.0', port=port, debug=debug)
