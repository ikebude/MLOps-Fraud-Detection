"""Tests for src/utils/feature_engineering.FeatureEngineer — the single
feature source of truth shared by training and inference."""
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "producer"))

from producer.main import TransactionGenerator  # noqa: E402
from src.utils.feature_engineering import FeatureEngineer  # noqa: E402


@pytest.fixture(scope="module")
def raw_batch():
    gen = TransactionGenerator()
    rows = [t for t in (gen.generate_transaction() for _ in range(500)) if t is not None]
    return pd.DataFrame(rows)


def test_engineer_features_adds_expected_feature_families(raw_batch):
    fe = FeatureEngineer()
    out = fe.engineer_features(raw_batch)

    expected = [
        "amount_zscore", "is_high_value", "account_age_days",
        "identity_verification_score", "device_trust_score", "ip_risk_score",
        "failed_payment_ratio", "fraud_ring_score", "activity_timing_score",
        "address_reuse_rate", "refund_abuse_score", "hour_of_day",
    ]
    for col in expected:
        assert col in out.columns, f"missing engineered feature: {col}"
    assert len(out) == len(raw_batch)


def test_engineered_scores_stay_in_unit_range(raw_batch):
    fe = FeatureEngineer()
    out = fe.engineer_features(raw_batch)
    for col in ["identity_verification_score", "device_trust_score", "ip_risk_score"]:
        assert out[col].min() >= 0.0
        assert out[col].max() <= 1.0


def test_no_nans_in_core_numeric_features(raw_batch):
    fe = FeatureEngineer()
    out = fe.engineer_features(raw_batch)
    core = ["amount_zscore", "account_age_days", "user_transaction_count", "time_since_prev_txn_sec"]
    for col in core:
        assert out[col].isna().sum() == 0, f"unexpected NaNs in {col}"


def test_fraud_rate_is_within_generator_spec(raw_batch):
    # Generator targets a 2.8% fraud rate; on 500 rows this should land
    # within a generous statistical band, not exactly 2.8%.
    rate = raw_batch["is_fraud"].mean()
    assert 0.0 <= rate <= 0.15


def test_features_do_not_depend_on_the_label(raw_batch):
    """Training frames carry is_fraud, serving payloads do not; the features must be identical."""
    fe = FeatureEngineer()
    with_label = fe.engineer_features(raw_batch)
    flipped = raw_batch.assign(is_fraud=1 - raw_batch["is_fraud"])
    without_label = fe.engineer_features(raw_batch.drop(columns=["is_fraud"]))
    feature_cols = [c for c in without_label.columns]
    pd.testing.assert_frame_equal(with_label[feature_cols], without_label[feature_cols])
    pd.testing.assert_frame_equal(fe.engineer_features(flipped)[feature_cols], without_label[feature_cols])
