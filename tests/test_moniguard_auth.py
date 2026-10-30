"""Security tests for the Moniguard Flask dashboard (moniguard/app.py).

The module reads its configuration at import time, so every test loads a fresh
copy with a controlled environment. These tests do not need a trained model.
"""
import importlib.util
import logging
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
APP_PATH = REPO_ROOT / "moniguard" / "app.py"
STRONG = "x" * 40


def load_app(monkeypatch, **env):
    import dotenv

    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: False)  # ignore developer's local .env
    for k in ["SECRET_KEY", "MONIGUARD_DEV_MODE", "MONIGUARD_ADMIN_PASSWORD", "MONIGUARD_EXEC_PASSWORD",
              "MONIGUARD_OPS_PASSWORD", "MONIGUARD_ANALYST_PASSWORD", "MONIGUARD_SECURE_COOKIES"]:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("DB_HOST", "127.0.0.1")
    monkeypatch.setenv("DB_PORT", "9")  # fail fast, no DNS
    monkeypatch.setenv("INFERENCE_SERVICE_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "http://127.0.0.1:9")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    name = "moniguard_app_under_test"
    sys.modules.pop(name, None)
    spec = importlib.util.spec_from_file_location(name, APP_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod  # Flask resolves root_path (templates/) via sys.modules[import_name].__file__
    spec.loader.exec_module(mod)
    return mod


def test_missing_secret_key_refuses_to_start(monkeypatch):
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        load_app(monkeypatch)


def test_legacy_default_secret_rejected(monkeypatch):
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        load_app(monkeypatch, SECRET_KEY="Moniguard-secret-key-change-in-production")


def test_short_secret_rejected(monkeypatch):
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        load_app(monkeypatch, SECRET_KEY="short")


def test_dev_mode_generates_random_key(monkeypatch, caplog):
    with caplog.at_level(logging.WARNING):
        a = load_app(monkeypatch, MONIGUARD_DEV_MODE="true")
        b = load_app(monkeypatch, MONIGUARD_DEV_MODE="true")
    assert a.app.secret_key != b.app.secret_key
    assert len(a.app.secret_key) == 64 and len(b.app.secret_key) == 64
    assert "MONIGUARD_DEV_MODE" in caplog.text


def test_strong_secret_used(monkeypatch):
    mod = load_app(monkeypatch, SECRET_KEY=STRONG)
    assert mod.app.secret_key == STRONG
