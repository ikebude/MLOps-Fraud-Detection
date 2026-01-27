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
PG_HOST="${POSTGRES_HOST:-postgres}"
PG_PORT="${POSTGRES_PORT:-5432}"
MLFLOW_PORT="${MLFLOW_PORT:-5000}"
MLFLOW_STATIC_PREFIX="${MLFLOW_STATIC_PREFIX:-/mlflow}"

export PGPASSWORD
export DB_NAME
export DB_USER

# Wait for PostgreSQL to be ready
echo "Waiting for PostgreSQL to be ready..."
until pg_isready -h "$PG_HOST" -p "$PG_PORT" -U "$DB_USER"; do
  echo "Waiting for PostgreSQL..."
  sleep 2
done

# Try to create DB if missing (ignore failures)
echo "Ensuring MLflow database exists..."
DB_EXISTS=$(psql -h "$PG_HOST" -p "$PG_PORT" -U "$DB_USER" -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'" 2>/dev/null || true)
if [ "$DB_EXISTS" != "1" ]; then
  psql -h "$PG_HOST" -p "$PG_PORT" -U "$DB_USER" -d postgres -c "CREATE DATABASE \"$DB_NAME\";" 2>/dev/null || true
fi

echo "Starting MLflow server..."
exec mlflow server \
  --host 0.0.0.0 --port "$MLFLOW_PORT" \
  --backend-store-uri "${MLFLOW_BACKEND_STORE_URI}" \
  --default-artifact-root "${MLFLOW_ARTIFACTS_DESTINATION}" \
  --allowed-hosts '*' \
  --cors-allowed-origins '*' \
  --static-prefix "$MLFLOW_STATIC_PREFIX"