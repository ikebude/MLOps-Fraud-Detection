#!/usr/bin/env python3
"""
main.py - Real-time Nigerian E-commerce Transaction Generator

Generates realistic raw e-commerce transactions for fraud detection training.
- Produces ONLY raw transactional data (no feature engineering)
- <3% fraud rate (2.8% average)
- Runs 24/7 when executed
- All feature engineering happens in fraud_detection_training.py

Usage:
    python3 main.py

Requirements:
    pip install psycopg2-binary python-dotenv faker jsonschema

Environment Variables (.env):
    DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD
    PRODUCER_INTERVAL (default: 0.5 seconds)
    PRODUCER_BATCH_SIZE (default: 1)
"""

import os
import sys
import time
import json
import random
import logging
import signal
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List

from dotenv import load_dotenv
from faker import Faker
from jsonschema import validate, ValidationError, FormatChecker

import psycopg2
from psycopg2.extras import execute_values
from psycopg2 import sql, pool

# Load environment
for path in ('.env', os.path.join(os.path.dirname(__file__), '.env')):
    if os.path.exists(path):
        load_dotenv(dotenv_path=path)
        break

# Configuration
DB_HOST = os.getenv('DB_HOST', '127.0.0.1')
DB_PORT = int(os.getenv('DB_PORT', 5432))
DB_NAME = os.getenv('DB_NAME', 'postgres')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD', '')
DB_SSLMODE = os.getenv('DB_SSLMODE', 'prefer')

PRODUCER_INTERVAL = float(os.getenv('PRODUCER_INTERVAL', '0.5'))
PRODUCER_BATCH_SIZE = int(os.getenv('PRODUCER_BATCH_SIZE', '1'))
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('ecommerce_transaction_generator')

fake = Faker('en_NG')

# Raw transaction schema (no feature engineering fields)
RAW_TRANSACTION_SCHEMA = {
    "type": "object",
    "properties": {
        # Core identifiers
        "transaction_id": {"type": "string", "minLength": 1},
        "order_id": {"type": "string", "minLength": 1},
        "user_id": {"type": "string", "minLength": 1},
        
        # User profile
        "full_name": {"type": "string", "minLength": 1},
        "email": {"type": "string", "format": "email"},
        "phone_number": {"type": "string", "pattern": "^\\+234[0-9]{10}$"},
        "gender": {"type": "string", "enum": ["Male", "Female", "Other"]},
        "age": {"type": "integer", "minimum": 18, "maximum": 100},
        "registration_date": {"type": "string", "format": "date-time"},
        "account_status": {"type": "string", "enum": ["active", "suspended", "new", "verified"]},
        
        # Session information
        "session_id": {"type": "string", "minLength": 1},
        "timestamp": {"type": "string", "format": "date-time"},
        "action": {"type": "string", "enum": ["login", "browse", "add_to_cart", "purchase", "view_product"]},
        "device_id": {"type": "string", "minLength": 1},
        "ip_address": {"type": "string", "pattern": "^[0-9]{1,3}\\.[0-9]{1,3}\\.[0-9]{1,3}\\.[0-9]{1,3}$"},
        "location": {"type": "string", "minLength": 1},
        "country": {"type": "string", "minLength": 1},
        "device_type": {"type": "string", "enum": ["Mobile", "Desktop", "Tablet"]},
        "browser": {"type": "string", "minLength": 1},
        "geo_location": {"type": "string", "minLength": 1},
        "session_duration": {"type": "integer", "minimum": 0},
        
        # Product information
        "product_id": {"type": "string", "minLength": 1},
        "product_name": {"type": "string", "minLength": 1},
        "category": {"type": "string", "minLength": 1},
        "price": {"type": "number", "minimum": 0},
        "discount": {"type": "number", "minimum": 0, "maximum": 100},
        "vendor_id": {"type": "string", "minLength": 1},
        "quantity": {"type": "integer", "minimum": 1},
        
        # Payment details
        "payment_method": {"type": "string", "minLength": 1},
        "payment_status": {"type": "string", "enum": ["success", "failed", "pending"]},
        "amount": {"type": "number", "minimum": 0},
        "currency": {"type": "string", "enum": ["NGN"]},
        "delivery_address": {"type": "string", "minLength": 1},
        
        # Post-transaction
        "return_request": {"type": "boolean"},
        "refund_status": {"type": "string", "enum": ["none", "requested", "approved", "completed", "denied"]},
        "rating": {"type": ["integer", "null"], "minimum": 1, "maximum": 5},
        
        # Fraud label (ground truth)
        "is_fraud": {"type": "integer", "minimum": 0, "maximum": 1},
        "fraud_type": {"type": ["string", "null"]},
    },
    "required": [
        "transaction_id", "order_id", "user_id", "full_name", "email", "phone_number",
        "timestamp", "action", "device_id", "ip_address", "location", "country",
        "product_id", "product_name", "category", "price", "payment_method",
        "payment_status", "amount", "currency", "is_fraud"
    ]
}


