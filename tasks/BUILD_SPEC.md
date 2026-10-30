# BUILD_SPEC — fraud workstream (Moniguard / mlops-fraud-detection)

Branch: `ccr-7d21c86c-pnbh8t` (exists locally; no upstream yet). Clone is shallow:
run `git fetch origin main` before the first push. Never push to `main`, never force-push,
never rewrite history. Commit author: `git -c user.name=ikebude -c user.email=precious.ikebude@outlook.com commit ...`.
This repo has no CLAUDE.md, so commit trailers are allowed (see section 4).

## 1. Context and goal

Moniguard is a fraud-scoring portfolio project: an offline-trained XGBoost + Isolation Forest
ensemble served by FastAPI (`src/inference/score_api.py`), plus a Flask analyst dashboard
(`moniguard/app.py`) and a docker-compose stack (`src/docker-compose.yml`). The goal is to make
it **secure and deployment-ready without changing any ML result**. The README must still match
`reports/metrics.json`: PR-AUC 0.877, ROC-AUC 0.943, p95 latency 47.9 ms. Do not retrain and do
not touch `reports/metrics.json` or `moniguard/models/offline_demo/*`.

### Baseline (measured by the planner on 2026-10-29, HEAD `f0845a5`)

Environment: Python 3.13.17 venv with requirements-demo.txt + pytest, pytest-cov, httpx
(xgboost 3.4.1, fastapi 0.162.0, flask 3.1.3). The CI command, exactly as in `.github/workflows/ci.yml`:

```bash
python3 -m pytest tests/ -v \
  --cov=src.utils.feature_engineering --cov=src.inference.scoring --cov=src.inference.score_api \
  --cov-report=term-missing --cov-fail-under=70
```

Result: **13 passed, 1 warning, 189.7 s**. Coverage: score_api.py 92% (62 stmts, 5 missed:
35-38, 59), scoring.py 99%, feature_engineering.py 99%, **TOTAL 97.14% (245 stmts, 7 missed)**.
There is no lint or typecheck config in the repo. `docker compose -f src/docker-compose.yml config -q`
exits 0 but does not catch the bugs in item 6. Most of the 190 s is the session fixture that
trains a small model (`tests/conftest.py`).

Vulnerabilities the planner reproduced with Flask's test client (script in TEST_PLAN.md §2):
- `Analyst User` / `password` + form field `role=admin`: 302 to `/admin`, then `/admin` returns 200.
- `POST /forgot-password name=Admin User new_password=pwned`: "updated successfully". Logging in as Admin with `pwned` then works.
- `GET /alerts` as Ops User: the HTML contains `"password"`, because `{{ USERS | tojson }}` dumps the whole user dict, passwords included.
- Exec User `POST /api/alerts/X1 {"status":"<img src=x onerror=alert(1)>"}`: 200, and the value is stored. Executives aren't meant to act on alerts, and `alerts.html` renders the value through `innerHTML` (stored XSS).
- `app.secret_key` == `Moniguard-secret-key-change-in-production`.

## 2. Work items (in this order; every item must leave the suite green)

---

### Item 1: Stop tracking secrets and runtime junk; complete `.env.example`

**Why.** These files are tracked even though `.gitignore` already lists `.env`, `.agent/`, `.vscode`:
- `.env` (106 lines) and `src/.env` (49 lines) hold the default credentials (airflow/airflow, minioadmin,
  producer/training DB passwords, and a test Fernet key in the root `.env`).
- `src/state/producer_state.sqlite` with its `-shm`/`-wal` files (55 MB). No code references it: `git grep -n sqlite` finds nothing in .py/.yml.
- `src/logs/`: 125 Airflow task logs (30 MB).
- `src/models/fraud_detection_model.pkl` (2.7 MB). The Airflow DAG writes it to `/app/models`
  (`src/plugins/fraud_detection_training.py:1045`). Compose bind-mounts `./models` into Airflow
  (`src/docker-compose.yml:66`) and into inference (`:337`), so `make train` regenerates it.
- `.agent/` (2 notes, no ownership wording) and `.vscode/settings.json`.
- `src/docker-compose.yml:15` falls back to a committed test Fernet key:
  `${AIRFLOW__CORE__FERNET_KEY:-dGVzdF9rZXlfZm9yX2RldmVsb3BtZW50X29ubHk_}`.
- The root `.env.example` lacks many keys that are in `.env`, for example `AIRFLOW__CORE__FERNET_KEY`,
  `MINIO_*`, `MLFLOW_DB_*`, `_AIRFLOW_WWW_USER_*`, `INFERENCE_*`, `FLASK_*`, `XGB_N_JOBS`.

**Files.**
- `git rm --cached` (keep the local copies): `.env`, `src/.env`, `src/state/producer_state.sqlite`,
  `src/state/producer_state.sqlite-shm`, `src/state/producer_state.sqlite-wal`, `-r src/logs`,
  `src/models/fraud_detection_model.pkl`, `-r .agent`, `-r .vscode`.
- Add empty `src/models/.gitkeep` and `src/state/.gitkeep`. `src/config/.gitkeep` already exists.
- `.gitignore`: append a block:
  ```
  # Secrets and runtime state (never commit)
  .env
  src/.env
  src/state/*
  !src/state/.gitkeep
  src/logs/
  src/models/*
  !src/models/.gitkeep
  .agent/
  .vscode/
  .venv/
  ```
  Do not add a blanket `*.pkl` or `models/`, because `moniguard/models/offline_demo/*` must stay tracked.
