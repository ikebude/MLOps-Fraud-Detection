# TEST_PLAN — fraud workstream (independent verification by the tester)

Don't rely on the builder's report. Run everything below yourself on branch `ccr-7d21c86c-pnbh8t`,
then add your own adversarial checks. Baseline to compare against: **13 passed, TOTAL coverage 97.14%**
(score_api 92%, scoring 99%, feature_engineering 99%) at `f0845a5`, about 190 s.

Use a venv. The CI path is `pip install -r requirements-demo.txt pytest pytest-cov httpx`. Run Python with `-I`
when importing from an untrusted directory.

## 1. Suite, coverage and build commands

| # | Command | Expected |
|---|---|---|
| 1.1 | `python -m pytest tests/ -v --cov=src.utils.feature_engineering --cov=src.inference.scoring --cov=src.inference.score_api --cov-report=term-missing --cov-fail-under=70` | ≥ 40 passed, 0 failed/skipped/xfail. TOTAL ≥ 97%. |
| 1.2 | `make test-unit` (fresh clone, no `.venv`) | Creates `.venv`, same pass count and same coverage flags as 1.1. No sudo, no `--break-system-packages`. |
| 1.3 | `diff <(grep -o -- '--cov[^ \\]*' Makefile \| sort) <(grep -o -- '--cov[^ \\]*' .github/workflows/ci.yml \| sort)` | No diff: CI and make measure the same scope. |
| 1.4 | `git grep -n -- "--break-system-packages"` | No output. |
| 1.5 | `grep -n "xgboost" requirements-demo.txt` | `xgboost-cpu` with `sys_platform != "darwin"` and `xgboost` with `== "darwin"`. Mutually exclusive markers. |
| 1.6 | `pip install --dry-run --report - -r requirements-demo.txt` on linux | Resolves. No `nvidia-nccl-cu12` in the install set. |
| 1.7 | `git diff main --stat -- reports/ moniguard/models/` | Empty. The ML artifacts and metrics are untouched. |
| 1.8 | ML-equivalence: score 5 seeded `TransactionGenerator` transactions with `FraudScorer()` (committed artifacts) under `xgboost-cpu`, and in a second venv under `xgboost` | Identical `score`/`probability`. Compare against the builder's pasted numbers. |
| 1.9 | `time python -m pytest tests/test_moniguard_auth.py -q` | Passes in < 30 s. Must not depend on the `tiny_model_dir` fixture. |

## 2. Security reproducer (all of these succeeded at baseline; all must fail now)

Run this from a scratch dir (not inside the repo), with the dashboard env set:
`SECRET_KEY=$(python -c "import secrets;print(secrets.token_hex(32))") MONIGUARD_ADMIN_PASSWORD=admin-pass-123456 MONIGUARD_ANALYST_PASSWORD=analyst-pass-1234 MONIGUARD_EXEC_PASSWORD=exec-pass-1234567 MONIGUARD_OPS_PASSWORD=ops-pass-12345678 DB_HOST=127.0.0.1 DB_PORT=9 INFERENCE_SERVICE_URL=http://127.0.0.1:9`

```python
import sys; sys.path.insert(0, '/home/user/mlops-fraud-detection/moniguard')
import app as m
c = m.app.test_client()
r = c.post('/login', data={'username':'Analyst User','password':'analyst-pass-1234','role':'admin'})
print('A1 role escalation', r.headers.get('Location'), c.get('/admin').status_code)      # expect Location '/', /admin -> 302 (not 200)
c2 = m.app.test_client()
print('A2 reset', c2.post('/forgot-password', data={'name':'Admin User','new_password':'pwned'}).status_code)  # expect 302 to /login
print('A2b', c2.post('/login', data={'username':'Admin User','password':'pwned'}).status_code)                # expect 401
c3 = m.app.test_client(); c3.post('/login', data={'username':'Ops User','password':'ops-pass-12345678'})
body = c3.get('/alerts').data
print('A3 leak', any(x in body for x in [b'scrypt:', b'pbkdf2:', b'password_hash', b'ops-pass']))             # expect False
c4 = m.app.test_client(); c4.post('/login', data={'username':'Exec User','password':'exec-pass-1234567'})
print('A4 exec POST', c4.post('/api/alerts/ALT-X1', json={'status':'Under Review'}).status_code)                 # expect 403
c5 = m.app.test_client(); c5.post('/login', data={'username':'Analyst User','password':'analyst-pass-1234'})
print('A5 xss status', c5.post('/api/alerts/ALT-X1', json={'status':'<img src=x onerror=alert(1)>'}).status_code)  # expect 400
print('A6 secret', m.app.secret_key != 'Moniguard-secret-key-change-in-production')                              # expect True
```

