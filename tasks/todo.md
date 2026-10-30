# Build checklist (BUILD_SPEC.md)

- [x] Item 1: untrack secrets/runtime state, complete .env.example, Fernet key required
- [x] Item 2: scoring API fails closed
- [x] Item 3: strong SECRET_KEY + cookie hardening
- [x] Item 4: hashed env users, role from stored user, remove self-service reset
- [x] Item 5: role-gate and validate alert updates
- [x] Item 6: compose build path / lowercase image
- [x] Item 7: venv make targets, xgboost-cpu, single coverage scope
- [x] Item 8: README/docs truthfulness
- [x] Item 9: Moniguard-only naming

## Review

Final verification (2026-10-30), run with Python 3.13.17:

- CI command and `make test-unit` (fresh `.venv`, no `--break-system-packages`): **41 passed**, 1 warning, 0 failed
  (baseline 13). Coverage TOTAL **97.64%** (baseline 97.14%): score_api.py 94%, scoring.py 99%, feature_engineering.py 99%.
- Untracked-file check, `git diff main -- reports/ moniguard/models/`, FraudGuard-name grep (only README Provenance lines 19, 21):
  all as the spec expects.
- `git grep "demo-key|Moniguard-secret-key|forgot-password"` now only matches the legacy-default constant that is
  rejected at startup (`moniguard/app.py`) and negative tests.
- Compose: without `AIRFLOW__CORE__FERNET_KEY`, `docker compose config -q` fails with the Set-the-key message (rc=1);
  with it, `config --images` lists `fraud-detection-moniguard:latest`, build context `.../moniguard`.
- README relative-link scan: 0 broken links.
