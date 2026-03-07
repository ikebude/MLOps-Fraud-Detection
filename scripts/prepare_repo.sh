#!/usr/bin/env bash
set -euo pipefail

# Prepare repository for building Docker images
# - Normalize line endings
# - Ensure executable bits on shell scripts
# - Print checklist and next steps

echo "[repo] Normalizing line endings..."
./scripts/normalize-line-endings.sh

echo "[repo] Ensuring execute permission on scripts..."
chmod +x scripts/*.sh || true

cat <<'MSG'

Repository prepared for build.
Next steps:
  1) Review/adjust .env values (copy .env.example -> .env)
  2) Run: cd src && docker compose build
  3) Start minimal stack for DB and infra: cd src && docker compose up -d postgres redis minio mlflow
  4) Start Airflow (scheduler & workers): cd src && docker compose up -d airflow-scheduler airflow-worker airflow-webserver
  5) Start optional services as profiles:
       - Flower: cd src && docker compose --profile flower up -d
       - Producer (standalone): cd src && docker compose --profile producer up -d producer

Notes:
  - Avoid running `docker compose down -v` unless you intend to wipe DB data.
  - Use scripts/backfill_transactions.py to fill the transactions DB for tests.

MSG





