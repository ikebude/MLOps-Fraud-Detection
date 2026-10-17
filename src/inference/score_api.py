"""
score_api.py — Moniguard v2's FastAPI serving layer, per PRODUCT_SPECS.md
section 1: `POST /v1/score` returning {score, decision, reasons[],
model_version}, plus `/v1/labels` for feedback and `/health` for the load
balancer / docker-compose healthcheck.

This is a thin wrapper around src/inference/scoring.FraudScorer — a single
scoring code path shared with reports/metrics.json's offline evaluation, so
the number on the dashboard and the number in the README are never two
different pipelines that can silently drift apart.

Run locally:
    uvicorn src.inference.score_api:app --reload --port 8000
"""
from __future__ import annotations

import hashlib
import os
import time
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from src.inference.scoring import FraudScorer

app = FastAPI(title="Moniguard Scoring API", version="2.0.0")

_scorer: Optional[FraudScorer] = None


def get_scorer() -> FraudScorer:
    global _scorer
    if _scorer is None:
        try:
            _scorer = FraudScorer()
        except FileNotFoundError as e:
            raise HTTPException(
                status_code=503,
                detail=f"Model artifacts not found — run `make demo` or "
                       f"`python3 scripts/offline_train_demo.py` first. ({e})",
            )
    return _scorer


# ---------------------------------------------------------------------------
# API key auth — hashed keys only, matching PRODUCT_SPECS.md "API keys hashed;
# rate-limited." A real deployment sources these from the DB (see
# fraudguard/platform for the pattern this reuses); for the demo, keys come
# from MONIGUARD_API_KEYS (comma-separated, already-hashed or plaintext —
# plaintext entries are hashed on the fly for convenience in local dev).
# ---------------------------------------------------------------------------
def _configured_key_hashes() -> set:
    raw = os.getenv("MONIGUARD_API_KEYS", "demo-key")
    hashes = set()
    for key in raw.split(","):
        key = key.strip()
        if not key:
            continue
        hashes.add(key if len(key) == 64 else hashlib.sha256(key.encode()).hexdigest())
    return hashes


def require_api_key(x_api_key: str = Header(..., alias="X-API-Key")) -> str:
    hashed = hashlib.sha256(x_api_key.encode()).hexdigest()
    if hashed not in _configured_key_hashes():
        raise HTTPException(status_code=401, detail="invalid API key")
    return x_api_key


class ScoreRequest(BaseModel):
    transaction: Dict[str, Any] = Field(
        ..., description="Raw transaction payload, same shape as producer/main.py's generator output."
    )


class ScoreResponse(BaseModel):
    score: int
    probability: float
    decision: str
    reasons: List[Dict[str, Any]]
    model_version: str
    latency_ms: float


class LabelRequest(BaseModel):
    transaction_id: str
    is_fraud: int = Field(..., ge=0, le=1)


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/score", response_model=ScoreResponse)
def score_transaction(req: ScoreRequest, _: str = Depends(require_api_key)) -> ScoreResponse:
    scorer = get_scorer()
    t0 = time.perf_counter()
    result = scorer.score(req.transaction)
    latency_ms = (time.perf_counter() - t0) * 1000
    return ScoreResponse(**result, latency_ms=round(latency_ms, 2))


@app.post("/v1/labels")
def submit_label(req: LabelRequest, _: str = Depends(require_api_key)) -> Dict[str, str]:
    """Accepts a ground-truth label arriving later (per spec: 'is_fraud 1/0
    arriving later'). The demo appends to a local JSONL feedback log that
    the Airflow retrain DAG reads; it does not retrain inline."""
    import json
    from pathlib import Path

    log_path = Path(__file__).resolve().parent.parent.parent / "reports" / "labels_feedback.jsonl"
    log_path.parent.mkdir(exist_ok=True)
    with open(log_path, "a") as f:
        f.write(json.dumps({"transaction_id": req.transaction_id, "is_fraud": req.is_fraud}) + "\n")
    return {"status": "recorded"}