- `.env.example` (root) and `src/.env.example`. Each must list **every** key in its matching `.env`
  plus the new keys from items 2-4: `SECRET_KEY`, `MONIGUARD_DEV_MODE`, `MONIGUARD_SECURE_COOKIES`,
  `MONIGUARD_ADMIN_PASSWORD`, `MONIGUARD_EXEC_PASSWORD`, `MONIGUARD_OPS_PASSWORD`,
  `MONIGUARD_ANALYST_PASSWORD`, `MONIGUARD_API_KEYS`, and in `src/.env.example` also `AIRFLOW__CORE__FERNET_KEY`.
  Secret values must be empty, or `change-me` where a non-empty value is needed for compose to
  start (DB passwords). `SECRET_KEY=`, `AIRFLOW__CORE__FERNET_KEY=` and `MONIGUARD_API_KEYS=` stay **empty**.
  Put a one-line comment above each new key saying how to generate it:
  `python -c "import secrets; print(secrets.token_hex(32))"`, `scripts/generate_fernet_key.sh`, or
  `flask --app moniguard/app.py hash-password` (from item 4). Non-secret values (hosts, ports,
  `FRAUD_API_URL`) keep their current values. **Do not change the `FRAUD_API_URL` value** (see section 3).
- `src/docker-compose.yml:15`: replace the default with a required variable:
  `AIRFLOW__CORE__FERNET_KEY: '${AIRFLOW__CORE__FERNET_KEY:?Set AIRFLOW__CORE__FERNET_KEY in src/.env (run scripts/generate_fernet_key.sh)}'`
- README: add a section "Configuration and secrets" after "How to run". It explains copying
  `src/.env.example` to `src/.env` and the required keys, and includes a table **"Defaults that must be
  rotated"** listing every credential that was ever committed, by name only, never by value:
  Airflow web user/password, Postgres airflow user, transactions DB producer/training passwords,
  MLflow DB password, MinIO root user/password and AWS keys, Airflow Fernet key, Grafana admin
  (`GF_SECURITY_ADMIN_PASSWORD` defaults to `admin` at compose:447), and the old Flask secret key.
  Add one sentence: these values remain in git history and must be treated as public.
  In the existing "Access" table, replace `airflow/airflow` and `minioadmin/minioadmin` with
  "set in `src/.env`". For the Moniguard Dashboard row, use "`MONIGUARD_*_PASSWORD` in `src/.env`".

**Edge cases.** `scripts/setup-local.sh` copies `src/.env.example` to `src/.env`. After this item, compose
refuses to start until the Fernet key is filled in. That is intended: document it in the README section.
Do not edit the heredoc fallback in setup-local.sh/.ps1 (it contains `FRAUD_API_URL`; see section 3).

**Done when.**
- `git ls-files | grep -E '(^|/)\.env$|src/state/.*sqlite|^src/logs/|\.pkl$|^\.agent/|^\.vscode/'` prints nothing.
- `git ls-files moniguard/models/offline_demo | wc -l` is 5.
- For both pairs, `comm -23 <(grep -oE '^[A-Z_][A-Z0-9_]*' .env | sort -u) <(grep -oE '^[A-Z_][A-Z0-9_]*' .env.example | sort -u)` is empty. Use the same command for `src/`.
- `cd src && env -u AIRFLOW__CORE__FERNET_KEY docker compose config -q` fails with the message above. `AIRFLOW__CORE__FERNET_KEY=x docker compose config -q` exits 0 (if `src/.env` sets the key, test with a temporary copy that lacks it).
- The test suite still passes 13/13.

---

### Item 2: Scoring API fails closed (no `demo-key` default)

**Why.** `src/inference/score_api.py:54`, `raw = os.getenv("MONIGUARD_API_KEYS", "demo-key")`: anyone can
call `/v1/score` and `/v1/labels` with `X-API-Key: demo-key` unless the operator remembers to set the variable.
In addition, `:60` treats **any** 64-character string as a pre-hashed key, so a 64-character plaintext key is never hashed.

**Files.** `src/inference/score_api.py`, `tests/test_score_api.py`.

**Design.**
```python
import hmac, logging, re
logger = logging.getLogger(__name__)
_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")

def _configured_key_hashes() -> set[str]:
    raw = os.getenv("MONIGUARD_API_KEYS", "")
    hashes = set()
    for key in raw.split(","):
        key = key.strip()
        if not key:
            continue
        hashes.add(key.lower() if _SHA256_HEX.fullmatch(key.lower()) else hashlib.sha256(key.encode()).hexdigest())
    return hashes

def require_api_key(x_api_key: str = Header(..., alias="X-API-Key")) -> str:
    configured = _configured_key_hashes()
    if not configured:
        logger.error("MONIGUARD_API_KEYS is not set; refusing all scoring requests")
        raise HTTPException(status_code=503, detail="scoring API is not configured with any API keys")
    hashed = hashlib.sha256(x_api_key.encode()).hexdigest()
    if not any(hmac.compare_digest(hashed, h) for h in configured):
        raise HTTPException(status_code=401, detail="invalid API key")
    return x_api_key
```
Update the module docstring and the comment at :46-52 to say that keys are required and there is no default.
The docstring at :2 and the comment at :47 reference `PRODUCT_SPECS.md`, which isn't in this repo. Reword
these to "the Moniguard v2 product spec (kept outside this repo)". The `fraudguard/platform` mention at :49 is
handled in item 9; if you do item 2 first, leave it for item 9 so that each commit stays focused.

