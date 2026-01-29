FROM python:3.12-slim-bookworm
WORKDIR /app

# Install curl, postgresql-client, and Oracle client build dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends bash curl postgresql-client dos2unix \
    gcc g++ python3-dev libc6-dev libaio1 wget unzip && \
    rm -rf /var/lib/apt/lists/*

COPY src/mlflow/requirements.txt /app/requirements.txt

# Install dependencies
RUN pip install -r /app/requirements.txt

# Copy entrypoint/start script
COPY src/mlflow/start-mlflow.sh /app/start-mlflow.sh
# Ensure script has Unix line endings inside the image to avoid /bin/sh parsing issues
RUN dos2unix /app/start-mlflow.sh || true
RUN chmod +x /app/start-mlflow.sh

EXPOSE 5000

# FIX: Use ENTRYPOINT to ensure bash runs directly without sh wrapper
ENTRYPOINT ["/bin/bash", "/app/start-mlflow.sh"]