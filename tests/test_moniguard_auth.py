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


# ---------------------------------------------------------------------------
# Item 4: users, login, password reset
# ---------------------------------------------------------------------------
PASSWORDS = {
    "MONIGUARD_ADMIN_PASSWORD": "admin-pass-123456",
    "MONIGUARD_ANALYST_PASSWORD": "analyst-pass-1234",
    "MONIGUARD_EXEC_PASSWORD": "exec-pass-1234567",
    "MONIGUARD_OPS_PASSWORD": "ops-pass-12345678",
}


@pytest.fixture()
def app_mod(monkeypatch):
    return load_app(monkeypatch, SECRET_KEY=STRONG, **PASSWORDS)


def _login(client, user, password, **extra):
    return client.post("/login", data={"username": user, "password": password, **extra})


def test_passwords_stored_hashed(app_mod):
    assert app_mod.USERS
    for name, info in app_mod.USERS.items():
        assert "password" not in info
        assert info["password_hash"].startswith(("scrypt:", "pbkdf2:"))
        assert info["password_hash"] not in PASSWORDS.values()


def test_prehashed_env_value_accepted(monkeypatch):
    from werkzeug.security import generate_password_hash

    env = dict(PASSWORDS, MONIGUARD_ADMIN_PASSWORD=generate_password_hash("pre-hashed-pass!"))
    mod = load_app(monkeypatch, SECRET_KEY=STRONG, **env)
    resp = _login(mod.app.test_client(), "Admin User", "pre-hashed-pass!")
    assert resp.status_code == 302


def test_unset_password_disables_account(monkeypatch):
    env = {k: v for k, v in PASSWORDS.items() if k != "MONIGUARD_EXEC_PASSWORD"}
    mod = load_app(monkeypatch, SECRET_KEY=STRONG, **env)
    assert "Exec User" not in mod.USERS
    assert _login(mod.app.test_client(), "Exec User", "anything-at-all").status_code == 401


def test_login_ignores_form_role(app_mod):
    client = app_mod.app.test_client()
    resp = _login(client, "Analyst User", PASSWORDS["MONIGUARD_ANALYST_PASSWORD"], role="admin")
    assert resp.status_code == 302
    with client.session_transaction() as s:
        assert s["role"] == "analyst"
    resp = client.get("/admin")
    assert resp.status_code == 302
    assert not resp.headers["Location"].endswith("/admin")


def test_wrong_password_rejected(app_mod):
    client = app_mod.app.test_client()
    assert _login(client, "Admin User", "wrong-password").status_code == 401
    with client.session_transaction() as s:
        assert "username" not in s


def test_unknown_user_rejected(app_mod):
    client = app_mod.app.test_client()
    assert _login(client, "Nobody", "password").status_code == 401
    with client.session_transaction() as s:
        assert "username" not in s


def test_forgot_password_removed(app_mod):
    client = app_mod.app.test_client()
    for method in (client.get, client.post):
        resp = method("/forgot-password")
        assert resp.status_code == 302 and resp.headers["Location"].endswith("/login")
    assert _login(client, "Admin User", PASSWORDS["MONIGUARD_ADMIN_PASSWORD"]).status_code == 302
    assert client.get("/forgot-password").status_code == 404
    client.post("/forgot-password", data={"name": "Admin User", "new_password": "pwned"})
    client.get("/logout")
    assert _login(client, "Admin User", "pwned").status_code == 401
    assert _login(client, "Admin User", PASSWORDS["MONIGUARD_ADMIN_PASSWORD"]).status_code == 302


def test_no_password_material_in_pages(app_mod):
    client = app_mod.app.test_client()
    _login(client, "Admin User", PASSWORDS["MONIGUARD_ADMIN_PASSWORD"])
    for path in ("/admin", "/alerts"):
        resp = client.get(path)
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        for needle in ["scrypt:", "pbkdf2:", "password_hash", *PASSWORDS.values()]:
            assert needle not in body


def test_session_cookie_flags(app_mod):
    resp = _login(app_mod.app.test_client(), "Admin User", PASSWORDS["MONIGUARD_ADMIN_PASSWORD"])
    cookie = resp.headers["Set-Cookie"]
    assert "HttpOnly" in cookie and "SameSite=Lax" in cookie


def test_hash_password_cli(app_mod, monkeypatch):
    import getpass

    from werkzeug.security import check_password_hash

    monkeypatch.setattr(getpass, "getpass", lambda *a, **k: "long-enough-pass")
    runner = app_mod.app.test_cli_runner()
    result = runner.invoke(args=["hash-password"])
    assert result.exit_code == 0
    assert check_password_hash(result.output.strip(), "long-enough-pass")

    answers = iter(["long-enough-pass", "different-pass-xx"])
    monkeypatch.setattr(getpass, "getpass", lambda *a, **k: next(answers))
    assert runner.invoke(args=["hash-password"]).exit_code != 0
