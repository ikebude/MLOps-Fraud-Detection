#!/usr/bin/env bash
# Build all Docker images locally (no cloud). Run from project root.
set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo -e "${GREEN}Building all Docker images (local only)...${NC}"

echo -e "${YELLOW}Building via docker compose...${NC}"
cd src
docker compose build
cd ..

echo -e "${GREEN}All images built. Start with: make up${NC}"