**New tests** (in `tests/test_score_api.py`, reusing the `client` fixture and `monkeypatch`):
- `test_unconfigured_keys_fail_closed`: `monkeypatch.delenv("MONIGUARD_API_KEYS", raising=False)`. A POST to `/v1/score` with `X-API-Key: demo-key` returns 503, and so does a POST to `/v1/labels`.
- `test_blank_keys_fail_closed`: `MONIGUARD_API_KEYS=" , ,"` returns 503.
- `test_demo_key_not_accepted_by_default`: `MONIGUARD_API_KEYS=test-key`, header `demo-key`, returns 401.
- `test_prehashed_key_accepted`: set the env to `hashlib.sha256(b"s3cret").hexdigest()`. Header `s3cret` returns 200 on `/v1/labels`. Header equal to the hash itself returns 401.
- `test_multiple_keys`: `"a-key, b-key"`. Both keys return 200 on `/v1/labels`.

**Edge cases.** The env var is read on every request, which existing tests rely on, so keep it that way.
`/health` stays unauthenticated. `test_labels_endpoint_records_feedback` writes to
`reports/labels_feedback.jsonl`, which is gitignored. Don't change that.

**Done when.** All score_api tests pass (5 existing + 5 new). Coverage of score_api.py is at least 92%.
`grep -n demo-key src/inference/score_api.py` prints nothing.

---

### Item 3: Dashboard refuses to start without a real `SECRET_KEY`; harden the session cookie

**Why.** At `moniguard/app.py:36`, `app.secret_key = os.getenv('SECRET_KEY', 'Moniguard-secret-key-change-in-production')`.
Anyone who knows the public default can forge a session cookie containing `{'username': 'Admin User', 'role': 'admin'}`.

**Files.** `moniguard/app.py`, `requirements-demo.txt`, new `tests/test_moniguard_auth.py`, `.github/workflows/ci.yml` (only if needed, see below).

**Design** (module level, placed immediately after `app = Flask(__name__)`):
```python
import secrets
_LEGACY_DEFAULT_SECRET = 'Moniguard-secret-key-change-in-production'
_DEV_MODE = os.getenv('MONIGUARD_DEV_MODE', 'false').lower() == 'true'

def _load_secret_key() -> str:
    key = os.getenv('SECRET_KEY', '')
    if key and key != _LEGACY_DEFAULT_SECRET and len(key) >= 32:
        return key
    if _DEV_MODE:
        logger.warning("SECRET_KEY missing/weak; MONIGUARD_DEV_MODE=true so using a random per-process key "
                       "(sessions will not survive a restart). Never use dev mode in deployment.")
        return secrets.token_hex(32)
    raise RuntimeError("SECRET_KEY must be set to a random value of at least 32 characters "
                       "(python -c \"import secrets; print(secrets.token_hex(32))\"). "
                       "For local development only, set MONIGUARD_DEV_MODE=true to generate one.")

app.secret_key = _load_secret_key()
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=os.getenv('MONIGUARD_SECURE_COOKIES', 'false').lower() == 'true',
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
)
```

**Test harness** (`tests/test_moniguard_auth.py`). The module reads its config at import time, so load
a fresh copy for each test:
```python
import importlib.util, sys
from pathlib import Path
import pytest
REPO_ROOT = Path(__file__).resolve().parent.parent
APP_PATH = REPO_ROOT / "moniguard" / "app.py"

def load_app(monkeypatch, **env):
    import dotenv
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: False)  # ignore developer's local .env
    for k in ["SECRET_KEY", "MONIGUARD_DEV_MODE", "MONIGUARD_ADMIN_PASSWORD", "MONIGUARD_EXEC_PASSWORD",
              "MONIGUARD_OPS_PASSWORD", "MONIGUARD_ANALYST_PASSWORD", "MONIGUARD_SECURE_COOKIES"]:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("DB_HOST", "127.0.0.1"); monkeypatch.setenv("DB_PORT", "9")       # fail fast, no DNS
    monkeypatch.setenv("INFERENCE_SERVICE_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "http://127.0.0.1:9")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    name = "moniguard_app_under_test"
    sys.modules.pop(name, None)
    spec = importlib.util.spec_from_file_location(name, APP_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod      # Flask resolves root_path (templates/) via sys.modules[import_name].__file__
    spec.loader.exec_module(mod)
    return mod
```
`STRONG = "x" * 40`. These tests must **not** depend on the `tiny_model_dir` fixture, so they stay fast.

**Tests for this item.**
- `test_missing_secret_key_refuses_to_start`: `load_app(monkeypatch)` raises `RuntimeError` matching "SECRET_KEY".
- `test_legacy_default_secret_rejected`: `SECRET_KEY=Moniguard-secret-key-change-in-production` raises `RuntimeError`.
- `test_short_secret_rejected`: `SECRET_KEY="short"` raises `RuntimeError`.
- `test_dev_mode_generates_random_key`: two loads with `MONIGUARD_DEV_MODE=true` give two different 64-character keys, and `caplog` contains "MONIGUARD_DEV_MODE".
- `test_strong_secret_used`: `SECRET_KEY=STRONG` gives `mod.app.secret_key == STRONG`.
- `test_session_cookie_flags`: once item 4 lands, log in and check that `Set-Cookie` contains `HttpOnly` and `SameSite=Lax`. Write this test in item 4.

**Dependencies.** Add the following to `requirements-demo.txt`, with a comment such as "# moniguard dashboard (security tests)":
`flask>=3.1,<4` (3.1.3 exists on PyPI; werkzeug 3.x comes with it) and `requests>=2.31`. `mlflow` and `psycopg2`
are optional imports in app.py (`try/except ImportError`), so they aren't needed. `psycopg2-binary` is already listed.
CI already installs requirements-demo.txt, so `ci.yml` needs no change for dependencies.

**Coverage.** Do **not** add `moniguard` to the `--cov` targets. app.py has about 900 statements, and adding
it would make the TOTAL figure in the README describe something different. The CI coverage scope stays exactly as it is.

