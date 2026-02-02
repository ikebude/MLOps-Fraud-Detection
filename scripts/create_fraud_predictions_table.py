#!/usr/bin/env python3
"""
Create fraud_predictions table in transactions_db
This table is missing from the init script but required by the inference service
"""

import psycopg2
import os
from dotenv import load_dotenv

def create_fraud_predictions_table():
    """Create the fraud_predictions table that inference service expects"""
    
    # Load environment
    load_dotenv()
    
    # Connect to transactions_db
    conn = psycopg2.connect(
        host=os.getenv('DB_HOST', '127.0.0.1'),
        port=int(os.getenv('DB_PORT', 5432)),
        database='transactions_db',
        user='postgres',
        password=os.getenv('POSTGRES_PASSWORD', 'airflow')
    )
    
    try:
        with conn.cursor() as cur:
            # Create fraud_predictions table
            cur.execute("""
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
                    
                    -- Indexes for performance
                    CONSTRAINT fk_transaction 
                        FOREIGN KEY(transaction_id) 
                        REFERENCES transactions(transaction_id) 
                        ON DELETE CASCADE
                );
                
                -- Create indexes for efficient queries
                CREATE INDEX IF NOT EXISTS idx_fraud_predictions_transaction_id 
                    ON fraud_predictions(transaction_id);
                CREATE INDEX IF NOT EXISTS idx_fraud_predictions_user_id 
                    ON fraud_predictions(user_id);
                CREATE INDEX IF NOT EXISTS idx_fraud_predictions_timestamp 
                    ON fraud_predictions(prediction_timestamp);
                CREATE INDEX IF NOT EXISTS idx_fraud_predictions_prediction 
                    ON fraud_predictions(fraud_prediction);
                
                -- Create trigger for updated_at
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
            """)
            
            conn.commit()
            print("✅ fraud_predictions table created successfully")
            
    except Exception as e:
        print(f"❌ Error creating fraud_predictions table: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    create_fraud_predictions_table()
