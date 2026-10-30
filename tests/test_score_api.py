"""Tests for the FastAPI app in src/inference/score_api.py."""
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "producer"))


@pytest.fixture()
def client(tiny_model_dir, monkeypatch):
    import src.inference.score_api as score_api_module
    from fastapi.testclient import TestClient
    from src.inference.scoring import FraudScorer

    monkeypatch.setenv("MONIGUARD_API_KEYS", "test-key")
    score_api_module._scorer = FraudScorer(models_dir=tiny_model_dir)
    return TestClient(score_api_module.app)


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_score_requires_api_key(client):
    resp = client.post("/v1/score", json={"transaction": {}})
    assert resp.status_code in (401, 422)  # 422 if header missing entirely, 401 if present-but-wrong


def test_score_rejects_wrong_api_key(client):
    resp = client.post(
        "/v1/score", json={"transaction": {}}, headers={"X-API-Key": "wrong-key"}
    )
    assert resp.status_code == 401


def test_score_with_valid_key_returns_contract(client):
    from producer.main import TransactionGenerator

    gen = TransactionGenerator()
    txn = gen.generate_transaction()
    while txn is None:
        txn = gen.generate_transaction()

    resp = client.post(
        "/v1/score", json={"transaction": txn}, headers={"X-API-Key": "test-key"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert 0 <= body["score"] <= 1000
    assert body["decision"] in {"approve", "review", "block"}
    assert body["latency_ms"] >= 0


def test_labels_endpoint_records_feedback(client, tmp_path, monkeypatch):
    resp = client.post(
        "/v1/labels",
        json={"transaction_id": "TXN_TEST123", "is_fraud": 1},
        headers={"X-API-Key": "test-key"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"status": "recorded"}


def _post_label(client, key):
    return client.post(
        "/v1/labels",
        json={"transaction_id": "TXN_TEST123", "is_fraud": 1},
        headers={"X-API-Key": key},
    )


def test_unconfigured_keys_fail_closed(client, monkeypatch):
    monkeypatch.delenv("MONIGUARD_API_KEYS", raising=False)
    resp = client.post("/v1/score", json={"transaction": {}}, headers={"X-API-Key": "demo-key"})
    assert resp.status_code == 503
    assert _post_label(client, "demo-key").status_code == 503


def test_blank_keys_fail_closed(client, monkeypatch):
    monkeypatch.setenv("MONIGUARD_API_KEYS", " , ,")
    resp = client.post("/v1/score", json={"transaction": {}}, headers={"X-API-Key": "demo-key"})
    assert resp.status_code == 503


def test_demo_key_not_accepted_by_default(client, monkeypatch):
    monkeypatch.setenv("MONIGUARD_API_KEYS", "test-key")
    resp = client.post("/v1/score", json={"transaction": {}}, headers={"X-API-Key": "demo-key"})
    assert resp.status_code == 401


def test_prehashed_key_accepted(client, monkeypatch):
    import hashlib

    digest = hashlib.sha256(b"s3cret").hexdigest()
    monkeypatch.setenv("MONIGUARD_API_KEYS", digest)
    assert _post_label(client, "s3cret").status_code == 200
    assert _post_label(client, digest).status_code == 401


def test_multiple_keys(client, monkeypatch):
    monkeypatch.setenv("MONIGUARD_API_KEYS", "a-key, b-key")
    assert _post_label(client, "a-key").status_code == 200
    assert _post_label(client, "b-key").status_code == 200


def test_incomplete_artifacts_give_503_not_500(client, monkeypatch):
    """Artifacts from an older training run (no iso_min/iso_max) must fail with an actionable 503."""
    import src.inference.score_api as score_api_module

    def old_artifacts():
        raise KeyError("iso_min")

    monkeypatch.setattr(score_api_module, "_scorer", None)
    monkeypatch.setattr(score_api_module, "FraudScorer", old_artifacts)
    resp = client.post("/v1/score", json={"transaction": {}}, headers={"X-API-Key": "test-key"})
    assert resp.status_code == 503
    assert "retrain" in resp.json()["detail"]
