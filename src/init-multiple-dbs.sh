#!/bin/bash
set -e

# Database initialization script for fraud detection system
# Creates 3 isolated databases with proper permissions:
# 1. transactions_db - Producer writes, other services read
# 2. mlflow - MLflow experiment tracking
# 3. airflow - Airflow DAG and task metadata

# Idempotent DB and role creation (safe to re-run)
# This avoids failures when the Postgres data directory already exists.

echo "Initializing databases and roles (idempotent)..."

# Helper: create database if it does not exist
create_db_if_not_exists() {
  DB_NAME="$1"
  if psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'" | grep -q 1; then
    echo "Database '${DB_NAME}' already exists — skipping"
  else
    echo "Creating database '${DB_NAME}'"
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -c "CREATE DATABASE ${DB_NAME};"
  fi
}

# Helper: create role/user if it does not exist
create_role_if_not_exists() {
  ROLE="$1"
  PWD="$2"
  if psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "SELECT 1 FROM pg_roles WHERE rolname='${ROLE}'" | grep -q 1; then
    echo "Role '${ROLE}' already exists — skipping"
  else
    echo "Creating role '${ROLE}'"
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -c "CREATE ROLE ${ROLE} WITH LOGIN PASSWORD '${PWD}';"
  fi
}

# Create MLflow DB & user
create_db_if_not_exists "mlflow"
create_role_if_not_exists "mlflow" "mlflow"
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -c "GRANT ALL PRIVILEGES ON DATABASE mlflow TO mlflow;"

# Create transactions DB and users
create_db_if_not_exists "transactions_db"
create_role_if_not_exists "fraud_producer" "producer_password"
create_role_if_not_exists "fraud_inference" "inference_password"
create_role_if_not_exists "fraud_training" "training_password"

# Ensure privileges
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -c "GRANT ALL PRIVILEGES ON DATABASE transactions_db TO fraud_producer;"
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -c "GRANT CONNECT ON DATABASE transactions_db TO fraud_inference;"
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -c "GRANT CONNECT ON DATABASE transactions_db TO fraud_training;"

echo "Database/role initialization complete"


# Now connect to transactions_db and set up schema + permissions
# Use the PostgreSQL superuser (POSTGRES_USER) to ensure idempotent schema creation
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "transactions_db" <<-EOSQL
    
    -- ============================================
    -- SCHEMA: Create transactions table
    -- ============================================
    CREATE TABLE IF NOT EXISTS transactions (
        -- Primary key
        transaction_id VARCHAR(50) PRIMARY KEY,
        
        -- Core identifiers
        order_id VARCHAR(50) NOT NULL,
        user_id VARCHAR(50) NOT NULL,
        
        -- User profile
        full_name VARCHAR(200),
        email VARCHAR(200),
        phone_number VARCHAR(20),
        gender VARCHAR(20),
        age INTEGER,
        registration_date TIMESTAMP,
        account_status VARCHAR(50),
        
        -- Session information
        session_id VARCHAR(50),
        timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
        action VARCHAR(50),
        device_id VARCHAR(50),
        ip_address VARCHAR(50),
        location VARCHAR(100),
        country VARCHAR(100),
        device_type VARCHAR(50),
        browser VARCHAR(50),
        geo_location VARCHAR(200),
        session_duration INTEGER,
        
        -- Product information
        product_id VARCHAR(50),
        product_name VARCHAR(200),
        category VARCHAR(100),
        price DECIMAL(15, 2),
        discount DECIMAL(5, 2),
        vendor_id VARCHAR(50),
        quantity INTEGER,
        
        -- Payment details
        payment_method VARCHAR(100),
        payment_status VARCHAR(50),
        amount DECIMAL(15, 2),
        currency VARCHAR(10),
        delivery_address TEXT,
        
        -- Post-transaction
        return_request BOOLEAN DEFAULT FALSE,
        refund_status VARCHAR(50),
        rating INTEGER,
        
        -- Fraud labels (ground truth)
        is_fraud INTEGER DEFAULT 0,
        fraud_type VARCHAR(100),
        
        -- Metadata
        created_at TIMESTAMP DEFAULT NOW()
    );
    
    -- ============================================
    -- INDEXES: For efficient feature engineering
    -- ============================================
    CREATE INDEX IF NOT EXISTS idx_user_timestamp ON transactions(user_id, timestamp);
    CREATE INDEX IF NOT EXISTS idx_device_timestamp ON transactions(device_id, timestamp);
    CREATE INDEX IF NOT EXISTS idx_ip_timestamp ON transactions(ip_address, timestamp);
    CREATE INDEX IF NOT EXISTS idx_timestamp ON transactions(timestamp);
    CREATE INDEX IF NOT EXISTS idx_is_fraud ON transactions(is_fraud);
    CREATE INDEX IF NOT EXISTS idx_payment_status ON transactions(payment_status);
    CREATE INDEX IF NOT EXISTS idx_action ON transactions(action);
    
    -- Analyze table for query optimization
    ANALYZE transactions;
    
    -- ============================================
    -- FRAUD PREDICTIONS TABLE (for inference results)
    -- ============================================
    -- This table stores fraud predictions from the inference service
    CREATE TABLE IF NOT EXISTS fraud_predictions (
        id SERIAL PRIMARY KEY,
        transaction_id VARCHAR(50) NOT NULL UNIQUE,
        user_id VARCHAR(50),
        amount DECIMAL(15, 2),
        currency VARCHAR(10),
        fraud_probability DECIMAL(5, 4),
        fraud_prediction INTEGER,
        prediction_timestamp TIMESTAMP DEFAULT NOW(),
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),
        
        -- Foreign key to transactions table
        CONSTRAINT fk_transaction 
            FOREIGN KEY(transaction_id) 
            REFERENCES transactions(transaction_id) 
            ON DELETE CASCADE
    );
    
    -- Indexes for fraud_predictions table
    CREATE INDEX IF NOT EXISTS idx_fraud_predictions_transaction_id 
        ON fraud_predictions(transaction_id);
    CREATE INDEX IF NOT EXISTS idx_fraud_predictions_user_id 
        ON fraud_predictions(user_id);
    CREATE INDEX IF NOT EXISTS idx_fraud_predictions_timestamp 
        ON fraud_predictions(prediction_timestamp);
    CREATE INDEX IF NOT EXISTS idx_fraud_predictions_prediction 
        ON fraud_predictions(fraud_prediction);
    
    -- Trigger for updated_at timestamp
    CREATE OR REPLACE FUNCTION update_updated_at_column()
    RETURNS TRIGGER AS $$
    BEGIN
        NEW.updated_at = NOW();
        RETURN NEW;
    END;
    $$ language 'plpgsql';
    
    DROP TRIGGER IF EXISTS update_fraud_predictions_updated_at 
        ON fraud_predictions;
    CREATE TRIGGER update_fraud_predictions_updated_at 
        BEFORE UPDATE ON fraud_predictions 
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    
    -- Analyze fraud_predictions table
    ANALYZE fraud_predictions;