**Done when.** Five new tests pass. The full suite passes. Smoke check from a shell with no local `.env` supplying the key:
`cd moniguard && env -u SECRET_KEY -u MONIGUARD_DEV_MODE python -c "import app"` exits non-zero with the RuntimeError message.
(app.py needs `import re` and `import secrets` added at the top for items 3-5.)

---

### Item 4: Hashed demo users from env; login role comes from the stored user; remove self-service reset; stop leaking users to templates

**Why.**
- `moniguard/app.py:39-44`: four users with plaintext password `'password'`.
- `:1405-1412`: `role = request.form.get('role')` and `session['role'] = role or user.get('role')`. This lets any user become admin (reproduced).
- `:1432-1446`: `/forgot-password` sets any user's password with no verification (reproduced). It is also whitelisted in `check_auth` (`:398`).
- `:964,967` + `templates/alerts.html:126`: `{{ USERS | tojson }}` sends every password to the browser (reproduced). `:1452` passes `USERS` to `admin_dashboard.html`, which reads only `username` and `info.role`.
- `templates/login.html:45-56` has a role `<select>`. `:62-67` links to Forgot Password.

**Files.** `moniguard/app.py`, `moniguard/templates/login.html`, `moniguard/templates/alerts.html`,
`moniguard/templates/admin_dashboard.html` (only if needed), delete `moniguard/templates/password_reset.html`,
`tests/test_moniguard_auth.py`, README (dashboard login paragraph).

**Design.**
```python
from werkzeug.security import generate_password_hash, check_password_hash

_DEMO_ACCOUNTS = [  # (username, role, env var holding its password or werkzeug hash)
    ('Admin User', 'admin', 'MONIGUARD_ADMIN_PASSWORD'),
    ('Exec User', 'executive', 'MONIGUARD_EXEC_PASSWORD'),
    ('Ops User', 'operations', 'MONIGUARD_OPS_PASSWORD'),
    ('Analyst User', 'analyst', 'MONIGUARD_ANALYST_PASSWORD'),
]
_HASH_PREFIXES = ('scrypt:', 'pbkdf2:')

def _load_users() -> dict:
    users = {}
    for username, role, env_var in _DEMO_ACCOUNTS:
        secret = os.getenv(env_var, '')
        if not secret:
            continue                      # account disabled when its password is not configured
        pw_hash = secret if secret.startswith(_HASH_PREFIXES) else generate_password_hash(secret)
        users[username] = {'password_hash': pw_hash, 'role': role}
    if not users:
        logger.warning("No MONIGUARD_*_PASSWORD set: no dashboard user can log in.")
    return users

USERS = _load_users()
_DUMMY_HASH = generate_password_hash(secrets.token_hex(16))   # equalises timing for unknown usernames

def _public_users() -> dict:
    """Safe view for templates: never includes password hashes."""
    return {name: {'role': info['role']} for name, info in USERS.items()}
```
Login POST:
```python
username = request.form.get('username', '')
password = request.form.get('password', '')
user = USERS.get(username)
ok = check_password_hash(user['password_hash'] if user else _DUMMY_HASH, password)
if user and ok:
    session.clear()                      # prevent session fixation
    session['username'] = username
    session['role'] = user['role']       # ONLY from the stored user; any form 'role' is ignored
    ...redirect by role as today...
return render_template('login.html', error='Invalid credentials'), 401
```
- Delete the `/forgot-password` route, `password_reset.html`, the `'/forgot-password'` entry in `check_auth`'s
  `allowed_paths`, and the Forgot Password link and role `<select>` in `login.html`. In place of the link, add
  a short line: "Forgot your password? Ask an administrator to reset it." Keep the username hint line.
- Admin reset path, as a Flask CLI command in app.py:
  ```python
  @app.cli.command('hash-password')
  def hash_password_cmd():
      """Print a werkzeug hash to paste into MONIGUARD_<ROLE>_PASSWORD, then restart the dashboard."""
      import getpass, click
      pw = getpass.getpass('New password: ')
      if len(pw) < 12 or pw != getpass.getpass('Repeat: '):
          raise click.ClickException('Passwords must match and be at least 12 characters.')
      click.echo(generate_password_hash(pw))
  ```
  Document it in the README: `SECRET_KEY=... flask --app moniguard/app.py hash-password`. Then put the
  output in `src/.env` and run `docker compose restart Moniguard`. A werkzeug hash contains `$`, so tell users
  to single-quote it in `.env` (compose would otherwise interpolate `$`). Check this claim against how compose
  handles `$` in env_file values and pick the quoting that works (`'...'`, or `$$`). The tester will check it.
- Templates: `admin_dashboard.html` gets `USERS=_public_users()`. `alerts.html` gets `USERNAMES=sorted(USERS)`
  in both render calls (`:964` and `:967`). In alerts.html, change line 126 to
  `<script id="users-data" type="application/json">{{ USERNAMES | tojson }}</script>` and line 130 to
  `const USERS = JSON.parse(document.getElementById('users-data').textContent || '[]');`.
- `grep -n "USERS" moniguard/templates/*.html` must show no use of a password or hash field afterwards.

