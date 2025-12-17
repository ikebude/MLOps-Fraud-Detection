#!/bin/bash
# Docker Network Diagnostics Script
# Helps troubleshoot DNS and networking issues in Docker Compose environment

set -e

echo "=== Docker Network Diagnostics ==="
echo ""

# Check if Docker is running
if ! docker ps > /dev/null 2>&1; then
    echo "ERROR: Docker is not running or not accessible"
    exit 1
fi

echo "1. Checking Docker Networks:"
docker network ls | grep fraud-detection || echo "WARNING: fraud-detection network not found"
echo ""

echo "2. Inspecting fraud-detection network:"
if docker network inspect fraud-detection > /dev/null 2>&1; then
    docker network inspect fraud-detection | grep -A 20 "Containers"
    echo ""
else
    echo "ERROR: fraud-detection network not found"
fi

echo "3. Testing connectivity to postgres service:"
docker run --rm --network fraud-detection alpine ping -c 3 postgres 2>/dev/null && \
    echo "✓ postgres is reachable" || \
    echo "✗ postgres is NOT reachable"
echo ""

echo "4. Testing connectivity to redis service:"
docker run --rm --network fraud-detection alpine ping -c 3 redis 2>/dev/null && \
    echo "✓ redis is reachable" || \
    echo "✗ redis is NOT reachable"
echo ""

echo "5. Testing DNS resolution inside container:"
docker run --rm --network fraud-detection alpine nslookup postgres 2>/dev/null && \
    echo "✓ DNS resolution for 'postgres' works" || \
    echo "✗ DNS resolution for 'postgres' FAILED"
echo ""

echo "6. Testing external DNS resolution:"
docker run --rm --network fraud-detection alpine nslookup 8.8.8.8 2>/dev/null && \
    echo "✓ External DNS reachable" || \
    echo "✗ External DNS NOT reachable"
echo ""

echo "7. Checking running containers:"
docker ps --format "table {{.Names}}\t{{.Status}}" | grep -E "postgres|redis|airflow" || \
    echo "WARNING: Some expected containers not running"
echo ""

echo "8. Container logs summary:"
echo "Checking for connectivity/DNS errors in logs..."
for service in postgres redis airflow-scheduler airflow-worker; do
    if docker ps --all | grep -q "$service"; then
        echo "  $service:"
        docker logs "$service" 2>&1 | grep -i "connection\|dns\|resolve" | head -2 || echo "    No obvious connection/DNS errors"
    fi
done
echo ""

echo "=== Diagnostics Complete ==="
echo ""
echo "Recommendations if tests fail:"
echo "1. Ensure docker-compose.yml has proper DNS settings (8.8.8.8, 1.1.1.1)"
echo "2. Restart the docker-compose stack: docker-compose down && docker-compose up -d"
echo "3. Check Docker daemon DNS settings: docker info | grep DNS"
echo "4. Verify network bridge driver is not broken: docker network prune"
echo "5. Check host network connectivity: ping 8.8.8.8"
