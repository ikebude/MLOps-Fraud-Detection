# Dockerfile for Fraud Detection Inference Service
# Optimized for HTTP API-based data ingestion (no Kafka/Spark dependency)

FROM python:3.10.16-slim-bookworm

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
COPY requirements.txt .
RUN pip install --upgrade pip setuptools wheel && \
    pip install -r requirements.txt

# Copy application files
COPY main.py .

# Create non-root user for security
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app
USER appuser

# Set working directory
WORKDIR /app

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import joblib; print('healthy')" || exit 1

# Run inference service
CMD ["python", "main.py"]
