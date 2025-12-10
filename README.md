# MLOps_Fraud_Detection

This repository contains a production-grade fraud detection MLOps example. By default the
training pipeline accepted Kafka as the ingestion source. The project has been adapted to also
support API-based ingestion from an HTTP endpoint specified by the `FRAUD_API_URL` environment
variable.

Notes: API-based ingestion

- To run the training pipeline using the HTTP API (instead of Kafka) set `FRAUD_API_URL` in
	`src/.env` (or the runtime environment). Example:

	FRAUD_API_URL=https://3consult-ng.com/fraud_api.php

- To limit the number of records pulled into the training pipeline (to avoid filling Postgres and OOM in Airflow),
  set `FRAUD_API_MAX_RECORDS` (default: 150000). The DAG will stop ingestion once this cap is reached and will
  retain the most recent records by timestamp when possible.

  FRAUD_API_MAX_RECORDS=150000  # 150k records (default, requires 4GB worker RAM)- The DAG `src/dags/fraud_detection_training.py` will page through the API using offset/limit
	parameters and build a pandas DataFrame for training and feature engineering.

- The `producer/` component (which reads from the API and writes to Kafka) is intentionally
	left unchanged.

## Memory & Resource Configuration

The training pipeline is now tuned for **4GB+ Docker Desktop/worker memory** to safely train on **150,000 fraud records**.

### Current defaults

- **Airflow Worker**: 4GB limit (3GB reserved) — processes training tasks
- **Airflow Webserver**: 3GB limit (2GB reserved) — UI and DAG parsing
- **Airflow Scheduler**: 3GB limit (2GB reserved) — schedule management
- **Training data cap**: 150k records (comprehensive, requires 4GB worker)
- **Task timeout**: 30 minutes (fraud detection training takes ~5-10 min on 150k records)

### Adjusting for different dataset sizes

If you want fewer records (faster training, less memory), edit `.env`:

```
FRAUD_API_MAX_RECORDS=50000   # ~1GB peak, 2 min training, fits 2GB workers
FRAUD_API_MAX_RECORDS=100000  # ~2GB peak, 4 min training, fits 3GB workers
FRAUD_API_MAX_RECORDS=150000  # ~3GB peak, 8 min training, requires 4GB+ workers
```

If you see "killed" (return code -9) or "OOM" errors:
1. Reduce `FRAUD_API_MAX_RECORDS` in `.env`, or
2. Increase worker memory in `docker-compose.yml`:
   ```yaml
   airflow-worker:
     deploy:
       resources:
         limits:
           memory: 6G    # or 8G for very large datasets
         reservations:
           memory: 5G
   ```
3. Restart: `docker compose up -d airflow-worker --remove-orphans`

# MLOps_Fraud_Detection

