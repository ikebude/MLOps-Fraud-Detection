#!/usr/bin/env bash
# POSIX-safe strict mode; enable 'pipefail' only when running under bash
set -eu
if [ -n "${BASH_VERSION-}" ]; then
  set -o pipefail
fi

echo "Starting MLflow server with Oracle ADB backend..."
MLFLOW_PORT="${MLFLOW_PORT:-5000}"
MLFLOW_STATIC_PREFIX="${MLFLOW_STATIC_PREFIX:-/mlflow}"

# Wait for backend to be available (check if MLFLOW_BACKEND_STORE_URI is set)
if [ -z "${MLFLOW_BACKEND_STORE_URI:-}" ]; then
  echo "ERROR: MLFLOW_BACKEND_STORE_URI not set!"
  exit 1
fi

# Sleep briefly to allow secrets to mount properly
sleep 2

echo "Starting MLflow server on port $MLFLOW_PORT..."
exec mlflow server \
  --host 0.0.0.0 --port "$MLFLOW_PORT" \
  --backend-store-uri "${MLFLOW_BACKEND_STORE_URI}" \
  --default-artifact-root "${MLFLOW_ARTIFACTS_DESTINATION}" \
  --allowed-hosts '*' \
  --cors-allowed-origins '*' \
  --static-prefix "$MLFLOW_STATIC_PREFIX"