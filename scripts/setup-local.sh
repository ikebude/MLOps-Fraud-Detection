#!/bin/bash
# Setup script for local development
# This script prepares the environment for local development

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Setting up local development environment...${NC}"

# Check if .env file exists
if [ ! -f src/.env ]; then
    echo -e "${YELLOW}Creating .env file from .env.example...${NC}"
    if [ -f .env.example ]; then
        cp .env.example src/.env
        echo -e "${GREEN}.env file created. Please update it with your values.${NC}"
    else
        echo -e "${YELLOW}.env.example not found. Creating basic .env file...${NC}"
        cat > src/.env << EOF
# Airflow Configuration
AIRFLOW_UID=50000
POSTGRES_USER=airflow
POSTGRES_PASSWORD=airflow
POSTGRES_DB=airflow

# MLflow Configuration
MLFLOW_TRACKING_URI=http://mlflow-server:5500
MLFLOW_S3_ENDPOINT_URL=http://minio:9000

# MinIO Configuration
MINIO_USERNAME=minioadmin
MINIO_PASSWORD=minioadmin
AWS_ACCESS_KEY_ID=minioadmin
AWS_SECRET_ACCESS_KEY=minioadmin

# Fraud Detection API
FRAUD_API_URL=https://3consult-ng.com/fraud_api.php
FRAUD_API_MAX_RECORDS=100000

# Inference Service
INFERENCE_PORT=8000
INFERENCE_SERVICE_URL=http://inference:8000

# Fraud Guard
FLASK_DEBUG=False
EOF
    fi
else
    echo -e "${GREEN}.env file already exists.${NC}"
fi

# Create necessary directories
echo -e "${YELLOW}Creating necessary directories...${NC}"
mkdir -p src/models
mkdir -p src/logs
mkdir -p src/state
mkdir -p fraudguard/data

# Set proper permissions
echo -e "${YELLOW}Setting permissions...${NC}"
chmod -R 755 src/logs
chmod -R 755 src/models

# Check Docker
if ! command -v docker &> /dev/null; then
    echo -e "${YELLOW}Docker is not installed. Please install Docker Desktop.${NC}"
    exit 1
fi

# Check Docker Compose
if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo -e "${YELLOW}Docker Compose is not installed. Please install Docker Compose.${NC}"
    exit 1
fi

echo -e "${GREEN}Local development environment setup complete!${NC}"
echo -e "${YELLOW}Next steps:${NC}"
echo "  1. Review and update src/.env with your configuration"
echo "  2. Run: cd src && docker compose build"
echo "  3. Run: docker compose up -d"