More adversarial checks:
- **Forged session.** Use `itsdangerous`/`flask.sessions.SecureCookieSessionInterface` with the *old* default secret to sign `{'username':'Admin User','role':'admin'}`, send it as the `session` cookie, then `GET /admin`. Expect 302 to `/login`, not 200.
- **Missing or weak secret.** Run `env -u SECRET_KEY -u MONIGUARD_DEV_MODE python -c "import app"` in `moniguard/` and expect a non-zero exit with a SECRET_KEY message. Also try `SECRET_KEY=short` and `SECRET_KEY=Moniguard-secret-key-change-in-production`, which must both fail. With `MONIGUARD_DEV_MODE=true` it starts and logs a warning. Check that the app doesn't pick up a developer `.env` silently in the tests (the tests patch `dotenv.load_dotenv`).
- **Login edge cases.** Try an empty password, an unknown user, a username with trailing space, `role=` missing, and a very long password (10 kB). All must give 401 or a redirect, never a 500. Also check timing: unknown user vs known user with a wrong password should be within the same order of magnitude (dummy hash).
- **Disabled account.** With `MONIGUARD_EXEC_PASSWORD` unset, logging in as Exec User with an empty password or any password gives 401.
- **Pre-hashed env value.** A `generate_password_hash(...)` value in the env logs in with its plaintext. The hash string itself as the password is rejected.
- **CLI reset.** `flask --app moniguard/app.py hash-password` with mismatched or short input fails, and a valid input prints a hash that `check_password_hash` accepts. Check the README's quoting advice for `$` in `src/.env`: put a hash in a temp `src/.env`, run `docker compose config`, and confirm the Moniguard service gets the exact hash, not one mangled by interpolation.
- **Cookie flags.** `Set-Cookie` on login contains `HttpOnly` and `SameSite=Lax`. With `MONIGUARD_SECURE_COOKIES=true` it also contains `Secure`.
- **Alert API fuzz.** For `alert_id`, try `ALT-<script>`, `../../etc`, 200 characters, unicode, and an empty string. For status, try `null`, a number, a list, and `"new"` (wrong case). For `assigned_to`, try `"Admin User<script>"` and `123`. Expect 400 or 404, never 500, and nothing stored in `_alerts_store`. Also check that the store is bounded (the `_MAX_ALERT_STATE` behaviour is the one documented).
- **XSS rendering.** In `alerts.html`, every `${...}` that interpolates alert or transaction data inside an HTML string is wrapped in `esc()`. Grep: `grep -n '\${a\.\|\${txn\|\${u}' moniguard/templates/alerts.html`. Manually inject a merchant name `<img src=x onerror=alert(1)>` into `_build_alert_from_transaction` output (monkeypatch `get_live_fraud_feed`) and confirm that the rendered page source, as JS would build it, is escaped. A headless browser is better if one is available.
- **Scoring API.** Check the following:
  - With `MONIGUARD_API_KEYS` unset, `POST /v1/score` and `/v1/labels` with `X-API-Key: demo-key` give **503**.
  - With `MONIGUARD_API_KEYS=" , "`, both give 503.
  - With `MONIGUARD_API_KEYS=test-key`, `demo-key` gives 401.
  - A 64-hex sha256 configured value is accepted for its preimage, and the hash itself is rejected.
  - `/health` stays 200 without a key.
  - `curl` against a live `uvicorn` gives the same results as the test client.
- **Secrets in git.** Run `git ls-files | grep -E '(^|/)\.env$|sqlite|^src/logs/|\.pkl$|^\.agent/|^\.vscode/'` and expect nothing. Then run `git grep -nE "minioadmin|airflow/airflow|dGVzdF9rZXlfZm9yX2RldmVsb3BtZW50X29ubHk|Moniguard-secret-key" -- ':!tasks'`. Expect hits only in documentation that names a default to rotate, and **no** secret values in `.env.example`. If one of these is an accepted placeholder, note it. `.env.example` secret keys (`SECRET_KEY`, `AIRFLOW__CORE__FERNET_KEY`, `MONIGUARD_API_KEYS`, `MONIGUARD_*_PASSWORD`) are empty.
- **.env.example completeness.** Use variable names only, never print values: `comm -23 <(grep -oE '^[A-Z_][A-Z0-9_]*' .env | sort -u) <(grep -oE '^[A-Z_][A-Z0-9_]*' .env.example | sort -u)` is empty. Do the same for `src/`. Every `os.getenv("X")` / `${X}` added by this work appears in an example file: `git diff main -U0 | grep -oE 'getenv\(.[A-Z_]+' | sort -u`.
- **Compose.**
  - `cd src && env -u AIRFLOW__CORE__FERNET_KEY docker compose --env-file /dev/null config -q` fails with the Fernet message.
  - `AIRFLOW__CORE__FERNET_KEY=x docker compose config` shows the Moniguard build context `…/moniguard`, mounts from `../moniguard/…`, and `docker compose config --images` lists `fraud-detection-moniguard:latest`.
  - If a daemon is available, run `docker compose build Moniguard`, then `docker run --rm -e SECRET_KEY= fraud-detection-moniguard:latest` exits non-zero quickly.
- **Runtime-junk regeneration.** `src/models/.gitkeep` and `src/state/.gitkeep` are tracked. `make train` is documented as the way to regenerate `src/models/fraud_detection_model.pkl`. Confirm the bind mounts (`src/docker-compose.yml:66,337`) still point there.

