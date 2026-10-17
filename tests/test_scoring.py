"""Tests for src/inference/scoring.FraudScorer — the ensemble scoring path
shared by the FastAPI /v1/score endpoint and the offline evaluation."""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "producer"))

from producer.main import TransactionGenerator  # noqa: E402


def _card_fraud_transaction() -> dict:
    """A transaction shaped like the generator's 'card_fraud' pattern:
    very high value, very short session, bulk quantity."""
    gen = TransactionGenerator()
    txn = gen.generate_transaction()
    while txn is None:
        txn = gen.generate_transaction()
    txn["amount"] = 450_000.0
    txn["session_duration"] = 20
    txn["quantity"] = 8
    txn["discount"] = 0
    txn["is_fraud"] = 1
    return txn


def _typical_transaction() -> dict:
    gen = TransactionGenerator()
    txn = gen.generate_transaction()
    while txn is None or txn["is_fraud"] == 1:
        txn = gen.generate_transaction()
    return txn


def test_score_contract(scorer):
    result = scorer.score(_typical_transaction())
    assert set(result.keys()) == {"score", "probability", "decision", "reasons", "model_version"}
    assert 0 <= result["score"] <= 1000
    assert 0.0 <= result["probability"] <= 1.0
    assert result["decision"] in {"approve", "review", "block"}
    assert isinstance(result["reasons"], list)
    assert len(result["reasons"]) <= 5


def test_card_fraud_pattern_scores_higher_than_typical_on_average(scorer):
    """Statistical, not a single-sample assertion: over several samples of
    each kind, the engineered card-fraud pattern should score higher on
    average than ordinary transactions. Flags a real regression (ensemble
    broken, feature pipeline mismatched) without being flaky over one draw."""
    fraud_scores = [scorer.score(_card_fraud_transaction())["score"] for _ in range(15)]
    typical_scores = [scorer.score(_typical_transaction())["score"] for _ in range(15)]

    avg_fraud = sum(fraud_scores) / len(fraud_scores)
    avg_typical = sum(typical_scores) / len(typical_scores)
    assert avg_fraud > avg_typical, (
        f"expected card-fraud-shaped transactions to score higher on average "
        f"({avg_fraud:.1f}) than typical ones ({avg_typical:.1f})"
    )


def test_reasons_reference_real_feature_names(scorer):
    result = scorer.score(_card_fraud_transaction())
    for reason in result["reasons"]:
        assert "feature" in reason and "signal" in reason
        assert isinstance(reason["feature"], str) and len(reason["feature"]) > 0


def test_model_version_is_non_empty_string(scorer):
    assert isinstance(scorer.model_version(), str)
    assert len(scorer.model_version()) > 0
