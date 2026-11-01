"""Shared fixtures. Trains a small, fast model (2,000 synthetic rows) once
per test session so tests don't depend on the full offline_train_demo.py
run (150k rows) finishing — same code path, smaller data, for speed."""
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "producer"))


@pytest.fixture(scope="session")
def tiny_model_dir(tmp_path_factory):
    """Run the real training script at a tiny scale, into a throwaway
    models dir, and return that dir's path."""
    import subprocess

    out_root = tmp_path_factory.mktemp("tiny_demo")
    script = REPO_ROOT / "scripts" / "offline_train_demo.py"
    # Run via subprocess so the script's own REPO_ROOT-relative paths stay
    # correct, then point FraudScorer at the models it wrote.
    subprocess.run(
        [
            sys.executable, str(script),
            "--n-transactions", "4000", "--days", "60", "--serving-sample", "100",
            "--output-dir", str(out_root),
        ],
        check=True,
        cwd=REPO_ROOT,
    )
    return out_root / "moniguard" / "models" / "offline_demo"


@pytest.fixture(scope="session")
def scorer(tiny_model_dir):
    from src.inference.scoring import FraudScorer

    return FraudScorer(models_dir=tiny_model_dir)
