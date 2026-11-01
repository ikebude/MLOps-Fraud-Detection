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
    client.post("/logout")
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


# ---------------------------------------------------------------------------
# Item 5: alert updates
# ---------------------------------------------------------------------------
def _client_as(mod, user, key):
    client = mod.app.test_client()
    assert _login(client, user, PASSWORDS[key]).status_code == 302
    return client


@pytest.fixture()
def analyst(app_mod):
    app_mod._alerts_store.clear()
    return app_mod, _client_as(app_mod, "Analyst User", "MONIGUARD_ANALYST_PASSWORD")


def test_executive_cannot_update_alert(app_mod):
    app_mod._alerts_store.clear()
    client = _client_as(app_mod, "Exec User", "MONIGUARD_EXEC_PASSWORD")
    resp = client.post("/api/alerts/ALT-X1", json={"status": "Under Review"})
    assert resp.status_code == 403
    assert app_mod._alerts_store == []


def test_unknown_status_rejected(analyst):
    mod, client = analyst
    resp = client.post("/api/alerts/ALT-X1", json={"status": "<img src=x onerror=alert(1)>"})
    assert resp.status_code == 400
    assert mod._alerts_store == []
    assert client.post("/api/alerts/ALT-X1", json={"status": ["New"]}).status_code == 400


def test_unknown_assignee_rejected(analyst):
    mod, client = analyst
    assert client.post("/api/alerts/ALT-X1", json={"assigned_to": "<b>Mallory</b>"}).status_code == 400
    assert mod._alerts_store == []


def test_known_assignee_accepted(analyst):
    _, client = analyst
    assert client.post("/api/alerts/ALT-X1", json={"assigned_to": "Ops User"}).status_code == 200


def test_bad_alert_id_rejected(analyst):
    _, client = analyst
    assert client.post("/api/alerts/ALT-%3Cscript%3E", json={"status": "New"}).status_code == 400
    assert client.post("/api/alerts/" + "A" * 200, json={"status": "New"}).status_code == 400


def test_valid_update_by_analyst(analyst):
    _, client = analyst
    resp = client.post("/api/alerts/ALT-TXN_0A1B2C3D", json={"status": "Under Review"})
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True


def test_ops_can_confirm_fraud(app_mod):
    client = _client_as(app_mod, "Ops User", "MONIGUARD_OPS_PASSWORD")
    assert client.post("/api/alerts/ALT-OPS1", json={"status": "Confirmed Fraud"}).status_code == 200


def test_alert_store_bounded(analyst, monkeypatch):
    mod, client = analyst
    monkeypatch.setattr(mod, "_MAX_ALERT_STATE", 3)
    for i in range(3):
        assert client.post(f"/api/alerts/ALT-{i}", json={"status": "New"}).status_code == 200
    assert client.post("/api/alerts/ALT-3", json={"status": "New"}).status_code == 429
    # updating an existing alert is still allowed at the limit
    assert client.post("/api/alerts/ALT-0", json={"status": "Escalated"}).status_code == 200


def test_alert_id_with_trailing_newline_rejected(analyst):
    mod, client = analyst
    assert client.post("/api/alerts/ALT-abc%0A", json={"status": "New"}).status_code == 400
    assert mod._alerts_store == []


def test_alert_update_requires_json_object(analyst):
    """A cross-site form or text/plain POST (CSRF shape) must not create or change state."""
    mod, client = analyst
    body = '{"status": "Confirmed Fraud"}'
    assert client.post("/api/alerts/ALT-C1", data=body, content_type="text/plain").status_code == 400
    assert client.post("/api/alerts/ALT-C1", data={"status": "Confirmed Fraud"}).status_code == 400
    assert client.post("/api/alerts/ALT-C1", json=["New"]).status_code == 400
    assert mod._alerts_store == []


def test_notification_settings_require_json_object(app_mod):
    client = _client_as(app_mod, "Admin User", "MONIGUARD_ADMIN_PASSWORD")
    before = dict(app_mod._notification_settings)
    resp = client.post("/api/notification-settings", data='{"method": "sms"}', content_type="text/plain")
    assert resp.status_code == 400
    assert app_mod._notification_settings == before
    assert client.post("/api/notification-settings", json={"method": "sms"}).status_code == 200


