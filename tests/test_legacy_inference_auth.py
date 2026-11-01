"""API-key and error-body tests for the legacy Flask inference server (src/inference/api_server.py).

The server imports the batch pipeline, the streaming worker and Prometheus/JSON-logging helpers at
module level. Those are replaced with stubs here, so the tests check only the HTTP layer and need
neither a model nor a database.
"""
import importlib.util
import logging
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SERVER_PATH = REPO_ROOT / "src" / "inference" / "api_server.py"


class _Metric:
    def __getattr__(self, name):
        return lambda *a, **k: self


def _stub_modules(monkeypatch):
    main = types.ModuleType("main")
    main.FraudDetectionInference = object
    worker = types.ModuleType("continuous_inference")
    worker.ContinuousInferenceWorker = object
    utils = types.ModuleType("utils")
    utils.__path__ = []
    metrics = types.ModuleType("utils.prometheus_metrics")
    for name in ["inference_predictions_total", "inference_prediction_latency", "inference_errors_total",
                 "inference_data_points_total", "inference_fraud_rate", "inference_model_loaded",
                 "inference_cumulative_frauds", "inference_cumulative_total"]:
        setattr(metrics, name, _Metric())
    metrics.get_metrics_exposition = lambda: ("", "text/plain")
    metrics.track_prediction_latency = lambda f: f
    log_cfg = types.ModuleType("utils.logging_config")
    log_cfg.setup_structured_logging = lambda name, level: logging.getLogger(name)
    for mod in (main, worker, utils, metrics, log_cfg):
        monkeypatch.setitem(sys.modules, mod.__name__, mod)


def load_server(monkeypatch, keys=None):
    _stub_modules(monkeypatch)
    if keys is None:
        monkeypatch.delenv("MONIGUARD_API_KEYS", raising=False)
    else:
        monkeypatch.setenv("MONIGUARD_API_KEYS", keys)
    name = "legacy_api_server_under_test"
    spec = importlib.util.spec_from_file_location(name, SERVER_PATH)
    mod = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, mod)
    spec.loader.exec_module(mod)
    return mod


def test_health_is_open(monkeypatch):
    client = load_server(monkeypatch).app.test_client()
    assert client.get("/health").status_code == 200


def test_no_keys_configured_refuses(monkeypatch):
    client = load_server(monkeypatch).app.test_client()
    assert client.get("/inference/stats").status_code == 503
    assert client.post("/inference/run", json={}).status_code == 503


@pytest.mark.parametrize("headers", [{}, {"X-API-Key": "wrong"}, {"X-API-Key": ""}])
def test_missing_or_wrong_key_rejected(monkeypatch, headers):
    client = load_server(monkeypatch, keys="k1,k2").app.test_client()
    for method, path in [("get", "/inference/stats"), ("get", "/results"), ("post", "/inference/run"),
                         ("post", "/predict"), ("post", "/inference/predict_from_api")]:
        assert getattr(client, method)(path, headers=headers).status_code == 401, path


def test_valid_key_reaches_handler(monkeypatch):
    mod = load_server(monkeypatch, keys="k1, k2")
    client = mod.app.test_client()
    # No pipeline is initialised in the test, so the handler itself answers 500, after auth passed.
    resp = client.post("/inference/run", headers={"X-API-Key": "k2"}, json={})
    assert resp.status_code == 500
    assert resp.get_json()["error"] == "Inference pipeline not initialized"


def test_hashed_key_entry_accepted(monkeypatch):
    import hashlib

    digest = hashlib.sha256(b"plain-key").hexdigest()
    client = load_server(monkeypatch, keys=digest).app.test_client()
    assert client.get("/inference/stats", headers={"X-API-Key": "plain-key"}).status_code != 401
    assert client.get("/inference/stats", headers={"X-API-Key": digest}).status_code == 401


def test_errors_do_not_leak_exception_text(monkeypatch):
    mod = load_server(monkeypatch, keys="k1")
    secret = "password authentication failed for user fraud_producer at 10.0.0.5"

    class Boom:
        model = object()

        def run_inference(self, **kwargs):
            raise RuntimeError(secret)

    mod.inference_pipeline = Boom()
    resp = mod.app.test_client().post("/inference/run", headers={"X-API-Key": "k1"}, json={})
    assert resp.status_code == 500
    assert secret not in resp.get_data(as_text=True)
