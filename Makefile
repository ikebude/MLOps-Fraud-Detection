.PHONY: help setup build up down logs clean test

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Available targets:'
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-15s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

setup: ## Run local setup script
	@chmod +x scripts/setup-local.sh
	@./scripts/setup-local.sh

prepare: ## Prepare repository for build (normalize line endings, mark scripts)
	@chmod +x scripts/prepare_repo.sh scripts/normalize-line-endings.sh
	@./scripts/prepare_repo.sh

backfill: ## Backfill transactions DB (usage: make backfill ROWS=150000)
	@python scripts/backfill_transactions.py --rows ${ROWS:-150000}

build: ## Build all Docker images
	@cd src && docker compose build

build-fast: ## Build Docker images without cache
	@cd src && docker compose build --no-cache

up: ## Start all services
	@cd src && docker compose up -d

up-flower: ## Start all services including Flower (Celery UI)
	@cd src && docker compose --profile flower up -d

up-logs: ## Start all services and show logs
	@cd src && docker compose up

down: ## Stop all services
	@cd src && docker compose down

down-volumes: ## Stop all services and remove volumes
	@cd src && docker compose down -v

logs: ## Show logs for all services
	@cd src && docker compose logs -f

logs-service: ## Show logs for a specific service (usage: make logs-service SERVICE=inference)
	@cd src && docker compose logs -f $(SERVICE)

ps: ## Show status of all services
	@cd src && docker compose ps

restart: ## Restart all services
	@cd src && docker compose restart

restart-service: ## Restart a specific service (usage: make restart-service SERVICE=inference)
	@cd src && docker compose restart $(SERVICE)

clean: ## Remove all containers, networks, and images
	@cd src && docker compose down -v --rmi all

test: ## Run health checks on all services
	@echo "Testing service health..."
	@curl -s http://localhost:5000/api/health | python -m json.tool || echo "Fraud Guard: Not responding"
	@curl -s http://localhost:8000/health | python -m json.tool || echo "Inference: Not responding"
	@curl -s http://localhost:5500/health | python -m json.tool || echo "MLflow: Not responding"
	@curl -s http://localhost:8080/health | python -m json.tool || echo "Airflow: Not responding"
	@curl -sf http://localhost:9000/minio/health/live >/dev/null && echo "MinIO: OK" || echo "MinIO: Not responding (optional)"
	@curl -sf http://localhost:5555/ >/dev/null && echo "Flower: OK" || echo "Flower: Not responding (use 'make up-flower' to enable)"

build-images: ## Build all images locally (no cloud)
	@chmod +x scripts/build-images.sh 2>/dev/null || true
	@./scripts/build-images.sh

init-db: ## Initialize Airflow database
	@cd src && docker compose up airflow-init

train: ## Trigger training DAG in Airflow
	@echo "Triggering fraud_detection_training DAG..."
	@cd src && docker compose exec airflow-webserver airflow dags trigger fraud_detection_training

inference: ## Run inference via API
	@curl -X POST http://localhost:8000/inference/run \
		-H "Content-Type: application/json" \
		-d '{"max_records": 1000}'

results: ## Get inference results
	@curl http://localhost:8000/inference/results | python -m json.tool

stats: ## Get inference statistics
	@curl http://localhost:8000/inference/stats | python -m json.tool





