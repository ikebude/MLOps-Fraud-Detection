#!/usr/bin/env python3
"""
offline_train_demo.py — the `make demo` pipeline for Moniguard v2.

Generates synthetic historical transactions (reusing the real
`TransactionGenerator` from `producer/main.py` — the same generator that
feeds the live Kafka/Postgres stream, just given historical timestamps
instead of "now"), engineers the 74 features from
`src/utils/feature_engineering.py` (the same module imported by both
training and inference, per architecture rule: one feature source of
truth), trains the XGBoost + Isolation Forest ensemble described in
the Moniguard v2 product spec (kept outside this repo), evaluates it on a *time-based* split (train on
the earlier period, test on the later period — never a random shuffle,
which would leak future information into training), and writes real,
reproducible numbers to reports/metrics.json.

This script does not require Postgres, Kafka, Docker, or Airflow — it is
the fast, dependency-light path that lets `make demo` run on a fresh
clone. The full docker-compose stack (producer -> Kafka -> streaming
inference -> Postgres -> FastAPI -> dashboard) is the production-shaped
path; this script is how the numbers quoted in the README are produced
and can be reproduced by anyone.

Usage:
    python3 scripts/offline_train_demo.py [--n-transactions 150000] [--days 180]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "producer"))

from producer.main import TransactionGenerator  # noqa: E402
from src.utils.feature_engineering import FeatureEngineer  # noqa: E402


# Fixed reference date for the demo dataset. Measuring timestamps back from the real "now" made
# hour-of-day / weekday / account-age features (and so every metric) change from run to run.
DEFAULT_ANCHOR = "2026-10-01T00:00:00+00:00"


def generate_historical_dataset(
    n_transactions: int, days: int, seed: int = 42, anchor: str = DEFAULT_ANCHOR
) -> pd.DataFrame:
    """Generate `n_transactions` using the real TransactionGenerator, with
    timestamps spread uniformly at random over the `days` days before `anchor`
    instead of all being "now" (the generator's live-streaming default), so a
    genuine time-based split is possible. Same seed + anchor -> identical rows."""
    import random

    np.random.seed(seed)
    now = datetime.fromisoformat(anchor)
    gen = TransactionGenerator(seed=seed, anchor=now)
    rows = []
    attempts = 0
    while len(rows) < n_transactions and attempts < n_transactions * 2:
        attempts += 1
        txn = gen.generate_transaction()
        if txn is None:
            continue
        offset_seconds = random.uniform(0, days * 86400)
        historical_ts = now - timedelta(seconds=offset_seconds)
        txn["timestamp"] = historical_ts.isoformat()
        rows.append(txn)

    df = pd.DataFrame(rows)
    df = df.sort_values("timestamp").reset_index(drop=True)
    return df


def bootstrap_ci(y_true: np.ndarray, y_score: np.ndarray, metric_fn, n_boot: int = 500, seed: int = 42):
    """95% bootstrap CI for a metric function(y_true, y_score)."""
    rng = np.random.RandomState(seed)
    n = len(y_true)
    stats = []
    for _ in range(n_boot):
        idx = rng.randint(0, n, n)
        yt, ys = y_true[idx], y_score[idx]
        if yt.sum() == 0 or yt.sum() == n:
            continue
        try:
            stats.append(metric_fn(yt, ys))
        except Exception:
            continue
    if not stats:
        return None, None
    lo, hi = np.percentile(stats, [2.5, 97.5])
    return float(lo), float(hi)


def recall_at_alert_rate(y_true: np.ndarray, y_score: np.ndarray, alert_rate: float) -> float:
    """Recall achieved if we alert on the top `alert_rate` fraction of scores."""
    n = len(y_score)
    k = max(1, int(np.ceil(n * alert_rate)))
    threshold_idx = np.argsort(y_score)[::-1][:k]
    alerted = np.zeros(n, dtype=bool)
    alerted[threshold_idx] = True
    tp = (alerted & (y_true == 1)).sum()
    total_fraud = (y_true == 1).sum()
    return float(tp / total_fraud) if total_fraud > 0 else float("nan")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n-transactions", type=int, default=150_000)
    parser.add_argument("--days", type=int, default=180)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--anchor", type=str, default=DEFAULT_ANCHOR,
        help="ISO date the synthetic history ends at (fixed so reruns reproduce the same data).",
    )
    parser.add_argument(
        "--output-dir", type=str, default=None,
        help="Override output root (default: the repo itself — reports/ and "
             "moniguard/models/offline_demo/ under it). Tests point this at a "
             "tmp dir so test runs never overwrite the real demo artifacts.",
    )
    args = parser.parse_args()
    output_root = Path(args.output_dir) if args.output_dir else REPO_ROOT

    t0 = time.time()
    print(f"[1/5] Generating {args.n_transactions} synthetic transactions over {args.days} days...")
    df = generate_historical_dataset(args.n_transactions, args.days, seed=args.seed, anchor=args.anchor)
    fraud_rate = df["is_fraud"].mean()
    print(f"      {len(df)} rows generated, fraud rate = {fraud_rate:.4%}")

    print("[2/5] Engineering features (src/utils/feature_engineering.FeatureEngineer)...")
    fe = FeatureEngineer()
    df_feat = fe.engineer_features(df)

    print("[3/5] Time-based split (first 70% of the period = train, last 30% = test)...")
    df_feat = df_feat.sort_values("timestamp").reset_index(drop=True)
    split_idx = int(len(df_feat) * 0.7)
    split_ts = df_feat.iloc[split_idx]["timestamp"]
    train_df = df_feat[df_feat["timestamp"] < split_ts].copy()
    test_df = df_feat[df_feat["timestamp"] >= split_ts].copy()
    print(f"      train={len(train_df)} rows (fraud={train_df['is_fraud'].mean():.4%}), "
          f"test={len(test_df)} rows (fraud={test_df['is_fraud'].mean():.4%})")

    drop_cols = [
        "transaction_id", "order_id", "user_id", "full_name", "email", "phone_number",
        "session_id", "timestamp", "registration_date", "device_id", "ip_address",
        "delivery_address", "product_id", "product_name", "vendor_id", "fraud_type",
        "is_fraud", "rating", "currency", "geo_location", "location",
    ]
    categorical_cols = [
        "gender", "account_status", "action", "device_type", "browser", "category",
        "payment_method", "payment_status", "country", "refund_status",
    ]

    from sklearn.preprocessing import OrdinalEncoder

    feature_cols = [c for c in df_feat.columns if c not in drop_cols]
    cat_present = [c for c in categorical_cols if c in feature_cols]
    num_present = [c for c in feature_cols if c not in cat_present]

    encoder = OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1)
    encoder.fit(train_df[cat_present].astype(str))

    def build_matrix(d: pd.DataFrame) -> pd.DataFrame:
        X_num = d[num_present].apply(pd.to_numeric, errors="coerce").fillna(0.0)
        X_cat = pd.DataFrame(
            encoder.transform(d[cat_present].astype(str)), columns=cat_present, index=d.index
        )
        return pd.concat([X_num, X_cat], axis=1)

    X_train, y_train = build_matrix(train_df), train_df["is_fraud"].astype(int).values
    X_test, y_test = build_matrix(test_df), test_df["is_fraud"].astype(int).values

    print("[4/5] Training XGBoost (class-weighted) + Isolation Forest, calibrating ensemble...")
    import xgboost as xgb
    from sklearn.ensemble import IsolationForest
    from sklearn.isotonic import IsotonicRegression
    from sklearn.metrics import average_precision_score, roc_auc_score

    scale_pos_weight = (y_train == 0).sum() / max(1, (y_train == 1).sum())
    xgb_model = xgb.XGBClassifier(
        n_estimators=300,
        max_depth=5,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        scale_pos_weight=scale_pos_weight,
        eval_metric="aucpr",
        random_state=args.seed,
        n_jobs=-1,
    )
    xgb_model.fit(X_train, y_train)
    xgb_train_proba = xgb_model.predict_proba(X_train)[:, 1]
    xgb_test_proba = xgb_model.predict_proba(X_test)[:, 1]

    iso_model = IsolationForest(
        n_estimators=200, contamination=float(y_train.mean()), random_state=args.seed, n_jobs=-1
    )
    iso_model.fit(X_train)
    # Isolation Forest: more negative score = more anomalous. Flip + min-max scale to [0, 1].
    iso_train_raw = -iso_model.score_samples(X_train)
    iso_test_raw = -iso_model.score_samples(X_test)
    iso_min, iso_max = iso_train_raw.min(), iso_train_raw.max()
    iso_train_norm = (iso_train_raw - iso_min) / (iso_max - iso_min + 1e-9)
    iso_test_norm = (iso_test_raw - iso_min) / (iso_max - iso_min + 1e-9)

    ensemble_train = 0.7 * xgb_train_proba + 0.3 * iso_train_norm
    ensemble_test = 0.7 * xgb_test_proba + 0.3 * iso_test_norm

    calibrator = IsotonicRegression(out_of_bounds="clip")
    calibrator.fit(ensemble_train, y_train)
    calibrated_test = calibrator.predict(ensemble_test)
    risk_score_test = (calibrated_test * 1000).round().astype(int)

    print("[5/5] Evaluating on the held-out (later-in-time) test set...")
    pr_auc = average_precision_score(y_test, calibrated_test)
    roc_auc = roc_auc_score(y_test, calibrated_test)
    recall_at_1pct = recall_at_alert_rate(y_test, calibrated_test, 0.01)
    recall_at_5pct = recall_at_alert_rate(y_test, calibrated_test, 0.05)

    pr_auc_ci = bootstrap_ci(y_test, calibrated_test, average_precision_score)
    roc_auc_ci = bootstrap_ci(y_test, calibrated_test, roc_auc_score)

    # Scoring latency (p95), single-row at a time, matching the FastAPI /v1/score path.
    sample_idx = np.random.RandomState(args.seed).choice(len(X_test), size=min(500, len(X_test)), replace=False)
    latencies_ms = []
    for i in sample_idx:
        row = X_test.iloc[[i]]
        t_start = time.perf_counter()
        xp = xgb_model.predict_proba(row)[:, 1][0]
        ip = -iso_model.score_samples(row)[0]
        ip_norm = (ip - iso_min) / (iso_max - iso_min + 1e-9)
        _ = calibrator.predict([0.7 * xp + 0.3 * ip_norm])
        latencies_ms.append((time.perf_counter() - t_start) * 1000)
    p95_latency_ms = float(np.percentile(latencies_ms, 95))

    elapsed = time.time() - t0

    metrics = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": {
            "source": "synthetic Nigerian pay-on-delivery e-commerce generator "
                       "(producer/main.py TransactionGenerator), NOT a public benchmark — "
                       "see README Provenance / Data sections",
            "n_transactions": int(len(df)),
            "days_spanned": args.days,
            "anchor": args.anchor,
            "fraud_rate_overall": float(fraud_rate),
            "n_train": int(len(train_df)),
            "n_test": int(len(test_df)),
            "fraud_rate_train": float(train_df["is_fraud"].mean()),
            "fraud_rate_test": float(test_df["is_fraud"].mean()),
            "split_method": "time-based (train = earliest 70% of the period, "
                             "test = latest 30%; never shuffled)",
        },
        "model": {
            "ensemble": "0.7 * XGBoost (class-weighted) + 0.3 * Isolation Forest (min-max normalized), "
                        "isotonic-calibrated, scaled to a 0-1000 risk score",
            "n_features": int(X_train.shape[1]),
        },
        "metrics": {
            "pr_auc": {"value": float(pr_auc), "ci95": pr_auc_ci},
            "roc_auc": {"value": float(roc_auc), "ci95": roc_auc_ci},
            "recall_at_1pct_alert_rate": recall_at_1pct,
            "recall_at_5pct_alert_rate": recall_at_5pct,
            "p95_scoring_latency_ms": p95_latency_ms,
        },
        "run": {
            "elapsed_seconds": round(elapsed, 1),
            "seed": args.seed,
        },
        "honesty_note": "These are real numbers from this exact script, on synthetic data generated "
                         "by this repo's own generator. They are NOT measured on PaySim or IEEE-CIS "
                         "(no Kaggle credentials were available when this run was produced) and do "
                         "not represent performance on real transaction data.",
    }

    reports_dir = output_root / "reports"
    reports_dir.mkdir(exist_ok=True, parents=True)
    with open(reports_dir / "metrics.json", "w") as f:
        json.dump(metrics, f, indent=2)

    models_dir = output_root / "moniguard" / "models" / "offline_demo"
    models_dir.mkdir(parents=True, exist_ok=True)
    xgb_model.save_model(str(models_dir / "xgb_model.json"))
    import joblib
    joblib.dump(iso_model, models_dir / "iso_model.joblib")
    joblib.dump(calibrator, models_dir / "calibrator.joblib")
    joblib.dump(encoder, models_dir / "ordinal_encoder.joblib")
    with open(models_dir / "feature_columns.json", "w") as f:
        json.dump(
            {
                "numeric": num_present,
                "categorical": cat_present,
                "iso_min": float(iso_min),
                "iso_max": float(iso_max),
                "ensemble_weights": {"xgb": 0.7, "iso": 0.3},
                "decision_thresholds": {"review": 300, "block": 700},
            },
            f,
            indent=2,
        )

    print()
    print("=" * 72)
    print(f"PR-AUC:                  {pr_auc:.4f}  (95% CI {pr_auc_ci})")
    print(f"ROC-AUC:                 {roc_auc:.4f}  (95% CI {roc_auc_ci})")
    print(f"Recall @ 1% alert rate:  {recall_at_1pct:.4f}")
    print(f"Recall @ 5% alert rate:  {recall_at_5pct:.4f}")
    print(f"p95 scoring latency:     {p95_latency_ms:.2f} ms")
    print(f"Wall-clock time:         {elapsed:.1f}s")
    print(f"Metrics written to:      {reports_dir / 'metrics.json'}")
    print("=" * 72)


if __name__ == "__main__":
    main()
