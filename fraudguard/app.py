"""
FraudGuard Dashboard – Web UI for fraud detection metrics.

Uses Inference API for stats/results/run, and optionally MLflow, Airflow, MinIO, Flower.
"""
import os
import logging
from datetime import datetime
from flask import Flask, render_template, jsonify, request, Response
from flask import stream_with_context
import json
import time

import requests

app = Flask(__name__)
app.config["JSON_SORT_KEYS"] = False

INFERENCE_URL = os.getenv("INFERENCE_SERVICE_URL", "http://inference:8000").rstrip("/")
MLFLOW_URI = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow-server:5500").rstrip("/")
AIRFLOW_URL = os.getenv("AIRFLOW_WEBSERVER_URL", "http://airflow-webserver:8080").rstrip("/")
MINIO_URL = os.getenv("MINIO_URL", "http://minio:9000").rstrip("/")
FLOWER_URL = os.getenv("FLOWER_URL", "http://flower:5555").rstrip("/")
REQUEST_TIMEOUT = int(os.getenv("FRAUDGUARD_REQUEST_TIMEOUT", "10"))

# Structured JSON logging
try:
    from utils.logging_config import setup_structured_logging
    logger = setup_structured_logging('fraudguard', logging.INFO)
except Exception:
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)


def _get(url: str, default=None):
    try:
        r = requests.get(url, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.warning("GET %s failed: %s", url, e)
        return default


def _get_raw(url: str):
    try:
        r = requests.get(url, timeout=REQUEST_TIMEOUT)
        return r.status_code == 200
    except Exception:
        return False


def _post(url: str, json=None, default=None):
    try:
        r = requests.post(url, json=json or {}, timeout=60)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.warning("POST %s failed: %s", url, e)
        return default


def _map_result_to_txn(r):
    """Map inference result record to dashboard transaction format."""
    # Handle timestamp: prefer prediction_timestamp (from DB), fallback to timestamp (from inference)
    ts = r.get("prediction_timestamp") or r.get("timestamp") or r.get("created_at")
    if hasattr(ts, "isoformat"):
        try:
            ts = ts.isoformat()
        except Exception:
            ts = str(ts)
    else:
        ts = str(ts) if ts is not None else "—"
    
    # Extract fraud probability (handle both float and string)
    prob_raw = r.get("fraud_probability", 0) or 0
    prob = float(prob_raw) if prob_raw else 0.0
    prob = max(0.0, min(1.0, prob))  # Clamp to [0, 1]
    
    # Extract fraud prediction (0=legitimate, 1=fraud)
    pred_raw = r.get("fraud_prediction", 0) or r.get("fraud_label")
    if isinstance(pred_raw, str):
        pred = 1 if pred_raw.upper() == "FRAUD" else 0
    else:
        pred = int(pred_raw) if pred_raw else 0
    
    # Determine status based on prediction and probability
    if pred == 1:
        status = "Declined" if prob >= 0.8 else "Flagged"
    else:
        status = "Approved"
    
    # Extract transaction ID (required for dashboard)
    transaction_id = str(r.get("transaction_id") or r.get("id") or r.get("order_id") or "-")
    
    # Extract user ID (displayed as merchant/user in dashboard)
    user_id = str(r.get("user_id") or r.get("full_name") or "—")
    
    # Extract amount and currency
    amount = float(r.get("amount", 0) or 0)
    currency = str(r.get('currency') or r.get('currency_code') or r.get('amount_currency') or 'NGN')
    
    return {
        "id": transaction_id,
        "time": ts,
        "merchant": user_id,
        "amount": amount,
        "currency": currency,
        "risk_score": min(100, int(round(100 * prob))),
        "status": status,
    }


@app.route("/")
def index():
    """Redirect to enterprise dashboard"""
    return render_template("enterprise_dashboard.html")


@app.route("/dashboard")
def dashboard():
    """Legacy dashboard route - redirects to enterprise dashboard"""
    return render_template("enterprise_dashboard.html")


@app.route("/enterprise")
def enterprise_dashboard():
    """Advanced enterprise-grade dashboard for clients"""
    return render_template("enterprise_dashboard.html", page="overview")


@app.route("/transactions")
def transactions():
    return render_template("transactions.html", page="transactions")


@app.route("/alerts")
def alerts():
    return render_template("alerts.html", page="alerts")


@app.route("/system_health")
def system_health():
    return render_template("system_health.html", page="system_health")


@app.route("/settings")
def settings():
    return render_template("settings.html", page="settings")


@app.route("/api/health")
def api_health():
    ok = False
    try:
        d = _get(f"{INFERENCE_URL}/health", {})
        ok = d.get("status") == "healthy"
    except Exception:
        pass
    return jsonify({
        "status": "healthy",
        "inference_reachable": ok,
        "inference_url": INFERENCE_URL,
    })


@app.route("/api/model_metrics")
def api_model_metrics():
    """Return latest model metrics from MLflow (precision, recall, f1, auc, etc.)"""
    try:
        # Import mlflow only when needed to avoid startup failures when mlflow not installed
        import mlflow
        from mlflow.tracking import MlflowClient
        
        logger.info(f"Fetching model metrics from MLflow at {MLFLOW_URI}")
        client = MlflowClient(tracking_uri=MLFLOW_URI)
        
        # Try to get latest registered model versions for default name
        registered_name = os.getenv('MLFLOW_REGISTERED_MODEL', 'fraud_detection_model')
        logger.info(f"Looking for registered model: {registered_name}")
        
        versions = client.get_latest_versions(registered_name, stages=["None", "Staging", "Production"])
        logger.info(f"Found {len(versions)} versions")
        
        if not versions:
            logger.warning(f"No registered model found for {registered_name}")
            return jsonify({"status": "no_model", "message": "No registered model found"})
        
        latest = versions[0]
        logger.info(f"Using latest version: {latest.version}, run_id: {latest.run_id}")
        
        # Attempt to pull run metrics
        run = client.get_run(latest.run_id)
        if not run:
            logger.error(f"Could not find run {latest.run_id}")
            return jsonify({"status": "no_run", "message": f"Run {latest.run_id} not found"})
        
        metrics = {}
        if run.data and hasattr(run.data, 'metrics') and run.data.metrics:
            logger.info(f"Found {len(run.data.metrics)} metrics in run")
            for k, v in run.data.metrics.items():
                try:
                    metrics[k] = float(v)
                    logger.debug(f"Metric {k}: {v}")
                except Exception as metric_error:
                    logger.warning(f"Failed to convert metric {k}={v} to float: {metric_error}")
                    metrics[k] = str(v)
        else:
            logger.warning(f"No metrics found in run {latest.run_id}")
        
        # Build response
        response = {
            "status": "success",
            "model_name": registered_name,
            "model_version": str(latest.version),
            "run_id": latest.run_id,
            "metrics": metrics,
        }
        
        # Add key metrics at top level for easier access
        key_metrics = ['precision', 'recall', 'f1', 'auc_pr', 'threshold']
        for metric in key_metrics:
            if metric in metrics:
                response[metric] = metrics[metric]
        
        logger.info(f"Returning model metrics: precision={metrics.get('precision', 'N/A')}, "
                   f"recall={metrics.get('recall', 'N/A')}, f1={metrics.get('f1', 'N/A')}")
        
        return jsonify(response)
        
    except ImportError:
        logger.warning('MLflow not installed in FraudGuard environment; skipping metrics fetch')
        return jsonify({"status": "unavailable", "message": "MLflow not available in this environment"}), 503
    except Exception as e:
        logger.error('Failed to fetch model metrics from MLflow: %s', e, exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/data")
def api_data():
    """Aggregated metrics, model_health, and transactions for the dashboard."""
    metrics = {
        "total_transactions": 0,
        "fraud_detections": 0,
        "fraud_rate": 0.0,
        "approval_rate": 100.0,
        "active_alerts": 0,
        "model_loaded": False,
        "model_version": None,
        "model_source": None,
        "timestamp": None,
        "inference_status": "unknown",
        "mlflow_status": "unknown",
        "airflow_status": "unknown",
        "minio_status": "unknown",
        "flower_status": "unknown",
    }
    transactions = []
    model_health = {
        "name": "fraud_detection_model",
        "version": "—",
        "accuracy": "—",
        "drift_status": "Normal",
        "last_retrained": "—",
    }

    stats = _get(f"{INFERENCE_URL}/inference/stats")
    if isinstance(stats, dict) and stats.get("status") == "success":
        metrics["total_transactions"] = int(stats.get("total_records", 0))
        metrics["fraud_detections"] = int(stats.get("fraud_detections", 0))
        metrics["fraud_rate"] = float(stats.get("fraud_rate", 0))
        metrics["approval_rate"] = round(100 - metrics["fraud_rate"], 1)
        metrics["active_alerts"] = metrics["fraud_detections"]
        metrics["model_loaded"] = True
        metrics["model_version"] = stats.get("model_version") or "—"
        metrics["model_source"] = stats.get("model_source") or "—"
        metrics["timestamp"] = stats.get("timestamp")
        metrics["inference_status"] = "ok"
        model_health["version"] = str(metrics["model_version"])
        if metrics["timestamp"]:
            model_health["last_retrained"] = metrics["timestamp"][:10]
    else:
        metrics["inference_status"] = "unreachable"

    # Try to fetch model metrics from MLflow and include precision/recall/f1/auc when available
    try:
        import mlflow
        from mlflow.tracking import MlflowClient
        logger.info(f"Connecting to MLflow at {MLFLOW_URI}")
        client = MlflowClient(tracking_uri=MLFLOW_URI)
        registered_name = os.getenv('MLFLOW_REGISTERED_MODEL', 'fraud_detection_model')
        
        # Get latest model versions
        versions = client.get_latest_versions(registered_name, stages=["None", "Staging", "Production"])
        logger.info(f"Found {len(versions)} model versions for {registered_name}")
        
        if versions:
            latest = versions[0]
            logger.info(f"Using model version {latest.version} with run_id {latest.run_id}")
            
            # Get run and metrics
            run = client.get_run(latest.run_id)
            if run and run.data and hasattr(run.data, 'metrics'):
                logger.info(f"Found {len(run.data.metrics)} metrics in run")
                
                # Extract and log key metrics
                for k, v in run.data.metrics.items():
                    try:
                        metric_value = float(v)
                        model_health[k] = metric_value
                        logger.info(f"Loaded metric {k}: {metric_value}")
                    except Exception as metric_error:
                        logger.warning(f"Failed to convert metric {k}={v} to float: {metric_error}")
                        model_health[k] = v
                
                model_health['version'] = str(latest.version)
                if 'run_id' not in model_health:
                    model_health['run_id'] = latest.run_id
                if 'last_retrained' not in model_health and run.info and run.info.start_time:
                    try:
                        model_health['last_retrained'] = datetime.fromtimestamp(run.info.start_time/1000).isoformat()[:10]
                    except Exception as time_error:
                        logger.warning(f"Failed to convert timestamp: {time_error}")
                
                logger.info(f"Model health updated: {model_health}")
            else:
                logger.warning(f"Run {latest.run_id} found but no metrics available")
        else:
            logger.warning(f"No model versions found for {registered_name}")
            
    except ImportError as import_error:
        logger.warning(f'MLflow not installed in FraudGuard environment: {import_error}')
    except Exception as mlflow_error:
        logger.error(f'Failed to fetch model metrics from MLflow: {mlflow_error}', exc_info=True)
        # Keep existing model_health values if MLflow fails

    metrics["mlflow_status"] = "ok" if _get_raw(f"{MLFLOW_URI}/health") else "unreachable"
    metrics["airflow_status"] = "ok" if _get_raw(f"{AIRFLOW_URL}/health") else "unreachable"
    metrics["minio_status"] = "ok" if _get_raw(f"{MINIO_URL}/minio/health/live") else "unreachable"
    metrics["flower_status"] = "ok" if _get_raw(f"{FLOWER_URL}/") else "unreachable"

    results = _get(f"{INFERENCE_URL}/inference/results")
    if isinstance(results, dict) and results.get("status") == "success":
        for r in (results.get("results") or [])[:200]:
            transactions.append(_map_result_to_txn(r))

    return jsonify({
        "metrics": metrics,
        "model_health": model_health,
        "transactions": transactions,
        "status": "success",
    })


@app.route("/api/inference/run", methods=["POST"])
def api_inference_run():
    payload = request.get_json(force=True, silent=True) or {}
    max_records = int(payload.get("max_records", 1000))
    data = _post(f"{INFERENCE_URL}/inference/run", json={"max_records": max_records})
    if data is None:
        return jsonify({"status": "error", "message": "Inference service unreachable"}), 502
    return jsonify(data)


@app.route("/api/inference/results")
def api_inference_results():
    data = _get(f"{INFERENCE_URL}/inference/results")
    if data is None:
        return jsonify({"status": "error", "message": "Inference service unreachable"}), 502
    return jsonify(data)


@app.route("/api/inference/stats")
def api_inference_stats():
    data = _get(f"{INFERENCE_URL}/inference/stats")
    if data is None:
        return jsonify({"status": "error", "message": "Inference service unreachable"}), 502
    return jsonify(data)


@app.route("/api/inference/details")
def api_inference_details():
    """Combined inference details: stats + recent results for live UI widgets."""
    stats = _get(f"{INFERENCE_URL}/inference/stats") or {}
    results = _get(f"{INFERENCE_URL}/inference/results") or {}
    return jsonify({
        "status": "success",
        "stats": stats,
        "results": results
    })


@app.route('/stream/transactions')
def stream_transactions():
    """Server-Sent Events stream that forwards recent inference results for live UI updates."""
    @stream_with_context
    def event_stream():
        last_ts = None
        while True:
            try:
                data = _get(f"{INFERENCE_URL}/inference/results") or {}
                payload = {}
                if isinstance(data, dict):
                    payload['timestamp'] = data.get('timestamp')
                    payload['results'] = data.get('results') or []
                else:
                    payload['results'] = []
                    payload['timestamp'] = None
                # Always send current payload (frontend will diff if needed)
                ev = 'event: transactions\n' + 'data: ' + json.dumps(payload) + '\n\n'
                yield ev
            except Exception:
                yield 'event: transactions\n' + 'data: ' + json.dumps({'results': [], 'timestamp': None}) + '\n\n'
            time.sleep(2)
    return Response(event_stream(), mimetype='text/event-stream')


if __name__ == "__main__":
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    port = int(os.getenv("FLASK_PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=debug)
