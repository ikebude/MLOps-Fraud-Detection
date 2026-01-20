# Dockerfile for Fraud Detection Inference Service
# Optimized for HTTP API-based data ingestion (no Kafka/Spark dependency)

FROM python:3.12-slim-bookworm

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    gcc \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Create application directory
RUN mkdir -p /app
WORKDIR /app

# Create Python virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

# Copy and install dependencies
COPY src/inference/requirements.txt .
RUN pip install --upgrade pip setuptools wheel && \
    pip install -r requirements.txt

# Copy application files
COPY src/inference/main.py .
COPY src/inference/api_server.py .
COPY src/inference/continuous_inference.py .

# Create non-root user for security
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app && \
    chmod 777 /app  # Allow writing cumulative stats file
USER appuser

# Set working directory
WORKDIR /app

# Expose API port
EXPOSE 8000

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run inference API server by default (can override with CMD for batch mode)
CMD ["python", "api_server.py"]
