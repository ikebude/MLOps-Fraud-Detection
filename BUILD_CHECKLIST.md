# Build Checklist

This repository has a multi-service Docker Compose stack. Follow these steps to get a clean, repeatable build and start:

1. Prepare repo
   - Normalize line endings and mark scripts executable:
     - ./scripts/prepare_repo.sh

2. Set your environment
   - Copy `.env.example` -> `.env` at repo root and fill in credentials.
   - Do not overwrite existing volumes unless you intend to wipe data.

3. Build images
   - cd src
   - docker compose build

4. Start core infrastructure
   - docker compose up -d postgres redis minio mlflow

5. Start Airflow
   - docker compose up -d airflow-init
   - docker compose up -d airflow-scheduler airflow-worker airflow-webserver

6. Optional services (profiles - start only when you need them)
   - Producer (standalone): docker compose --profile producer up -d producer
   - Flower (Celery UI): docker compose --profile flower up -d

7. Populate / backfill data (if you need N rows immediately)
   - Quick SQL backfill or use provided helper:
     - python scripts/backfill_transactions.py --rows 150000

8. Trigger training DAG
   - docker compose exec src-airflow-scheduler-1 /bin/bash -lc "airflow dags trigger fraud_detection_training"

Notes
 - Avoid running `docker compose down -v` unless you want to delete persistent DB state.
 - The producer is intentionally profile-scoped and standalone so you can choose when to generate data.
 - Airflow connects to `transactions_db` (seen by env TRANSACTIONS_*) and will read data after the producer writes it.