**Tests** (add to `tests/test_moniguard_auth.py`; fixture `app_mod` = `load_app(monkeypatch, SECRET_KEY=STRONG,
MONIGUARD_ADMIN_PASSWORD="admin-pass-123456", MONIGUARD_ANALYST_PASSWORD="analyst-pass-1234",
MONIGUARD_EXEC_PASSWORD="exec-pass-1234567", MONIGUARD_OPS_PASSWORD="ops-pass-12345678")`):
- `test_passwords_stored_hashed`: every `USERS[u]` has no `'password'` key, and `password_hash` starts with `scrypt:` or `pbkdf2:` and is not the plaintext.
- `test_prehashed_env_value_accepted`: set the env to `generate_password_hash("pre-hashed-pass!")`. Logging in with `pre-hashed-pass!` returns 302.
- `test_unset_password_disables_account`: load without `MONIGUARD_EXEC_PASSWORD`. `'Exec User' not in USERS`, and login returns 401.
- `test_login_ignores_form_role`: analyst logs in with `role=admin`. Inside `with client.session_transaction() as s`, `s['role'] == 'analyst'`. `GET /admin` returns 302 with a Location that does not end in `/admin`.
- `test_wrong_password_rejected` and `test_unknown_user_rejected`: both return 401, and no `username` in the session.
- `test_forgot_password_removed`: unauthenticated GET/POST `/forgot-password` returns 302 to `/login`. Authenticated GET returns 404. After a POST that tries to change Admin's password, the old password still works and `pwned` does not.
- `test_no_password_material_in_pages`: as admin, `GET /admin` and `GET /alerts`. Neither body contains `scrypt:`, `pbkdf2:`, `password_hash`, or any configured plaintext password. Both return 200: the routes swallow DB failures, as the planner confirmed with the DB unreachable.
- `test_session_cookie_flags`: after a successful login, the `Set-Cookie` header contains `HttpOnly` and `SameSite=Lax`.
- `test_hash_password_cli`: `app.test_cli_runner()` with `getpass.getpass` monkeypatched to return `"long-enough-pass"` twice. The output passes `check_password_hash`. A mismatch gives exit_code != 0.

**Done when.** All the tests above pass. The full suite passes. The reproducer in TEST_PLAN §2 shows that every attack fails.

---

### Item 5: Lock down alert updates (`POST /api/alerts/<id>`)

**Why.** `moniguard/app.py:1558-1560` checks only `@login_required`, so executives can change cases.
`status` and `assigned_to` are stored verbatim (`:1585-1588`, `:1622-1623`) and rendered through `innerHTML`
template strings in `templates/alerts.html:139-190`, which is stored XSS (reproduced). Any `alert_id` is appended
to `_alerts_store` without limit (`:1580-1583`), so memory can grow without bound.

**Files.** `moniguard/app.py`, `moniguard/templates/alerts.html`, `tests/test_moniguard_auth.py`.

**Design** (POST branch only; GET stays `login_required`):
```python
ALERT_STATUSES = {'New', 'Under Review', 'Confirmed Fraud', 'False Positive', 'Escalated'}
ALERT_EDITOR_ROLES = {'analyst', 'operations', 'admin'}
_ALERT_ID_RE = re.compile(r'^ALT-[A-Za-z0-9_-]{1,12}$')
_MAX_ALERT_STATE = 10_000
```
- If the role is not in `ALERT_EDITOR_ROLES`, return 403 `{'error': 'forbidden'}` as JSON. Don't redirect, because callers use fetch.
- If `alert_id` doesn't match `_ALERT_ID_RE`, return 400. The IDs come from `_build_alert_from_transaction`: `ALT-` plus the first 12 characters of the transaction id with spaces removed, for example `ALT-TXN_0A1B2C3D`. Producer IDs are `TXN_` plus 16 uppercase hex characters (`producer/main.py:419`), and numeric DB ids also match.
- If `'status'` is present but not in `ALERT_STATUSES`, return 400. If `'assigned_to'` is present and is neither `None` nor `''` nor a key of `USERS`, return 400. Validate everything before mutating anything.
- If creating a new entry would push `_alerts_store` past `_MAX_ALERT_STATE`, return 429. Alternatively, evict the oldest entry, but choose one, document it in a comment, and test it.
- In `alerts.html`, add `function esc(v){ return String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }`
  and wrap every `${...}` that interpolates alert, transaction or user data inside the HTML strings with `esc(...)`.
  That covers `renderAlertCard`, `renderAlertsTableRows`, and the details modal. Numeric formatting expressions can stay
  as they are. Inline `onclick="takeAction('${a.id}',...)"` must use `esc(a.id)`: the id regex already blocks quotes,
  so this is defence in depth.

**Tests.**
- `test_executive_cannot_update_alert`: returns 403, and `_alerts_store` is unchanged.
- `test_unknown_status_rejected`: `"<img src=x onerror=alert(1)>"` returns 400.
- `test_unknown_assignee_rejected`: returns 400. `test_known_assignee_accepted` returns 200.
- `test_bad_alert_id_rejected`: `ALT-<script>` (URL-encoded) and a 200-character id both return 400.
- `test_valid_update_by_analyst`: `{"status": "Under Review"}` returns 200, and `success` is true.
- `test_alert_store_bounded`: monkeypatch `_MAX_ALERT_STATE` to 3 on the module. After 3 creations the 4th behaves as designed.

**Done when.** The tests pass. In the browser, the reproducer's XSS payload can no longer be stored, and existing
statuses still render. The ops dashboard's `Confirmed Fraud` POST (`templates/ops_dashboard.html:228-232`) still returns 200 for an ops user.

---

### Item 6: Make the compose stack actually build and run on Linux

**Why.** `src/docker-compose.yml:353` has `build: ../Moniguard` and `:374-376` mounts `../Moniguard/{data,static,templates}`,
but the directory is `moniguard/` (`ls -d ../Moniguard` gives "No such file"). On a case-sensitive filesystem the build
context doesn't exist, and the bind mounts would create empty host directories that hide `/app/templates`. In addition,
`:354` `image: fraud-detection-Moniguard:latest` is invalid, because Docker image repository names must be lowercase.
`scripts/verify-setup.sh:47` checks `../Moniguard`.