class TransactionGenerator:
    """Generates realistic Nigerian e-commerce transactions."""
    
    # Nigerian cities and states
    NIGERIAN_LOCATIONS = [
        "Lagos, Lagos", "Abuja, FCT", "Port Harcourt, Rivers", "Kano, Kano",
        "Ibadan, Oyo", "Benin City, Edo", "Kaduna, Kaduna", "Enugu, Enugu",
        "Abeokuta, Ogun", "Ilorin, Kwara", "Jos, Plateau", "Warri, Delta",
        "Calabar, Cross River", "Aba, Abia", "Owerri, Imo", "Akure, Ondo"
    ]
    
    PRODUCT_CATEGORIES = {
        "Electronics": ["Samsung Galaxy A54", "iPhone 13", "HP Laptop", "Dell Monitor", "Sony Headphones"],
        "Fashion": ["Nike Sneakers", "Adidas Tracksuit", "Designer Bag", "Wristwatch", "Sunglasses"],
        "Home & Kitchen": ["Blender", "Rice Cooker", "Gas Cooker", "Microwave", "Dinner Set"],
        "Groceries": ["Rice 50kg", "Cooking Oil", "Beverages Pack", "Frozen Chicken", "Noodles Carton"],
        "Beauty": ["Skincare Set", "Perfume", "Makeup Kit", "Hair Extensions", "Body Lotion"],
        "Sports": ["Football", "Gym Equipment", "Yoga Mat", "Running Shoes", "Sport Watch"],
        "Books": ["Textbook", "Novel", "Business Book", "Children's Book", "Magazine Subscription"]
    }
    
    PAYMENT_METHODS = [
        "Card - Mastercard", "Card - Verve", "Card - Visa",
        "Bank Transfer", "USSD", "Wallet - Paystack", "Wallet - Flutterwave"
    ]
    
    BROWSERS = ["Chrome", "Firefox", "Safari", "Edge", "Opera"]
    
    def __init__(self):
        """Initialize transaction generator."""
        self.user_pool = self._create_user_pool(500)  # Pool of 500 users for realism
        self.device_pool = self._create_device_pool(300)  # Pool of 300 devices
        self.vendor_pool = [f"VENDOR_{i:04d}" for i in range(1, 51)]  # 50 vendors
        
    def _create_user_pool(self, size: int) -> List[Dict]:
        """Create a pool of realistic users."""
        users = []
        for i in range(size):
            reg_date = fake.date_time_between(start_date='-3y', end_date='now', tzinfo=timezone.utc)
            users.append({
                'user_id': f"USER_{i:06d}",
                'full_name': fake.name(),
                'email': fake.email(),
                'phone_number': f"+234{random.randint(7000000000, 9099999999)}",
                'gender': random.choice(['Male', 'Female', 'Other']),
                'age': random.randint(18, 65),
                'registration_date': reg_date.isoformat(),
                'account_status': random.choices(
                    ['active', 'verified', 'new', 'suspended'],
                    weights=[70, 20, 8, 2]
                )[0]
            })
        return users
    
    def _create_device_pool(self, size: int) -> List[Dict]:
        """Create a pool of devices."""
        devices = []
        for i in range(size):
            device_type = random.choice(['Mobile', 'Desktop', 'Tablet'])
            devices.append({
                'device_id': f"DEV_{uuid.uuid4().hex[:12]}",
                'device_type': device_type,
                'browser': random.choice(self.BROWSERS)
            })
        return devices
    
    def generate_transaction(self) -> Dict[str, Any]:
        """Generate a single raw transaction with <3% fraud rate."""
        
        # Fraud rate: 2.8% (28 out of 1000)
        is_fraud = 1 if random.random() < 0.028 else 0
        
        # Select user and device
        user = random.choice(self.user_pool)
        device = random.choice(self.device_pool)
        
        # Generate transaction basics
        transaction_id = f"TXN_{uuid.uuid4().hex[:16].upper()}"
        order_id = f"ORD_{uuid.uuid4().hex[:12].upper()}"
        session_id = f"SESS_{uuid.uuid4().hex[:10]}"
        timestamp = datetime.now(timezone.utc).isoformat()
        
        # Location
        location = random.choice(self.NIGERIAN_LOCATIONS)
        city, state = location.split(", ")
        
        # Product selection
        category = random.choice(list(self.PRODUCT_CATEGORIES.keys()))
        product_name = random.choice(self.PRODUCT_CATEGORIES[category])
        product_id = f"PROD_{uuid.uuid4().hex[:8].upper()}"
        
        # Pricing
        base_price = random.uniform(5000, 500000)  # NGN 5k to 500k
        discount = 0
        
        # Apply discount patterns
        if random.random() < 0.3:  # 30% chance of discount
            discount = random.choice([5, 10, 15, 20, 25, 30])
        
        price = base_price
        quantity = random.choices([1, 2, 3, 4, 5], weights=[70, 15, 10, 3, 2])[0]
        amount = price * quantity * (1 - discount / 100)
        
        # Payment method
        payment_method = random.choice(self.PAYMENT_METHODS)
        
        # Payment status (fraud attempts often fail)
        if is_fraud:
            payment_status = random.choices(
                ['success', 'failed', 'pending'],
                weights=[30, 50, 20]  # Fraudsters often fail
            )[0]
        else:
            payment_status = random.choices(
                ['success', 'failed', 'pending'],
                weights=[85, 10, 5]  # Legitimate mostly succeed
            )[0]
        
        # Action type
        action = random.choices(
            ['purchase', 'add_to_cart', 'view_product', 'browse', 'login'],
            weights=[40, 25, 20, 10, 5]
        )[0]
        
        # Session duration (fraudsters tend to be faster)
        if is_fraud:
            session_duration = random.randint(30, 300)  # 30s to 5min
        else:
            session_duration = random.randint(120, 1800)  # 2min to 30min
        
        # IP address (fraud patterns)
        if is_fraud and random.random() < 0.4:
            # Suspicious IPs
            ip_address = f"{random.randint(100, 200)}.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(0, 255)}"
        else:
            # Normal Nigerian ISP ranges
            ip_address = f"{random.choice([105, 197, 41, 154])}.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(0, 255)}"
        
        # Delivery address
        delivery_address = f"{fake.street_address()}, {city}, {state}, Nigeria"
        
        # Post-transaction fields
        return_request = False
        refund_status = "none"
        rating = None
        
        if payment_status == "success" and action == "purchase":
            # Only successful purchases can have returns/ratings
            if random.random() < 0.05:  # 5% return rate
                return_request = True
                refund_status = random.choice(["requested", "approved", "completed"])
            
            if random.random() < 0.7:  # 70% leave ratings
                rating = random.choices([1, 2, 3, 4, 5], weights=[5, 5, 15, 35, 40])[0]
        
        # Fraud type (only if is_fraud = 1)
        fraud_type = None
        if is_fraud:
            fraud_type = random.choice([
                "account_takeover",
                "card_testing",
                "payment_fraud",
                "identity_theft",
                "promo_abuse",
                "friendly_fraud"
            ])
        
        # Build transaction
        transaction = {
            # Identifiers
            "transaction_id": transaction_id,
            "order_id": order_id,
            "user_id": user['user_id'],
            
            # User profile
            "full_name": user['full_name'],
            "email": user['email'],
            "phone_number": user['phone_number'],
            "gender": user['gender'],
            "age": user['age'],
            "registration_date": user['registration_date'],
            "account_status": user['account_status'],
            
            # Session
            "session_id": session_id,
            "timestamp": timestamp,
            "action": action,
            "device_id": device['device_id'],
            "ip_address": ip_address,
            "location": city,
            "country": "Nigeria",
            "device_type": device['device_type'],
            "browser": device['browser'],
            "geo_location": location,
            "session_duration": session_duration,
            
            # Product
            "product_id": product_id,
            "product_name": product_name,
            "category": category,
            "price": round(price, 2),
            "discount": discount,
            "vendor_id": random.choice(self.vendor_pool),
            "quantity": quantity,
            
            # Payment
            "payment_method": payment_method,
            "payment_status": payment_status,
            "amount": round(amount, 2),
            "currency": "NGN",
            "delivery_address": delivery_address,
            
            # Post-transaction
            "return_request": return_request,
            "refund_status": refund_status,
            "rating": rating,
            
            # Fraud label
            "is_fraud": is_fraud,
            "fraud_type": fraud_type
        }
        
        # Validate against schema
        try:
            validate(instance=transaction, schema=RAW_TRANSACTION_SCHEMA, format_checker=FormatChecker())
        except ValidationError as e:
            logger.error(f"Transaction validation failed: {e.message}")
            return None
        
        return transaction


