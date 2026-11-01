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
    if [ ! -f src/.env.example ]; then
        echo -e "${YELLOW}src/.env.example not found; restore it from git (git checkout -- src/.env.example).${NC}"
        exit 1
    fi
    cp src/.env.example src/.env
    echo -e "${GREEN}src/.env created. Replace every change-me value with your own secret before 'make up'.${NC}"
else
    echo -e "${GREEN}.env file already exists.${NC}"
fi

# Create necessary directories
echo -e "${YELLOW}Creating necessary directories...${NC}"
mkdir -p src/models
mkdir -p src/logs
mkdir -p src/state
mkdir -p src/config
mkdir -p moniguard/data
mkdir -p moniguard/static

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

echo -e "${GREEN}Local setup complete!${NC}"
echo -e "${YELLOW}Next steps:${NC}"
echo "  1. (Optional) Review src/.env"
echo "  2. make build   # or: cd src && docker compose build"
echo "  3. make up     # or: cd src && docker compose up -d"
echo "  4. make init-db   # first time only"
echo "  5. Open Airflow http://localhost:8080 (user and password from src/.env), enable fraud_detection_training DAG"
echo "  6. Open Moniguard http://localhost:5000"





