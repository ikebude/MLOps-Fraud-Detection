FROM apache/airflow:2.10.1

# Improve pip reliability and speed during image builds
ENV PIP_DEFAULT_TIMEOUT=600 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    LD_LIBRARY_PATH=/opt/oracle/instantclient_21_10:${LD_LIBRARY_PATH} \
    ORACLE_HOME=/opt/oracle/instantclient_21_10

# Create models directory and set ownership
USER root
RUN mkdir -p /app/models /app/plugins /opt/airflow/plugins /app/config

# Install curl, build dependencies, and Oracle Instant Client
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    gcc \
    g++ \
    python3-dev \
    libc6-dev \
    libaio1 \
    wget \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Install Oracle Instant Client
RUN mkdir -p /opt/oracle && \
    cd /opt/oracle && \
    wget -O instantclient-basic.zip "https://download.oracle.com/otn_software/linux/instantclient/instantclient-basic-linux.x64-21.10.0.0.0dbru.zip" && \
    wget -O instantclient-sdk.zip "https://download.oracle.com/otn_software/linux/instantclient/instantclient-sdk-linux.x64-21.10.0.0.0dbru.zip" && \
    unzip instantclient-basic.zip && \
    unzip instantclient-sdk.zip && \
    rm instantclient-basic.zip instantclient-sdk.zip && \
    cd instantclient_21_10 && \
    echo /opt/oracle/instantclient_21_10 > /etc/ld.so.conf.d/oracle-instantclient.conf && \
    ldconfig

USER airflow
# Copy requirements file from src/airflow directory
COPY src/airflow/requirements.txt /tmp/requirements.txt

# Install Python packages as airflow user into the image virtualenv
RUN python -m pip install --upgrade pip setuptools wheel && \
    pip install --default-timeout=600 -r /tmp/requirements.txt

# Copy DAGs and plugins into the image
# Note: These can be overridden by ConfigMap/volume mounts in Kubernetes
# The build context should be from the project root, so paths are relative to that
COPY --chown=airflow:root src/dags /opt/airflow/dags
COPY --chown=airflow:root src/plugins /opt/airflow/plugins

# PATH remains as set by base image (virtualenv active)