class DatabaseManager:
    """
    Manages PostgreSQL database operations with connection pooling.
    
    Features:
    - Connection pooling for concurrent access
    - Automatic table creation
    - Batch insert optimization
    - Connection health monitoring
    - Graceful shutdown
    """
    
    def __init__(self):
        """Initialize database manager with connection pool."""
        self.conn_pool = None
        self.running = True
        
        # Initialize connection pool
        self._init_pool()
        
        # Ensure table exists
        self._create_table()
        
        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        logger.info("Database manager initialized with connection pooling")
    
    def _init_pool(self):
        """Initialize connection pool."""
        try:
            self.conn_pool = pool.SimpleConnectionPool(
                minconn=2,  # Minimum 2 connections
                maxconn=10,  # Maximum 10 connections
                host=DB_HOST,
                port=DB_PORT,
                dbname=DB_NAME,
                user=DB_USER,
                password=DB_PASSWORD,
                sslmode=DB_SSLMODE
            )
            logger.info("Connection pool initialized (min=2, max=10)")
        except Exception as e:
            logger.error(f"Failed to initialize connection pool: {e}")
            self.conn_pool = None
    
    def _get_connection(self, timeout: int = 5):
        """Get a connection from the pool."""
        if not self.conn_pool:
            return None
        
        try:
            conn = self.conn_pool.getconn()
            conn.autocommit = True
            return conn
        except Exception as e:
            logger.error(f"Failed to get connection from pool: {e}")
            return None
    
    def _put_connection(self, conn):
        """Return a connection to the pool."""
        if self.conn_pool and conn:
            try:
                self.conn_pool.putconn(conn)
            except Exception as e:
                logger.error(f"Failed to return connection to pool: {e}")
    
    def _create_table(self):
        """Create transactions table if it doesn't exist."""
        conn = self._get_connection()
        if not conn:
            logger.warning("Cannot create table: no database connection")
            return
        
        create_table_sql = """
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
        
        -- Create indexes for feature engineering queries
        CREATE INDEX IF NOT EXISTS idx_user_timestamp ON transactions(user_id, timestamp);
        CREATE INDEX IF NOT EXISTS idx_device_timestamp ON transactions(device_id, timestamp);
        CREATE INDEX IF NOT EXISTS idx_ip_timestamp ON transactions(ip_address, timestamp);
        CREATE INDEX IF NOT EXISTS idx_timestamp ON transactions(timestamp);
        CREATE INDEX IF NOT EXISTS idx_is_fraud ON transactions(is_fraud);
        CREATE INDEX IF NOT EXISTS idx_payment_status ON transactions(payment_status);
        CREATE INDEX IF NOT EXISTS idx_action ON transactions(action);
        """
        
        try:
            with conn.cursor() as cur:
                # Execute all statements
                for statement in create_table_sql.split(';'):
                    if statement.strip():
                        cur.execute(statement)
            logger.info("Transactions table ready (with indexes)")
        except Exception as e:
            logger.error(f"Failed to create table: {e}")
        finally:
            self._put_connection(conn)
    
    def insert_batch(self, transactions: List[Dict]) -> int:
        """
        Insert batch of transactions into database.
        
        Uses connection pooling for efficient resource management.
        
        Args:
            transactions: List of transaction dictionaries
            
        Returns:
            Number of transactions successfully inserted
        """
        if not self.conn_pool or not transactions:
            return 0
        
        conn = self._get_connection()
        if not conn:
            logger.error("Cannot insert: no database connection")
            return 0
        
        try:
            # Convert transactions to tuples
            rows = []
            for txn in transactions:
                rows.append((
                    txn['transaction_id'],
                    txn['order_id'],
                    txn['user_id'],
                    txn['full_name'],
                    txn['email'],
                    txn['phone_number'],
                    txn['gender'],
                    txn['age'],
                    txn['registration_date'],
                    txn['account_status'],
                    txn['session_id'],
                    txn['timestamp'],
                    txn['action'],
                    txn['device_id'],
                    txn['ip_address'],
                    txn['location'],
                    txn['country'],
                    txn['device_type'],
                    txn['browser'],
                    txn['geo_location'],
                    txn['session_duration'],
                    txn['product_id'],
                    txn['product_name'],
                    txn['category'],
                    txn['price'],
                    txn['discount'],
                    txn['vendor_id'],
                    txn['quantity'],
                    txn['payment_method'],
                    txn['payment_status'],
                    txn['amount'],
                    txn['currency'],
                    txn['delivery_address'],
                    txn['return_request'],
                    txn['refund_status'],
                    txn['rating'],
                    txn['is_fraud'],
                    txn['fraud_type']
                ))
            
            insert_sql = """
            INSERT INTO transactions (
                transaction_id, order_id, user_id, full_name, email, phone_number, gender, age,
                registration_date, account_status, session_id, timestamp, action, device_id,
                ip_address, location, country, device_type, browser, geo_location, session_duration,
                product_id, product_name, category, price, discount, vendor_id, quantity,
                payment_method, payment_status, amount, currency, delivery_address,
                return_request, refund_status, rating, is_fraud, fraud_type
            ) VALUES %s ON CONFLICT (transaction_id) DO NOTHING
            """
            
            with conn.cursor() as cur:
                execute_values(cur, insert_sql, rows, page_size=100)
            
            return len(rows)
            
        except Exception as e:
            logger.error(f"Batch insert failed: {e}")
            return 0
        finally:
            self._put_connection(conn)
    
    def get_stats(self) -> Dict[str, int]:
        """Get transaction statistics from database."""
        conn = self._get_connection()
        if not conn:
            return {}
        
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT 
                        COUNT(*) as total,
                        COUNT(CASE WHEN is_fraud=1 THEN 1 END) as fraud_count,
                        COUNT(DISTINCT user_id) as unique_users
                    FROM transactions
                """)
                row = cur.fetchone()
                if row:
                    return {
                        'total_transactions': row[0] or 0,
                        'fraud_transactions': row[1] or 0,
                        'unique_users': row[2] or 0
                    }
        except Exception as e:
            logger.error(f"Failed to get statistics: {e}")
        finally:
            self._put_connection(conn)
        
        return {}
    
    def is_healthy(self) -> bool:
        """Check if database connection pool is healthy."""
        conn = self._get_connection()
        if not conn:
            return False
        
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
            self._put_connection(conn)
            return True
        except Exception:
            return False
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        logger.info(f"Signal {signum} received - shutting down gracefully")
        self.running = False
        
        # Close all connections in pool
        if self.conn_pool:
            try:
                self.conn_pool.closeall()
                logger.info("Connection pool closed")
            except Exception as e:
                logger.error(f"Error closing connection pool: {e}")
        
        sys.exit(0)
    
    def __del__(self):
        """Cleanup on deletion."""
        if self.conn_pool:
            try:
                self.conn_pool.closeall()
            except Exception:
                pass

def main():
    """Main entry point - runs 24/7 transaction generation."""
    
    logger.info("="*80)
    logger.info("Nigerian E-commerce Transaction Generator with Connection Pooling")
    logger.info("="*80)
    logger.info(f"Database: {DB_HOST}:{DB_PORT}/{DB_NAME}")
    logger.info(f"Interval: {PRODUCER_INTERVAL}s | Batch Size: {PRODUCER_BATCH_SIZE}")
    logger.info(f"Fraud Rate: <3% (target: 2.8%)")
    logger.info("Running 24/7 - Press Ctrl+C to stop")
    logger.info("="*80)
    
    # Initialize components
    generator = TransactionGenerator()
    db = DatabaseManager()
    
    # Check database connectivity
    if not db.is_healthy():
        logger.error("Database is not healthy - retrying with exponential backoff")
        backoff = 1
        while backoff <= 32:
            logger.info(f"Retrying in {backoff} seconds...")
            time.sleep(backoff)
            if db.is_healthy():
                break
            backoff *= 2
        
        if not db.is_healthy():
            logger.error("Database unavailable after retries - exiting")
            sys.exit(1)
    
    logger.info("Database connection established and healthy")
    
    # Statistics tracking
    total_generated = 0
    total_fraud = 0
    total_inserted = 0
    start_time = time.time()
    last_stats_time = start_time
    
    try:
        while db.running:
            # Generate batch
            batch = []
            for _ in range(PRODUCER_BATCH_SIZE):
                txn = generator.generate_transaction()
                if txn:
                    batch.append(txn)
                    total_generated += 1
                    if txn['is_fraud'] == 1:
                        total_fraud += 1
            
            # Insert batch
            if batch:
                inserted = db.insert_batch(batch)
                total_inserted += inserted
                
                # Log sample transactions
                if LOG_LEVEL == 'DEBUG':
                    for txn in batch[:min(2, len(batch))]:
                        logger.debug(
                            f"[{txn['action'].upper()}] {txn['transaction_id']} | "
                            f"User: {txn['user_id']} | Amount: NGN {txn['amount']:,.2f} | "
                            f"Status: {txn['payment_status']} | Fraud: {txn['is_fraud']}"
                        )
            
            # Periodic statistics (every 10 seconds or 100 transactions)
            now = time.time()
            if (total_generated > 0 and total_generated % 100 == 0) or (now - last_stats_time > 10):
                fraud_rate = (total_fraud / total_generated) * 100 if total_generated > 0 else 0
                elapsed = now - start_time
                rate = total_generated / elapsed if elapsed > 0 else 0
                
                # Get database stats
                db_stats = db.get_stats()
                db_total = db_stats.get('total_transactions', 0)
                db_fraud = db_stats.get('fraud_transactions', 0)
                db_users = db_stats.get('unique_users', 0)
                
                logger.info("="*80)
                logger.info(f"PRODUCER STATS | Generated: {total_generated:,} | "
                          f"Inserted: {total_inserted:,} | Fraud: {total_fraud:,} ({fraud_rate:.2f}%) | "
                          f"Rate: {rate:.2f} txn/s")
                logger.info(f"DATABASE STATS | Total: {db_total:,} | "
                          f"Fraud: {db_fraud:,} | Unique Users: {db_users:,}")
                logger.info("="*80)
                last_stats_time = now
            
            # Sleep between batches
            if PRODUCER_INTERVAL > 0:
                time.sleep(PRODUCER_INTERVAL)
    
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received - shutting down gracefully")
    except Exception as e:
        logger.exception(f"Unhandled exception: {e}")
        sys.exit(1)
    finally:
        # Final statistics
        elapsed = time.time() - start_time
        fraud_rate = (total_fraud / total_generated * 100) if total_generated > 0 else 0
        
        db_stats = db.get_stats()
        db_total = db_stats.get('total_transactions', 0)
        
        logger.info("="*80)
        logger.info("FINAL STATISTICS")
        logger.info("="*80)
        logger.info(f"Generated:        {total_generated:,} transactions")
        logger.info(f"Inserted:         {total_inserted:,} transactions")
        logger.info(f"Database Total:   {db_total:,} transactions")
        logger.info(f"Fraud Count:      {total_fraud:,} ({fraud_rate:.2f}%)")
        logger.info(f"Runtime:          {elapsed:.2f} seconds ({elapsed/60:.2f} minutes)")
        logger.info(f"Average Rate:     {total_generated/elapsed if elapsed > 0 else 0:.2f} txn/s")
        logger.info("="*80)
        
        logger.info("Producer shutdown complete")


if __name__ == '__main__':
    main()

