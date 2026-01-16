#!/bin/bash
# Build all Docker images locally
# Usage: ./scripts/build-images.sh

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
ACR_REGISTRY=${ACR_REGISTRY:-mlopsacr12345.azurecr.io}
IMAGE_PREFIX=${IMAGE_PREFIX:-fraud-detection}

echo -e "${GREEN}Building all Docker images...${NC}"

# Build Airflow image
echo -e "${YELLOW}Building Airflow image...${NC}"
cd src/airflow
docker build -t ${ACR_REGISTRY}/${IMAGE_PREFIX}/airflow:latest .
cd ../..

# Build MLflow image
echo -e "${YELLOW}Building MLflow image...${NC}"
cd src/mlflow
docker build -t ${ACR_REGISTRY}/${IMAGE_PREFIX}/mlflow:latest .
cd ../..

# Build Inference image
echo -e "${YELLOW}Building Inference image...${NC}"
cd src/inference
docker build -t ${ACR_REGISTRY}/${IMAGE_PREFIX}/inference:latest .
cd ../..

# Build Fraud Guard image
echo -e "${YELLOW}Building Fraud Guard image...${NC}"
cd fraudguard
docker build -t ${ACR_REGISTRY}/${IMAGE_PREFIX}/fraudguard:latest .
cd ..

echo -e "${GREEN}All images built successfully!${NC}"
echo -e "${YELLOW}To view images:${NC}"
echo "  docker images | grep ${IMAGE_PREFIX}"
