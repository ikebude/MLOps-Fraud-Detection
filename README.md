# MLOps Fraud Detection – Local End-to-End Solution

A local MLOps stack for fraud detection: **Airflow** runs the training DAG, **MLflow** stores the model, **Inference** serves predictions on new records, and **Moniguard** shows metrics. All services run via Docker Compose on your machine.

## Overview

- **Airflow**: DAG `fraud_detection_training` collects data from the **PostgreSQL database (populated by Producer)**, trains an XGBoost model, and logs to MLflow.
- **MLflow**: Experiment tracking and model registry; artifacts in MinIO.
- **Inference**: Loads the model (from MLflow or local cache), runs on new records in DB, exposes REST API.
- **Moniguard**: Dashboard that displays real-time metrics and alerts from the database.

## Architecture

```
Transactions Producer → PostgreSQL (Live Data) → Airflow DAG → Training → MLflow (model)
                                           ↓              ↘
Moniguard UI ← PostgreSQL (Live Data) ← Inference API ←──────────┘
```

## Prerequisites

- Docker Desktop (Windows/Mac) or Docker Engine (Linux)
- Docker Compose v2+
- 8GB+ RAM for Docker
- Git

## Quick Start

1. **Setup**
   ```bash
   git clone <repo>
   cd MLOps_Fraud_Detection
   chmod +x scripts/setup-local.sh
   ./scripts/setup-local.sh
   ```
   On **Windows** (PowerShell): `.\scripts\setup-local.ps1` instead.

2. **Build and run**
   ```bash
   make build
   make up
   make init-db    # first time only
   ```
   **Windows (no `make`):** use `.\make.ps1` instead of `make`, e.g. `.\make.ps1 build`, `.\make.ps1 up`, `.\make.ps1 init-db`.

3. **Access**
   - **Moniguard**: http://localhost:5000  
   - **Airflow**: http://localhost:8080 (airflow / airflow)  
   - **MLflow**: http://localhost:5500  
   - **MinIO Console**: http://localhost:9001 (minioadmin / minioadmin)  
   - **MinIO API**: http://localhost:9000 (S3-compatible; used by MLflow)  
   - **Inference API**: http://localhost:8000  
   - **Flower** (Celery UI): http://localhost:5555 — start with `docker compose --profile flower up -d` (from `src/`).  

4. **Training**
   - Airflow UI → enable `fraud_detection_training` DAG → trigger a run.

5. **Inference & metrics**
   - Use “Run Inference” in Moniguard or `make inference`. Metrics appear in Moniguard.

## Project Structure

```
MLOps_Fraud_Detection/
├── Moniguard/           # Moniguard Flask app
│   ├── app.py
│   ├── Dockerfile
│   ├── templates/
│   └── static/
├── src/
│   ├── airflow/          # Airflow image & DAGs
│   ├── mlflow/           # MLflow server
│   ├── inference/        # Inference API
│   ├── dags/
│   ├── plugins/          # Training logic
│   ├── producer/         # Transaction Generator
│   ├── config.yaml
│   └── docker-compose.yml
├── scripts/
│   ├── setup-local.sh
│   ├── setup-local.ps1
│   ├── build-images.sh
│   └── verify-setup.sh
└── README.md
```

## Configuration

- **`src/.env`**: Copy from `src/.env.example`, adjust if needed.  
- **`src/config.yaml`**: MLflow, API, and model settings.  
- **Transactions Data**: The system uses a local producer sending data to PostgreSQL. No external API is required.

## End-to-end workflow (verified)

1. **Postgres** starts → **init-multiple-dbs** creates `mlflow` DB and user. **MinIO** starts → **mc** creates `mlflow` bucket.
2. **MLflow** starts → backend `mlflow` DB, artifacts `s3://mlflow/fraud_detection` (MinIO).
3. **Producer** starts → generates synthetic transactions and writes to `transactions` table in PostgreSQL.
4. **Airflow** (scheduler, workers, webserver) start → **fraud_detection_training** DAG is loaded.
5. **Training** (when DAG runs):
   - Reads `src/config.yaml` and `src/.env` (mounted at `/app`).
   - Fetches data from **PostgreSQL** (`transactions` table) → feature engineering → XGBoost + SMOTE → logs to **MLflow** (metrics, params, `fraud_detection_model`), writes artifacts to MinIO.
   - Saves `fraud_detection_model.pkl` to **`/app/models`** (mounted `src/models`).
6. **Inference** starts → loads model from **MLflow** first (`models:/fraud_detection_model/latest`), else from **`/app/models/fraud_detection_model.pkl`**.
7. **Run inference** (Moniguard “Run Inference” or `make inference`):
   - Fetches recent unscored transactions from **PostgreSQL** → same preprocessing/features as training → predictions → writes back to DB.
8. **Moniguard** → queries **PostgreSQL** directly for live transaction feed and real-time aggregations.

**Model**: `fraud_detection_model` everywhere (config, training, inference). **Data**: PostgreSQL `transactions` table is the single source of truth.

## Makefile Targets

| Target | Description |
|--------|-------------|
| `make setup` | Run setup-local.sh |
| `make build` | Build all images |
| `make up` | Start stack |
| `make up-flower` | Start stack + Flower (Celery UI on :5555) |
| `make down` | Stop stack |
| `make init-db` | Initialize Airflow DB (first run) |
| `make train` | Trigger training DAG |
| `make inference` | POST /inference/run (1000 records) |
| `make stats` | GET /inference/stats |
| `make test` | Health checks (Moniguard, Inference, MLflow, Airflow, MinIO, Flower) |

## Local endpoints summary

| Service | URL | Notes |
|--------|-----|-------|
| Moniguard | http://localhost:5000 | Dashboard |
| Airflow | http://localhost:8080 | airflow / airflow |
| MLflow | http://localhost:5500 | |
| MinIO Console | http://localhost:9001 | minioadmin / minioadmin |
| MinIO API | http://localhost:9000 | S3-compatible |
| Inference API | http://localhost:8000 | |
| Flower (Celery) | http://localhost:5555 | `--profile flower` |

## Troubleshooting

- **Services not up**: `make logs` or `cd src && docker compose logs -f`
- **Out of memory**: Lower training batch size (`Airflow Variable: training_batch_size`) or `XGB_N_JOBS=1` in `src/.env`
- **Port in use**: Change port mappings in `src/docker-compose.yml`

## API (Inference, port 8000)

- `GET /health` – Health check  
- `POST /inference/run` – Run inference (JSON: `max_records`, etc.)  
- `GET /inference/results` – Latest results  
- `GET /inference/stats` – Cumulative stats (used by Moniguard)

---

**Local only.** No cloud or Kubernetes; everything runs via Docker Compose.