EOSQL

# Set up read-only permissions for inference and training users
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "transactions_db" <<-EOSQL
    
    -- ============================================
    -- PERMISSIONS: Grant read-only access & producer ownership
    -- ============================================
    
    -- Grant schema usage to read-only users
    GRANT USAGE ON SCHEMA public TO fraud_inference;
    GRANT USAGE ON SCHEMA public TO fraud_training;
    
    -- Grant read-only access to tables
    GRANT SELECT ON ALL TABLES IN SCHEMA public TO fraud_inference;
    GRANT SELECT ON ALL TABLES IN SCHEMA public TO fraud_training;
    
    -- Grant INSERT/UPDATE on fraud_predictions for inference user (needed for predictions)
    GRANT INSERT, UPDATE, SELECT ON fraud_predictions TO fraud_inference;

    -- Ensure producer has ownership/privileges on existing tables so it can manage inserts/DDL if necessary
    ALTER TABLE IF EXISTS transactions OWNER TO fraud_producer;
    GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO fraud_producer;

    -- Make sure future tables created by fraud_producer grant appropriate access to readers
    ALTER DEFAULT PRIVILEGES FOR ROLE fraud_producer IN SCHEMA public GRANT SELECT ON TABLES TO fraud_inference;
    ALTER DEFAULT PRIVILEGES FOR ROLE fraud_producer IN SCHEMA public GRANT SELECT ON TABLES TO fraud_training;
    ALTER DEFAULT PRIVILEGES FOR ROLE fraud_producer IN SCHEMA public GRANT INSERT, UPDATE, SELECT ON TABLES TO fraud_inference;

    -- Ensure future fraud_predictions table permissions
    ALTER DEFAULT PRIVILEGES FOR ROLE fraud_producer IN SCHEMA public GRANT INSERT, UPDATE, SELECT ON TABLES TO fraud_inference;

EOSQL

echo "✓ Databases created successfully"
echo "  - mlflow (for MLflow experiment tracking)"
echo "  - transactions_db (producer writes, inference/training read)"
echo ""
echo "Users created:"
echo "  - fraud_producer (full access to transactions_db)"
echo "  - fraud_inference (read-only access to transactions_db)"
echo "  - fraud_training (read-only access to transactions_db)"
echo "  - mlflow (full access to mlflow database)"