## 3. Scope-fence checks (FAIL if violated)

- `git diff main -- README.md` doesn't touch the "Provenance" section or lines 12-13 (the ownership wording). `git diff main | grep -i "3consult\|fraudguard"` shows only unchanged context lines, or none.
- `FRAUD_API_URL` values are unchanged everywhere: `git diff main | grep FRAUD_API_URL` is empty.
- `score_api.py`'s `fraudguard/platform` comment is still present.
- No history rewrite: `git log --oneline main..HEAD` is linear, and the planner commit plus the builder's commits are on top of `f0845a5`.
- `--cov-fail-under=70` is unchanged, with no `skip`/`xfail` added: `git diff main -- tests | grep -n "skip\|xfail"` is empty.
- The owner's name is spelled "Precious Ikebude" (unchanged).

## 4. UI screenshots (the dashboard has a UI)

If a headless browser (Playwright/Chromium) is available, run the dashboard:
`cd moniguard && SECRET_KEY=… MONIGUARD_ADMIN_PASSWORD=… DB_HOST=127.0.0.1 DB_PORT=9 python app.py`.
Take screenshots of `/login`, `/alerts` (as analyst) and `/admin` (as admin) at **390×844 and 1280×800**, in
**light and dark** (`prefers-color-scheme`, `emulate_media(color_scheme=...)`). Check that:
- the role dropdown and the Forgot Password link are gone;
- the "ask an administrator" line is present;
- nothing overflows horizontally at 390 px;
- the alerts page still renders, including its empty state with no DB.

The app may not implement a dark theme. If so, note "no dark theme (pre-existing)" rather than failing. If no
browser is available, state that, and fall back to an HTML assertion on the rendered templates.

## 5. Broken-link and missing-reference scan

```bash
python3 - <<'EOF'
import re, pathlib, subprocess
root = pathlib.Path('/home/user/mlops-fraud-detection')
tracked = set(subprocess.check_output(['git','ls-files'], cwd=root, text=True).split('\n'))
for md in [p for p in tracked if p.endswith('.md') and not p.startswith('src/logs')]:
    text = (root/md).read_text(errors='ignore')
    for link in re.findall(r'\]\(([^)#\s]+)', text):
        if link.startswith(('http://','https://','mailto:')): continue
        target = (root/md).parent / link
        if not target.exists(): print('BROKEN', md, link)
    for name in re.findall(r'`([A-Za-z0-9_./-]+\.md)`', text):
        if not any(t.endswith(name) for t in tracked) and 'archive' not in md: print('MISSING-REF', md, name)
EOF
```
Expected: no `BROKEN` lines, and no `MISSING-REF` lines for README.md. In particular, `PRODUCT_SPECS.md` and
`PORTFOLIO_BUILD_PLAN.md` are no longer referenced as if they were in the repo. Also check the README's in-page
anchors (`#results`, `#provenance`, `#what-id-do-next`, and any new section anchor) against the headings. External
links: the CI badge URL points at `ikebude/mlops-fraud-detection`. Don't add new external URLs. `cloud-init.yaml:20`
clones `github.com/your-repo/MLOps_Fraud_Detection.git`, a placeholder that is still broken. That is an owner
decision, so report it rather than failing.

## 6. README claim → evidence table

| README claim | Evidence (must match exactly) |
|---|---|
| PR-AUC 0.877 (95% CI 0.845–0.905) | `reports/metrics.json` `metrics.pr_auc.value` 0.87661…, ci95 [0.8452…, 0.9046…] |
| ROC-AUC 0.943 (0.927–0.958) | `metrics.roc_auc` 0.94254…, [0.92695…, 0.95759…] |
| Recall @1% 0.377, @5% 0.892 | `recall_at_1pct_alert_rate` 0.37711…, `recall_at_5pct_alert_rate` 0.89194… |
| p95 latency 47.9 ms | `p95_scoring_latency_ms` 47.8608… |
| 60,000 txns / 180 days; train 42,000 (2.68%), test 18,000 (2.62%) | `dataset.*` in metrics.json |
| 74 shared features | `model.n_features` 74, and `moniguard/models/offline_demo/feature_columns.json` length |
| "NN% line coverage of [3 modules]" | Floor of TOTAL from 1.1. The module list matches `--cov` flags exactly. |
| ~2.8% base fraud rate in generator | `producer/main.py` generator config (verify the constant) |
| "API refuses requests without configured keys" | §2 scoring API checks |
| "no self-service password reset" / login instructions | §2 A2, CLI reset check |
| "Defaults that must be rotated" table | Every name listed appears in the git history of `.env`/`src/.env`/compose defaults (`git show main:src/docker-compose.yml \| grep ':-'`), and no values are printed |

Any README number without a row here: trace it, or flag it.

## 7. Verdict format

PASS / PASS-WITH-NOTES / FAIL, with evidence: commands, counts, and before→after (13 → N tests, 97.14% → X%).
Fix small defects directly (commit `fix: …`). Write large ones below with file:line and severity.

## Tester findings

(empty)