**Files.** `src/docker-compose.yml` (lines 353, 354, 374-376 only), `scripts/verify-setup.sh:47`.

**Design.** Change these to `../moniguard` and `image: fraud-detection-moniguard:latest`. **Keep the service name
`Moniguard` and `container_name: Moniguard-web`**, because the Makefile and docs refer to them. The service already
uses `env_file: .env`, so `SECRET_KEY` and `MONIGUARD_*` reach the container from `src/.env`. Add a comment there
saying that `SECRET_KEY` is required (item 3).

**Done when.**
- `cd src && AIRFLOW__CORE__FERNET_KEY=x docker compose config | grep -A3 "Moniguard:" ` shows `context: .../moniguard`.
- `docker compose config --images` lists `fraud-detection-moniguard:latest`.
- If a Docker daemon is available, `docker compose build Moniguard` succeeds. If it isn't, say so in Builder notes; don't claim it was built.

---

### Item 7: Makefile uses a venv, CI and README measure the same coverage, xgboost-cpu where it is a drop-in

**Why.**
- `Makefile:94` (demo) and `:101` (test-unit) run `pip install --break-system-packages`, which modifies the system Python.
- `Makefile:102` `test-unit` measures `--cov=src` (all of src/), but the README says "97% line coverage on the modules they
  target" and points to `make test-unit`. Only CI's scoped command produces 97%, so the claim and the command disagree.
- The `xgboost` wheel for linux x86_64 is 57.6 MB and pulls in NCCL/CUDA dependencies. `xgboost-cpu` 3.4.1 is the same
  `xgboost` module, built for CPU only, at 5.8 MB (checked on the PyPI JSON). xgboost-cpu has **no macOS wheels**
  (only manylinux_2_28 x86_64/aarch64 and win_amd64/arm64), so a single requirement line can't serve every platform.

**Files.** `Makefile`, `requirements-demo.txt`, `.github/workflows/ci.yml`, `.gitignore` (`.venv/` was added in item 1).

**Design.**
- `requirements-demo.txt`: replace `xgboost>=2.0` with:
  ```
  xgboost-cpu>=2.1.1; sys_platform != "darwin"   # CPU-only build, same `xgboost` module, ~10x smaller wheel
  xgboost>=2.0; sys_platform == "darwin"         # xgboost-cpu ships no macOS wheels
  ```
  Leave `src/requirements.txt`, `src/airflow/requirements.txt` and `src/inference/requirements.txt` alone. They pin
  `xgboost==2.0.2`, and `xgboost-cpu` has no 2.0.x release.
- Makefile:
  ```make
  VENV ?= .venv
  PY   := $(VENV)/bin/python
  COV_FLAGS := --cov=src.utils.feature_engineering --cov=src.inference.scoring --cov=src.inference.score_api \
               --cov-report=term-missing --cov-fail-under=70

  $(PY):
  	python3 -m venv $(VENV)
  	$(PY) -m pip install -q --upgrade pip

  venv: $(PY) ## Create .venv and install the demo/test dependencies
  	$(PY) -m pip install -q -r requirements-demo.txt pytest pytest-cov httpx

  demo: venv ## (keep existing help text)
  	$(PY) scripts/offline_train_demo.py
  	...existing echo lines; change the uvicorn hint to: MONIGUARD_API_KEYS=dev-key $(VENV)/bin/uvicorn src.inference.score_api:app --reload --port 8000

  test-unit: venv ## (keep existing help text)
  	$(PY) -m pytest tests/ -v $(COV_FLAGS)
  ```
  Add `venv` to `.PHONY`. Recipe lines must be indented with real tabs.
- ci.yml: replace the inline `--cov...` flags with `make test-unit`, or keep the inline flags if you prefer, but they must
  be **identical** to `COV_FLAGS`. Simplest: keep ci.yml's install step and run
  `python3 -m pytest tests/ -v $(the same flags)`, with a comment saying "keep in sync with Makefile COV_FLAGS".
  Don't add `--break-system-packages` anywhere.

**ML-results guard.** After the switch, in a fresh venv built with the xgboost-cpu requirements, load the committed
artifacts with `FraudScorer()` (default models_dir = `moniguard/models/offline_demo`). Score 5 transactions from
`TransactionGenerator` with `random.seed(42)`, `numpy.random.seed(42)` and `Faker.seed(42)`, and compare them with the
same script under the current `xgboost` install. The scores must be identical. Paste both outputs into Builder notes.
If they differ, revert the xgboost-cpu change and record why.

**Done when.** `make test-unit` passes in a clean checkout, without sudo and without `--break-system-packages`.
`grep -rn "break-system-packages" Makefile make.ps1 scripts .github` prints nothing.

---

### Item 8: README and docs truthfulness (links, coverage figure, run instructions)

**Why.**
- `README.md:43` links to `PRODUCT_SPECS.md` and `README.md:117` links to `PORTFOLIO_BUILD_PLAN.md`. Neither is in this repo.
  `docs/archive/README.md:9-10` says they live in the owner's `ikebude/chidi-who-am-ii` repo.
  `scripts/offline_train_demo.py:12` and `src/inference/score_api.py:2,47` mention `PRODUCT_SPECS.md` too.
- `README.md:131-134`: the coverage sentence must match what CI measures after item 7.
- `README.md:124-128`: the fast-path `uvicorn` command now needs `MONIGUARD_API_KEYS` (item 2).
- The README doesn't say how to log in to the dashboard (items 3-4).

**Files.** `README.md`, `scripts/offline_train_demo.py` (docstring line 12 only), `docs/archive/README.md` (no change needed; it already explains the location).

