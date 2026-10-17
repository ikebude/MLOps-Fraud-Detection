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
