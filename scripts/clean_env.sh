#!/usr/bin/env bash
set -euo pipefail

# Safe clean script for docker compose environment.
# By default this stops containers but does NOT remove volumes.
# Use -v to remove volumes and -i to remove images.

REMOVE_VOLUMES=false
REMOVE_IMAGES=false

while getopts "vi" opt; do
  case $opt in
    v) REMOVE_VOLUMES=true ;;
    i) REMOVE_IMAGES=true ;;
    *) echo "Usage: $0 [-v] [-i]"; exit 1 ;;
  esac
done

echo "Stopping containers..."
cd src && docker compose down

if [ "$REMOVE_VOLUMES" = true ]; then
  echo "Removing volumes (this WILL delete Postgres data)..."
  cd src && docker compose down -v
fi

if [ "$REMOVE_IMAGES" = true ]; then
  echo "Removing images (rmi all)..."
  cd src && docker compose down -v --rmi all
fi

echo "Clean complete."
