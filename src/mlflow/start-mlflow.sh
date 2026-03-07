#!/usr/bin/env bash
# POSIX-safe strict mode; enable 'pipefail' only when running under bash
set -eu
if [ -n "${BASH_VERSION-}" ]; then
  set -o pipefail
fi

echo "Resetting MLflow database to fix migration issues..."
PGPASSWORD="${MLFLOW_DB_PASSWORD:-mlflow}"
DB_NAME="${MLFLOW_DB_NAME:-mlflow}"
DB_USER="${MLFLOW_DB_USER:-mlflow}"

export PGPASSWORD
export DB_NAME
export DB_USER

# Wait for PostgreSQL to be ready
echo "Waiting for PostgreSQL to be ready..."
until pg_isready -h postgres -p 5432 -U "$DB_USER"; do
  echo "Waiting for PostgreSQL..."
  sleep 2
done

# Try to drop/create DB (ignore failures)
echo "Resetting MLflow database..."
psql -h postgres -U "$DB_USER" -d postgres -c "DROP DATABASE IF EXISTS \"$DB_NAME\";" 2>/dev/null || true
psql -h postgres -U "$DB_USER" -d postgres -c "CREATE DATABASE \"$DB_NAME\";" 2>/dev/null || true

echo "Starting MLflow server..."
exec mlflow server \
  --host 0.0.0.0 --port 5500 \
  --backend-store-uri "${MLFLOW_BACKEND_STORE_URI}" \
  --default-artifact-root "${MLFLOW_ARTIFACTS_DESTINATION}" \
  --allowed-hosts '*' \
  --cors-allowed-origins '*'