**Design.**
- Lines 43 and 117: replace the bare filenames with text such as "the Moniguard v2 product spec (kept in the owner's private planning notes, not in this repo)". **Don't invent a URL.** Keep the sentence meaning otherwise identical.
- Coverage sentence: "(... **NN% line coverage** of `src/utils/feature_engineering.py`, `src/inference/scoring.py` and `src/inference/score_api.py`, the modules CI measures; Moniguard dashboard auth is covered by `tests/test_moniguard_auth.py` but not included in that figure)". NN is the integer **floor** of the TOTAL from the final CI-flag run you paste.
- Fast path: `MONIGUARD_API_KEYS=dev-key uvicorn src.inference.score_api:app --reload --port 8000`, plus one line saying the API refuses every request (503) when no key is configured.
- API section line 145: add "there is no default key".
- "Configuration and secrets" (created in item 1): add the dashboard login: set `SECRET_KEY` and one or more `MONIGUARD_*_PASSWORD` values (plaintext or a `flask ... hash-password` hash); roles are fixed per account; there is no self-service password reset.
- **Do not change** the Results table numbers, the "Provenance" section, or the line "Built by **Precious Ikebude** ... not a 3Consulting deliverable."

**Done when.** The link check in TEST_PLAN §5 reports 0 broken relative links and 0 references to files missing from the repo.
`git grep -n "PRODUCT_SPECS.md\|PORTFOLIO_BUILD_PLAN.md" -- ':!docs/archive'` prints nothing. Every README number is traceable (TEST_PLAN §6).

---

---

### Item 9: The repo reads as Moniguard only (no FraudGuard naming)

**Why (owner decision, 2026-10-29, scratchpad `OWNER_DECISIONS.md` §1).** `ikebude/MLOps-Fraud-Detection` is the
owner's personal product **Moniguard**. **FraudGuard** is a different repo, a 3Consulting product under the
`Chidi-3Consulting` GitHub org. Nothing in this repo may be named or labelled in a way that implies it *is*
FraudGuard. Current hits from `git grep -n -i "fraudguard\|fraud guard"`:
- `.agent/FRAUDGUARD_UPGRADE_SUMMARY.md`: the filename says FraudGuard, but the content is about the Moniguard dashboard. Item 1 already untracks `.agent/`. Verify it is gone from `git ls-files`.
- `Makefile:61`: `echo "Fraud Guard: Not responding"`.
- `moniguard/Dockerfile:1`: `# Dockerfile for Fraud Guard Web Application`.
- `scripts/setup-local.sh:47`, `scripts/setup-local.ps1:53`: `# Fraud Guard` comment in the generated .env.
- `scripts/verify-setup.sh:76,89`: endpoint labels "Fraud Guard".
- `src/inference/score_api.py:49`: "(see fraudguard/platform for the pattern this reuses)". This points to FraudGuard code that isn't here and implies this API is FraudGuard's.
- `README.md:116`: "Add the industry-pack idea from the FraudGuard spec, ... per `PORTFOLIO_BUILD_PLAN.md` ...". This makes Moniguard's roadmap depend on the employer's spec.
- `cloud-init.yaml:20` clones the placeholder `https://github.com/your-repo/MLOps_Fraud_Detection.git`. The owner confirmed that Moniguard's repo is `ikebude/MLOps-Fraud-Detection`.
- `make.ps1:2` "Run from project root: MLOps_Fraud_Detection". This is a local folder name, harmless, so leave it.

**Files and changes.**
- Makefile:61, moniguard/Dockerfile:1, setup-local.sh:47, setup-local.ps1:53, verify-setup.sh:76,89: replace "Fraud Guard"
  with "Moniguard", for example "Moniguard dashboard". Comments and labels only, no behaviour change. On verify-setup.sh:89,
  also replace `(airflow/airflow)` with `(credentials in src/.env)`, in line with item 1.
- `score_api.py:46-52` comment: drop the `fraudguard/platform` sentence. The rewrite reads: keys come from
  `MONIGUARD_API_KEYS` (comma-separated, sha256 hex or plaintext hashed at load); a production deployment would store hashed
  keys in a database.
- README:116, item 4 of "What I'd do next": rewrite as "Add industry packs (feature and threshold presets), scoped to
  e-commerce and mobile money first." Don't mention a FraudGuard spec or `PORTFOLIO_BUILD_PLAN.md`. This also resolves
  item 8's line-117 reference.
- `cloud-init.yaml:20`: `git clone https://github.com/ikebude/MLOps-Fraud-Detection.git .`. Never point at any Chidi-3Consulting URL.
- **Keep the README "Provenance" section (lines 15-23) and lines 12-13 unchanged.** They state explicitly that Moniguard is
  *not* FraudGuard and *not* a 3Consulting deliverable, which is the distinction the owner wants. Don't add any link to the
  Chidi-3Consulting repo in this repo.
- Don't touch `src/logs/` content; item 1 untracks it. Check `docs/archive/*` and `moniguard/docs/*` with the same grep, and fix
  any "FraudGuard"/"Fraud Guard" label that names *this* project the same way. Leave sentences that name FraudGuard as a separate product.

**Done when.** `git grep -n -i "fraudguard\|fraud guard" -- ':!tasks'` prints only README Provenance lines 19 and 21.
`git ls-files | grep -i fraudguard` prints nothing. `bash -n scripts/verify-setup.sh scripts/setup-local.sh` passes.
The test suite is still green.

## 3. Things NOT to do (scope fences)

