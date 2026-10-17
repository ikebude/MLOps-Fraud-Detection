"""
scoring.py — shared scoring logic for Moniguard v2's /v1/score endpoint.

Loads the artifacts written by scripts/offline_train_demo.py (XGBoost model,
Isolation Forest, isotonic calibrator, ordinal encoder, feature-column list)
and scores a single raw transaction the same way the offline training script
evaluates its test set — same FeatureEngineer, same ensemble weights, same
calibration — so the API's live score and the README's reported metrics
come from one code path, not two that can drift apart.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

import joblib
import numpy as np
import pandas as pd
import xgboost as xgb

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MODELS_DIR = REPO_ROOT / "moniguard" / "models" / "offline_demo"

import sys  # noqa: E402

sys.path.insert(0, str(REPO_ROOT))
from src.utils.feature_engineering import FeatureEngineer  # noqa: E402


class FraudScorer:
    """Loads model artifacts once and scores raw transactions."""

    def __init__(self, models_dir: Path = MODELS_DIR):
        self.models_dir = models_dir
        self.xgb_model = xgb.XGBClassifier()
        self.xgb_model.load_model(str(models_dir / "xgb_model.json"))
        self.iso_model = joblib.load(models_dir / "iso_model.joblib")
        self.calibrator = joblib.load(models_dir / "calibrator.joblib")
        self.encoder = joblib.load(models_dir / "ordinal_encoder.joblib")
        with open(models_dir / "feature_columns.json") as f:
            cols = json.load(f)
        self.numeric_cols: List[str] = cols["numeric"]
        self.categorical_cols: List[str] = cols["categorical"]
        self.feature_engineer = FeatureEngineer()

        # Exactly the min/max Isolation Forest scores observed at train
        # time (persisted by offline_train_demo.py), reused here unchanged
        # so a live score is normalized identically to how the reported
        # metrics were computed — not approximated by a different function.
        self._iso_min: float = cols["iso_min"]
        self._iso_max: float = cols["iso_max"]
        weights = cols.get("ensemble_weights", {"xgb": 0.7, "iso": 0.3})
        self._w_xgb = weights["xgb"]
        self._w_iso = weights["iso"]
        thresholds = cols.get("decision_thresholds", {"review": 300, "block": 700})
        self._review_threshold = thresholds["review"]
        self._block_threshold = thresholds["block"]

    @classmethod
    def model_version(cls) -> str:
        meta_path = MODELS_DIR / "feature_columns.json"
        if meta_path.exists():
            return f"offline_demo-{int(meta_path.stat().st_mtime)}"
        return "unloaded"

    def _build_feature_row(self, raw_txn: Dict[str, Any]) -> pd.DataFrame:
        """Run the same FeatureEngineer used in training on a single-row
        DataFrame built from the raw transaction payload."""
        df = pd.DataFrame([raw_txn])
        df_feat = self.feature_engineer.engineer_features(df)

        num = df_feat.reindex(columns=self.numeric_cols, fill_value=0.0)
        num = num.apply(pd.to_numeric, errors="coerce").fillna(0.0)

        cat_raw = df_feat.reindex(columns=self.categorical_cols, fill_value="unknown").astype(str)
        cat_encoded = pd.DataFrame(
            self.encoder.transform(cat_raw), columns=self.categorical_cols, index=df_feat.index
        )
        return pd.concat([num, cat_encoded], axis=1)

    def score(self, raw_txn: Dict[str, Any]) -> Dict[str, Any]:
        X = self._build_feature_row(raw_txn)

        xgb_proba = float(self.xgb_model.predict_proba(X)[:, 1][0])
        iso_raw = float(-self.iso_model.score_samples(X)[0])
        # Same min-max normalization used in offline_train_demo.py, against
        # the exact train-time bounds (clipped — a live row can fall outside
        # the training range).
        iso_norm = (iso_raw - self._iso_min) / (self._iso_max - self._iso_min + 1e-9)
        iso_norm = min(max(iso_norm, 0.0), 1.0)

        ensemble = self._w_xgb * xgb_proba + self._w_iso * iso_norm
        calibrated = float(self.calibrator.predict([ensemble])[0])
        calibrated = min(max(calibrated, 0.0), 1.0)
        risk_score = int(round(calibrated * 1000))

        decision = (
            "block" if risk_score >= self._block_threshold
            else "review" if risk_score >= self._review_threshold
            else "approve"
        )
        reasons = self._top_reasons(X)

        return {
            "score": risk_score,
            "probability": round(calibrated, 4),
            "decision": decision,
            "reasons": reasons,
            "model_version": self.model_version(),
        }

    def _top_reasons(self, X: pd.DataFrame, top_n: int = 5) -> List[Dict[str, Any]]:
        """Feature-importance-weighted contribution ranking as plain-word
        reason codes. (SHAP TreeExplainer is the documented upgrade path —
        see README "What I'd do next" — this ships a lighter but genuinely
        computed alternative: XGBoost's built-in gain importances applied to
        this row's actual feature values, not a fixed/fake list.)"""
        importances = self.xgb_model.feature_importances_
        row = X.iloc[0]
        contributions = []
        for col, imp in zip(X.columns, importances):
            if imp <= 0:
                continue
            contributions.append((col, float(imp) * float(row[col])))
        contributions.sort(key=lambda t: abs(t[1]), reverse=True)
        return [
            {"feature": name, "signal": round(value, 4)}
            for name, value in contributions[:top_n]
        ]