def test_login_throttled_after_repeated_failures(app_mod):
    client = app_mod.app.test_client()
    for _ in range(app_mod._LOGIN_MAX_FAILURES):
        assert _login(client, "Admin User", "wrong-password").status_code == 401
    # Locked out even with the right password until the window passes.
    assert _login(client, "Admin User", "admin-pass-123456").status_code == 429
    # Other accounts are not affected.
    assert _login(app_mod.app.test_client(), "Analyst User", "analyst-pass-1234").status_code == 302
    # After the window, the correct password works again and clears the counter.
    key = ("Admin User", "127.0.0.1")
    app_mod._login_failures[key] = [t - app_mod._LOGIN_WINDOW_SECONDS - 1 for t in app_mod._login_failures[key]]
    assert _login(client, "Admin User", "admin-pass-123456").status_code == 302
    assert key not in app_mod._login_failures


def test_dashboard_templates_escape_data():
    """Every page that renders transaction/alert/log data through innerHTML uses esc()."""
    root = REPO_ROOT / "moniguard"
    base = (root / "templates" / "base.html").read_text(encoding="utf-8")
    assert "window.esc = function" in base
    checks = {
        "templates/transactions.html": ["${esc(txn.merchant || txn.user_id)}", "${esc(item.feature)}"],
        "templates/ops_dashboard.html": ["${esc(tx.merchant)}", "takeAction('${esc(alert.id)}', 'block')"],
        "templates/admin_dashboard.html": ["${esc(log.action)}", "${esc(log.system)}"],
        "templates/base.html": ["${esc(message)}"],
        "static/js/dashboard-enhanced.js": ["${esc(txn.merchant)}", "esc(txn.merchant || 'Unknown')",
                                            "${esc(f.feature)}", "${esc(message)}"],
    }
    for rel, needles in checks.items():
        text = (root / rel).read_text(encoding="utf-8")
        for needle in needles:
            assert needle in text, f"{rel} is missing {needle}"


def test_pages_brand_as_moniguard(app_mod):
    """Every rendered page carries the Moniguard name and no other product's."""
    import re

    admin = _client_as(app_mod, "Admin User", "MONIGUARD_ADMIN_PASSWORD")
    anon = app_mod.app.test_client()
    for client, path in [(anon, "/login"), (admin, "/admin"), (admin, "/settings")]:
        html = client.get(path).get_data(as_text=True)
        text = re.sub(r"\s+", "", re.sub(r"<[^>]+>", "", html)).lower()
        assert "fraud" + "guard" not in text, path  # split so a repo-wide name search stays clean
        assert "moniguard" in text, path


# ---------------------------------------------------------------------------
# Audit 2026-11-01: logout method, error bodies, security headers, pinned CDN assets
# ---------------------------------------------------------------------------
def test_logout_requires_post(app_mod):
    client = _client_as(app_mod, "Admin User", "MONIGUARD_ADMIN_PASSWORD")
    assert client.get("/logout").status_code == 405
    assert client.get("/admin").status_code == 200  # a GET (e.g. a cross-site <img>) did not log out
    resp = client.post("/logout")
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/login")
    assert client.get("/admin").status_code == 302


def test_errors_do_not_leak_exception_text(app_mod, monkeypatch):
    secret = "relation fraud_predictions does not exist at host db-internal"

    def boom(*a, **k):
        raise RuntimeError(secret)

    monkeypatch.setattr(app_mod, "get_live_fraud_feed", boom)
    monkeypatch.setattr(app_mod, "get_all_predictions_feed", boom)
    client = _client_as(app_mod, "Admin User", "MONIGUARD_ADMIN_PASSWORD")
    for path in ("/api/alerts/ALT-1", "/api/transactions"):
        resp = client.get(path)
        assert resp.status_code == 500, path
        assert secret not in resp.get_data(as_text=True), path


def test_security_headers(app_mod):
    resp = app_mod.app.test_client().get("/login")
    csp = resp.headers["Content-Security-Policy"]
    for directive in ("default-src 'self'", "object-src 'none'", "frame-ancestors 'none'", "base-uri 'self'"):
        assert directive in csp
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"


def test_versioned_cdn_assets_have_sri():
    """Chart.js and the icon font are pinned and integrity-checked. The Tailwind Play CDN cannot be
    (it compiles in the browser); it is listed as an open item in tasks/AUDIT_2026-11-01.md."""
    import re

    base = (REPO_ROOT / "moniguard" / "templates" / "base.html").read_text(encoding="utf-8")
    for tag in re.findall(r"<(?:script|link)[^>]+(?:unpkg\.com|jsdelivr\.net)[^>]*>", base):
        assert re.search(r"@\d+\.\d+\.\d+/", tag), tag
        assert 'integrity="sha384-' in tag and 'crossorigin="anonymous"' in tag, tag