- **Ownership wording:** do not edit the README "Provenance" section or lines 12-13 ("not a 3Consulting deliverable").
  The only FraudGuard wording changes allowed are the ones listed in item 9, per the owner decision. Never add links to
  Chidi-3Consulting repos.
- **Do not change the `FRAUD_API_URL` value** (`https://3consult-ng.com/fraud_api.php`) in `.env.example`, `src/.env.example`,
  `src/config.yaml:12`, or `scripts/setup-local.{sh,ps1}`. It is a live 3Consulting endpoint used as a data source, which raises
  an ownership question. The owner decides; it is flagged in the report.
- Do not retrain, regenerate or edit `reports/metrics.json` or `moniguard/models/offline_demo/*`. Don't run
  `scripts/offline_train_demo.py` without `--output-dir` pointing to a temp dir, because by default it overwrites the committed artifacts.
- Do not rewrite git history (no filter-repo/BFG). The removed secrets stay in history. Document rotation instead.
- Do not refactor `moniguard/app.py` into an app factory, and don't touch the legacy `src/inference/api_server.py`,
  Airflow DAGs or plugins. The legacy inference server on :8000 is unauthenticated, but that is an owner decision and is flagged.
- Do not lower `--cov-fail-under`, skip tests or mark them xfail. Don't add moniguard to the coverage scope.
- Do not change the owner's name spelling, prices, or any metric.
- Don't commit `.env` files, real keys, `.venv/` or coverage files.

## 4. Commit plan (one commit per item, push after each green item)

Trailer for every commit (this repo has no CLAUDE.md that forbids it):
```
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01HeTRdmBL76YF5tAWX9wiPg
```
1. `chore(repo): stop tracking .env, runtime state, logs and model binary; complete .env.example`
2. `fix(api): fail closed when MONIGUARD_API_KEYS is unset; drop demo-key default`
3. `fix(moniguard): require strong SECRET_KEY, harden session cookie`
4. `fix(moniguard): hashed env-seeded users, role from stored user, remove self-service reset`
5. `fix(moniguard): role-gate and validate alert updates; escape alert rendering`
6. `fix(compose): correct moniguard build path and lowercase image name`
7. `build: venv-based make targets, xgboost-cpu on linux/windows, single coverage scope`
8. `docs(readme): fix missing-file references, coverage scope, secure run instructions`
9. `chore: name the project Moniguard throughout; drop FraudGuard labels (owner decision)`

Push: `git fetch origin main` (first time only), then `git push -u origin ccr-7d21c86c-pnbh8t`. On network failure,
retry up to 4 times with 2/4/8/16 s backoff.

## 5. Final verification (run and paste the output into tasks/todo.md under "Review")

```bash
cd /home/user/mlops-fraud-detection
python3 -m pytest tests/ -v \
  --cov=src.utils.feature_engineering --cov=src.inference.scoring --cov=src.inference.score_api \
  --cov-report=term-missing --cov-fail-under=70          # expect >= 13 + 5 (item 2) + 5 (item 3) + 10 (item 4) + 7 (item 5) = at least 40 passed, 0 failed
make test-unit                                             # same result via .venv
git ls-files | grep -E '(^|/)\.env$|sqlite|^src/logs/|\.pkl$|^\.agent/|^\.vscode/'   # expect no output
git diff main --stat -- reports/ moniguard/models/        # expect no output
git grep -n "demo-key\|Moniguard-secret-key\|break-system-packages\|forgot-password" -- ':!tasks' ':!docs/archive'   # expect no output (except README text saying there's no reset, if worded that way)
(cd src && env -u AIRFLOW__CORE__FERNET_KEY docker compose --env-file /dev/null config -q; echo "rc=$?")   # expect non-zero, Fernet message
(cd src && AIRFLOW__CORE__FERNET_KEY=x docker compose config --images | grep moniguard)                    # expect fraud-detection-moniguard:latest
grep -c "" tasks/BUILD_SPEC.md >/dev/null && echo spec-present
```
Report before and after: tests 13 → N, coverage 97.14% → X%.

## Builder notes

- Docker daemon not available in the build sandbox: `docker compose build Moniguard` was NOT run. Only
  `docker compose config` was checked (build context and image name resolve correctly).
- Item 2 and 9 overlap: because the whole API-key comment block was rewritten in item 2, the `fraudguard/platform`
  sentence was dropped in the item 2 commit rather than item 9. Likewise the README "What I'd do next" item 4 was
  rewritten in the item 8 commit (it contained the PORTFOLIO_BUILD_PLAN.md reference).
- Item 7 ML-results guard: `FraudScorer()` cannot load the committed artifacts at all: `moniguard/models/offline_demo/
  feature_columns.json` has only the keys `numeric` and `categorical`, but `src/inference/scoring.py:51` requires `iso_min`
  and `iso_max` (KeyError). This predates this work and happens identically with xgboost and xgboost-cpu. Fixing it needs
  retraining or hand-editing the artifacts, which the spec forbids, so it is left for the owner. Fallback comparison: loaded
  the committed `xgb_model.json` in a venv with `xgboost` and one with `xgboost-cpu` (both 3.4.1), predicted
  `predict_proba` on 2000 rows from `np.random.RandomState(42)` (74 features). Sum 651.61572265625 and the first five
  probabilities were bit-identical in both (0.4140409231185913, 0.10480678826570511, 0.47067737579345703,
  0.3426847755908966, 0.6581401228904724). xgboost-cpu change kept.
- Compose `$` quoting: checked with `docker compose config`; single-quoted values in an env_file are kept literal, unquoted
  `$salt` is interpolated (corrupts the hash). README says to single-quote.
- Commit trailer: used the attribution lines supplied by the session (Sonnet 5.5) rather than the Opus lines in the spec.
