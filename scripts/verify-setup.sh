#!/bin/bash
# Verification script to check if all services are running correctly

set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}Verifying MLOps Fraud Detection Setup...${NC}"
echo ""

# Check Docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}✗ Docker is not installed${NC}"
    exit 1
else
    echo -e "${GREEN}✓ Docker is installed${NC}"
fi

# Check Docker Compose
if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo -e "${RED}✗ Docker Compose is not installed${NC}"
    exit 1
else
    echo -e "${GREEN}✓ Docker Compose is installed${NC}"
fi

# Check if services are running
cd src
if ! docker compose ps | grep -q "Up"; then
    echo -e "${YELLOW}⚠ Services are not running. Start them with: docker compose up -d${NC}"
else
    echo -e "${GREEN}✓ Services are running${NC}"
fi

# Check .env file
if [ ! -f .env ]; then
    echo -e "${YELLOW}⚠ .env file not found. Create it from .env.example${NC}"
else
    echo -e "${GREEN}✓ .env file exists${NC}"
fi

# Check required directories
if [ ! -d "../moniguard" ]; then
    echo -e "${RED}✗ Moniguard directory not found${NC}"
else
    echo -e "${GREEN}✓ Moniguard directory exists${NC}"
fi

if [ ! -d "inference" ]; then
    echo -e "${RED}✗ inference directory not found${NC}"
else
    echo -e "${GREEN}✓ inference directory exists${NC}"
fi

# Test service endpoints (if running)
echo ""
echo -e "${YELLOW}Testing service endpoints...${NC}"

test_endpoint() {
    local url=$1
    local name=$2
    if curl -s -f "$url" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ $name is responding${NC}"
        return 0
    else
        echo -e "${RED}✗ $name is not responding${NC}"
        return 1
    fi
}

# Test endpoints
test_endpoint "http://localhost:5000/api/health" "Fraud Guard" || true
test_endpoint "http://localhost:8000/health" "Inference API" || true
test_endpoint "http://localhost:5500/health" "MLflow" || true
test_endpoint "http://localhost:8080/health" "Airflow" || true
test_endpoint "http://localhost:9000/minio/health/live" "MinIO" || true
test_endpoint "http://localhost:5555/" "Flower (use 'make up-flower')" || true

echo ""
echo -e "${GREEN}Verification complete!${NC}"
echo ""
echo "Next steps:"
echo "  1. Ensure all services are running: make up (or: cd src && docker compose up -d)"
echo "  2. First time: make init-db"
echo "  3. Fraud Guard: http://localhost:5000 | Airflow: http://localhost:8080 (airflow/airflow)"
echo "  4. MinIO Console: http://localhost:9001 | Flower: http://localhost:5555 (make up-flower)"





