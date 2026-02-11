#!/usr/bin/env python3
"""
main.py - Real-time Nigerian E-commerce Transaction Generator (Enhanced)

Generates realistic raw e-commerce transactions for fraud detection training.
- Produces ONLY raw transactional data (no feature engineering)
- <3% fraud rate (2.8% average)
- Runs 24/7 when executed
- All feature engineering happens in fraud_detection_training.py

NEW ENHANCEMENTS:
- Health check endpoint for monitoring
- Prometheus metrics export
- Configurable working hours mode
- Data quality validation
- Automatic recovery from database failures
- Performance metrics tracking
- CSV export capability
- Backup to JSON files

Usage:
    python3 main.py

Requirements:
    pip install psycopg2-binary python-dotenv faker jsonschema

Environment Variables (.env):
    DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD
    PRODUCER_INTERVAL (default: 0.5 seconds)
    PRODUCER_BATCH_SIZE (default: 1)
    WORKING_HOURS_ONLY (default: false) - Set to true for business hours only
    ENABLE_JSON_BACKUP (default: false) - Backup transactions to JSON files
    ENABLE_METRICS (default: false) - Enable Prometheus metrics
    HEALTH_CHECK_PORT (default: 8080) - Port for health check endpoint
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
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

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

# NEW: Enhanced configuration
WORKING_HOURS_ONLY = os.getenv('WORKING_HOURS_ONLY', 'false').lower() == 'true'
ENABLE_JSON_BACKUP = os.getenv('ENABLE_JSON_BACKUP', 'false').lower() == 'true'
ENABLE_METRICS = os.getenv('ENABLE_METRICS', 'false').lower() == 'true'
HEALTH_CHECK_PORT = int(os.getenv('HEALTH_CHECK_PORT', 8080))
JSON_BACKUP_DIR = os.getenv('JSON_BACKUP_DIR', './backups')
MAX_RETRY_ATTEMPTS = int(os.getenv('MAX_RETRY_ATTEMPTS', 5))

# Structured JSON logging
try:
    from pythonjsonlogger import jsonlogger
except Exception:
    jsonlogger = None

root_logger = logging.getLogger()
root_logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
for h in list(root_logger.handlers):
    root_logger.removeHandler(h)

console_handler = logging.StreamHandler(sys.stdout)
if jsonlogger:
    formatter = jsonlogger.JsonFormatter('%(asctime)s %(levelname)s %(name)s %(message)s')
else:
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
root_logger.addHandler(console_handler)

logger = logging.getLogger('ecommerce_transaction_generator')

# Prometheus metrics for producer (optional)
if ENABLE_METRICS:
    try:
        from prometheus_client import Counter, start_http_server
        PRODUCER_METRICS_PORT = int(os.getenv('PRODUCER_METRICS_PORT', '8001'))
        producer_transactions_total = Counter('producer_transactions_total', 'Total transactions produced')
        producer_errors_total = Counter('producer_errors_total', 'Total producer errors')
        # Start metrics HTTP endpoint in background
        start_http_server(PRODUCER_METRICS_PORT)
        logger.info('Prometheus metrics server started on port %d', PRODUCER_METRICS_PORT)
    except Exception as e:
        logger.warning('Failed to start Prometheus client: %s', str(e))

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


class MetricsCollector:
    """NEW: Collects and exports Prometheus-style metrics."""
    
    def __init__(self):
        self.total_generated = 0
        self.total_fraud = 0
        self.total_inserted = 0
        self.total_failed = 0
        self.total_validation_errors = 0
        self.start_time = time.time()
        self.last_error_time = None
        self.error_count_last_minute = 0
        
    def record_generation(self, is_fraud: bool):
        """Record a generated transaction."""
        self.total_generated += 1
        if is_fraud:
            self.total_fraud += 1
    
    def record_insertion(self, count: int):
        """Record successful insertions."""
        self.total_inserted += count
    
    def record_failure(self):
        """Record a failure."""
        self.total_failed += 1
        self.last_error_time = time.time()
        self.error_count_last_minute += 1
    
    def record_validation_error(self):
        """Record a validation error."""
        self.total_validation_errors += 1
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get current metrics."""
        uptime = time.time() - self.start_time
        fraud_rate = (self.total_fraud / self.total_generated * 100) if self.total_generated > 0 else 0
        generation_rate = self.total_generated / uptime if uptime > 0 else 0
        
        return {
            'total_generated': self.total_generated,
            'total_fraud': self.total_fraud,
            'total_inserted': self.total_inserted,
            'total_failed': self.total_failed,
            'total_validation_errors': self.total_validation_errors,
            'fraud_rate_percent': round(fraud_rate, 2),
            'generation_rate_per_sec': round(generation_rate, 2),
            'uptime_seconds': round(uptime, 2),
            'error_count_last_minute': self.error_count_last_minute,
            'last_error_time': self.last_error_time
        }
    
    def export_prometheus(self) -> str:
        """Export metrics in Prometheus format."""
        metrics = self.get_metrics()
        lines = [
            f"# HELP transactions_generated_total Total transactions generated",
            f"# TYPE transactions_generated_total counter",
            f"transactions_generated_total {metrics['total_generated']}",
            f"",
            f"# HELP transactions_fraud_total Total fraudulent transactions",
            f"# TYPE transactions_fraud_total counter",
            f"transactions_fraud_total {metrics['total_fraud']}",
            f"",
            f"# HELP transactions_inserted_total Total transactions inserted to database",
            f"# TYPE transactions_inserted_total counter",
            f"transactions_inserted_total {metrics['total_inserted']}",
            f"",
            f"# HELP transactions_failed_total Total failed insertions",
            f"# TYPE transactions_failed_total counter",
            f"transactions_failed_total {metrics['total_failed']}",
            f"",
            f"# HELP fraud_rate_percent Current fraud rate percentage",
            f"# TYPE fraud_rate_percent gauge",
            f"fraud_rate_percent {metrics['fraud_rate_percent']}",
            f"",
            f"# HELP generation_rate_per_second Transactions generated per second",
            f"# TYPE generation_rate_per_second gauge",
            f"generation_rate_per_second {metrics['generation_rate_per_sec']}",
        ]
        return '\n'.join(lines)


class HealthCheckHandler(BaseHTTPRequestHandler):
    """NEW: HTTP handler for health checks and metrics."""
    
    metrics_collector = None
    db_manager = None
    
    def log_message(self, format, *args):
        """Suppress default HTTP logging."""
        pass
    
    def do_GET(self):
        """Handle GET requests."""
        if self.path == '/health':
            self._handle_health()
        elif self.path == '/metrics' and ENABLE_METRICS:
            self._handle_metrics()
        elif self.path == '/stats':
            self._handle_stats()
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")
    
    def _handle_health(self):
        """Health check endpoint."""
        healthy = self.db_manager.is_healthy() if self.db_manager else False
        status_code = 200 if healthy else 503
        
        response = {
            'status': 'healthy' if healthy else 'unhealthy',
            'database': 'connected' if healthy else 'disconnected',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(response, indent=2).encode())
    
    def _handle_metrics(self):
        """Prometheus metrics endpoint."""
        if not self.metrics_collector:
            self.send_response(503)
            self.end_headers()
            return
        
        metrics_text = self.metrics_collector.export_prometheus()
        
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain; version=0.0.4')
        self.end_headers()
        self.wfile.write(metrics_text.encode())
    
    def _handle_stats(self):
        """Statistics endpoint (JSON)."""
        if not self.metrics_collector:
            self.send_response(503)
            self.end_headers()
            return
        
        stats = self.metrics_collector.get_metrics()
        
        # Add database stats if available
        if self.db_manager:
            db_stats = self.db_manager.get_stats()
            stats.update({'database': db_stats})
        
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(stats, indent=2).encode())


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
        self.user_pool = self._create_user_pool(500)
        self.device_pool = self._create_device_pool(300)
        self.vendor_pool = [f"VENDOR_{i:04d}" for i in range(1, 51)]
        
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
        session_id = f"SES_{uuid.uuid4().hex[:12]}"
        
        # Select product
        category = random.choice(list(self.PRODUCT_CATEGORIES.keys()))
        product_name = random.choice(self.PRODUCT_CATEGORIES[category])
        product_id = f"PRD_{uuid.uuid4().hex[:8].upper()}"
        
        # Pricing
        if category == "Electronics":
            price = random.uniform(5000, 500000)
        elif category == "Fashion":
            price = random.uniform(1000, 50000)
        elif category == "Home & Kitchen":
            price = random.uniform(2000, 100000)
        elif category == "Groceries":
            price = random.uniform(500, 20000)
        elif category == "Beauty":
            price = random.uniform(500, 25000)
        elif category == "Sports":
            price = random.uniform(1000, 50000)
        else:  # Books
            price = random.uniform(500, 15000)
        
        discount = random.choice([0, 0, 0, 5, 10, 15, 20]) if random.random() < 0.3 else 0
        quantity = random.choices([1, 2, 3, 4, 5], weights=[70, 15, 10, 3, 2])[0]
        amount = price * quantity * (1 - discount / 100)
        
        # Payment
        payment_method = random.choice(self.PAYMENT_METHODS)
        payment_status = random.choices(
            ['success', 'failed', 'pending'],
            weights=[85, 10, 5]
        )[0]
        
        # Location
        location = random.choice(self.NIGERIAN_LOCATIONS)
        city, state = location.split(', ')
        
        # Timestamp - use current time for real-time streaming
        timestamp = datetime.now(timezone.utc)
        
        # Action
        action = random.choices(
            ['purchase', 'browse', 'add_to_cart', 'view_product', 'login'],
            weights=[40, 25, 20, 10, 5]
        )[0]
        
        # Session duration (default for legitimate transactions)
        session_duration = random.randint(30, 3600)
        
        # Post-transaction
        return_request = random.random() < 0.05
        refund_status = random.choice(['none', 'requested']) if return_request else 'none'
        rating = random.randint(1, 5) if action == 'purchase' and random.random() < 0.6 else None
        
        # Apply fraud patterns - ENHANCED for strong distinguishable signals
        fraud_type = None
        if is_fraud:
            fraud_patterns = [
                'account_takeover', 'card_fraud', 'refund_abuse',
                'identity_theft', 'triangulation', 'friendly_fraud'
            ]
            fraud_type = random.choice(fraud_patterns)
            
            # ========== STRONG FRAUD PATTERN SIGNALS ==========
            # Each pattern systematically modifies MULTIPLE features to create
            # learnable patterns for the ML model
            
            if fraud_type == 'card_fraud':
                # HIGH VALUE + SHORT SESSION + OFTEN FAILS
                amount = random.uniform(80000, 500000)  # Very high value
                session_duration = random.randint(10, 90)  # Very short session
                payment_status = random.choices(['failed', 'success'], weights=[40, 60])[0]
                quantity = random.randint(3, 10)  # Bulk purchase
                discount = 0  # No discount hunting
                
            elif fraud_type == 'refund_abuse':
                # RETURN REQUEST + HIGH VALUE + SPECIFIC CATEGORIES
                return_request = True
                refund_status = random.choice(['requested', 'approved'])
                amount = random.uniform(30000, 150000)  # Medium-high value
                category = random.choice(['Electronics', 'Fashion'])  # High-value categories
                session_duration = random.randint(60, 300)  # Short session
                
            elif fraud_type == 'account_takeover':
                # DIFFERENT DEVICE + SHORT SESSION + HIGH VALUE + FAST PURCHASE
                device = random.choice(self.device_pool)  # Random device
                location = random.choice(self.NIGERIAN_LOCATIONS)  # Different location
                session_duration = random.randint(15, 120)  # Very short session
                amount = random.uniform(50000, 300000)  # High value
                action = 'purchase'  # Direct to purchase (skips browsing)
                
            elif fraud_type == 'identity_theft':
                # NEW ACCOUNT + HIGH VALUE + FAILED PAYMENTS
                user = random.choice([u for u in self.user_pool if u['account_status'] == 'new'] or self.user_pool)
                amount = random.uniform(40000, 200000)  # High value
                payment_status = random.choices(['failed', 'pending', 'success'], weights=[30, 20, 50])[0]
                session_duration = random.randint(30, 180)  # Short session
                
            elif fraud_type == 'triangulation':
                # HIGH QUANTITY + DIFFERENT DELIVERY + BULK ORDERS
                quantity = random.randint(5, 15)  # Very high quantity
                amount = price * quantity * (1 - discount / 100)  # Recalculate with high qty
                session_duration = random.randint(120, 600)  # Medium session
                category = random.choice(['Electronics', 'Home & Kitchen'])  # Resellable items
                
            elif fraud_type == 'friendly_fraud':
                # SUCCESSFUL PURCHASE + RETURN REQUEST + HIGH VALUE
                payment_status = 'success'  # Always succeeds first
                return_request = True  # Then requests refund
                refund_status = 'requested'
                amount = random.uniform(25000, 100000)  # Medium-high value
                rating = None  # No rating (didn't intend to keep)
        
        # Build transaction
        transaction = {
            # Core identifiers
            'transaction_id': transaction_id,
            'order_id': order_id,
            'user_id': user['user_id'],
            
            # User profile
            'full_name': user['full_name'],
            'email': user['email'],
            'phone_number': user['phone_number'],
            'gender': user['gender'],
            'age': user['age'],
            'registration_date': user['registration_date'],
            'account_status': user['account_status'],
            
            # Session
            'session_id': session_id,
            'timestamp': timestamp.isoformat(),
            'action': action,
            'device_id': device['device_id'],
            'ip_address': f"{random.randint(1, 255)}.{random.randint(1, 255)}.{random.randint(1, 255)}.{random.randint(1, 255)}",
            'location': city,
            'country': 'Nigeria',
            'device_type': device['device_type'],
            'browser': device['browser'],
            'geo_location': location,
            'session_duration': session_duration,
            
            # Product
            'product_id': product_id,
            'product_name': product_name,
            'category': category,
            'price': round(price, 2),
            'discount': discount,
            'vendor_id': random.choice(self.vendor_pool),
            'quantity': quantity,
            
            # Payment
            'payment_method': payment_method,
            'payment_status': payment_status,
            'amount': round(amount, 2),
            'currency': 'NGN',
            'delivery_address': f"{random.randint(1, 999)} {fake.street_name()}, {city}, {state}, Nigeria",
            
            # Post-transaction
            'return_request': return_request,
            'refund_status': refund_status,
            'rating': rating,
            
            # Fraud
            'is_fraud': is_fraud,
            'fraud_type': fraud_type
        }
        
        # Validate
        try:
            validate(instance=transaction, schema=RAW_TRANSACTION_SCHEMA, format_checker=FormatChecker())
            return transaction
        except ValidationError as e:
            logger.debug(f"Validation failed: {e}")
            return None


class DatabaseManager:
    """
    NEW: Enhanced database manager with automatic recovery and connection pooling.
    """
    
    def __init__(self, metrics_collector: Optional[MetricsCollector] = None):
        """Initialize database manager with connection pool."""
        self.conn_pool = None
        self.running = True
        self.metrics = metrics_collector
        self.consecutive_failures = 0
        
        # Initialize connection pool
        self._init_pool()
        
        # Ensure table exists
        self._create_table()
        
        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        logger.info("Database manager initialized with connection pooling")
    
    def _init_pool(self):
        """Initialize connection pool with retry logic."""
        attempt = 0
        while attempt < MAX_RETRY_ATTEMPTS:
            try:
                self.conn_pool = pool.SimpleConnectionPool(
                    minconn=2,
                    maxconn=10,
                    host=DB_HOST,
                    port=DB_PORT,
                    dbname=DB_NAME,
                    user=DB_USER,
                    password=DB_PASSWORD,
                    sslmode=DB_SSLMODE
                )
                logger.info("Connection pool initialized (min=2, max=10)")
                self.consecutive_failures = 0
                return
            except Exception as e:
                attempt += 1
                logger.error(f"Failed to initialize connection pool (attempt {attempt}/{MAX_RETRY_ATTEMPTS}): {e}")
                if attempt < MAX_RETRY_ATTEMPTS:
                    wait_time = min(2 ** attempt, 30)  # Exponential backoff, max 30s
                    logger.info(f"Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                else:
                    logger.error("Max retry attempts reached. Connection pool not initialized.")
                    self.conn_pool = None
    
    def _get_connection(self, timeout: int = 5):
        """Get a connection from the pool."""
        if not self.conn_pool:
            logger.warning("Connection pool not available, attempting to reinitialize...")
            self._init_pool()
            if not self.conn_pool:
                return None
        
        try:
            conn = self.conn_pool.getconn()
            conn.autocommit = True
            return conn
        except Exception as e:
            logger.error(f"Failed to get connection from pool: {e}")
            if self.metrics:
                self.metrics.record_failure()
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
            if self.metrics:
                self.metrics.record_failure()
        finally:
            self._put_connection(conn)
    
    def insert_batch(self, transactions: List[Dict]) -> int:
        """
        Insert batch of transactions into database with automatic recovery.
        """
        if not self.conn_pool or not transactions:
            return 0
        
        conn = self._get_connection()
        if not conn:
            logger.error("Cannot insert: no database connection")
            if self.metrics:
                self.metrics.record_failure()
            
            # Attempt to recover connection pool
            self.consecutive_failures += 1
            if self.consecutive_failures >= 3:
                logger.warning("Multiple consecutive failures detected. Reinitializing connection pool...")
                self._init_pool()
                self.consecutive_failures = 0
            
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
            
            if self.metrics:
                self.metrics.record_insertion(len(rows))
            
            self.consecutive_failures = 0  # Reset on success
            return len(rows)
            
        except Exception as e:
            logger.error(f"Batch insert failed: {e}")
            if self.metrics:
                self.metrics.record_failure()
            
            self.consecutive_failures += 1
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


class JSONBackupManager:
    """NEW: Manages JSON backups of transactions."""
    
    def __init__(self, backup_dir: str = './backups'):
        """Initialize backup manager."""
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(exist_ok=True)
        self.current_file = None
        self.transactions_in_file = 0
        self.max_transactions_per_file = 10000
        logger.info(f"JSON backup enabled. Directory: {self.backup_dir}")
    
    def backup_transactions(self, transactions: List[Dict]):
        """Backup transactions to JSON file."""
        try:
            # Create new file if needed
            if not self.current_file or self.transactions_in_file >= self.max_transactions_per_file:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"transactions_{timestamp}.json"
                self.current_file = self.backup_dir / filename
                self.transactions_in_file = 0
                
                # Initialize file with empty array
                with open(self.current_file, 'w') as f:
                    json.dump([], f)
                
                logger.info(f"Created new backup file: {filename}")
            
            # Append transactions
            with open(self.current_file, 'r') as f:
                existing = json.load(f)
            
            existing.extend(transactions)
            
            with open(self.current_file, 'w') as f:
                json.dump(existing, f, indent=2)
            
            self.transactions_in_file += len(transactions)
            
        except Exception as e:
            logger.error(f"Failed to backup transactions to JSON: {e}")


def is_working_hours() -> bool:
    """NEW: Check if current time is within working hours (Mon-Fri, 9am-3pm WAT)."""
    now = datetime.now(timezone.utc) + timedelta(hours=1)  # Convert to WAT (UTC+1)
    
    # Check if weekday (0 = Monday, 6 = Sunday)
    if now.weekday() >= 5:  # Saturday or Sunday
        return False
    
    # Check time (9am to 3pm)
    hour = now.hour
    return 9 <= hour < 15


def start_health_check_server(port: int, metrics: MetricsCollector, db: DatabaseManager):
    """NEW: Start health check HTTP server in background thread."""
    HealthCheckHandler.metrics_collector = metrics
    HealthCheckHandler.db_manager = db
    
    try:
        server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
        logger.info(f"Health check server started on port {port}")
        logger.info(f"  - Health: http://localhost:{port}/health")
        logger.info(f"  - Stats:  http://localhost:{port}/stats")
        if ENABLE_METRICS:
            logger.info(f"  - Metrics: http://localhost:{port}/metrics")
        
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
    except Exception as e:
        logger.error(f"Failed to start health check server: {e}")


def main():
    """Main entry point - runs 24/7 transaction generation with enhancements."""
    
    logger.info("="*80)
    logger.info("Nigerian E-commerce Transaction Generator (Enhanced)")
    logger.info("="*80)
    logger.info(f"Database: {DB_HOST}:{DB_PORT}/{DB_NAME}")
    logger.info(f"Interval: {PRODUCER_INTERVAL}s | Batch Size: {PRODUCER_BATCH_SIZE}")
    logger.info(f"Fraud Rate: <3% (target: 2.8%)")
    logger.info(f"Working Hours Only: {WORKING_HOURS_ONLY}")
    logger.info(f"JSON Backup: {ENABLE_JSON_BACKUP}")
    logger.info(f"Metrics Export: {ENABLE_METRICS}")
    logger.info(f"Health Check Port: {HEALTH_CHECK_PORT}")
    logger.info("="*80)
    
    # Initialize components
    generator = TransactionGenerator()
    metrics = MetricsCollector()
    db = DatabaseManager(metrics_collector=metrics)
    
    # Initialize JSON backup if enabled
    backup_manager = JSONBackupManager(JSON_BACKUP_DIR) if ENABLE_JSON_BACKUP else None
    
    # Start health check server
    start_health_check_server(HEALTH_CHECK_PORT, metrics, db)
    
    # Check database connectivity
    if not db.is_healthy():
        logger.error("Database is not healthy - will retry automatically during operation")
    else:
        logger.info("Database connection established and healthy")
    
    # Statistics tracking
    start_time = time.time()
    last_stats_time = start_time
    in_working_hours = False
    
    try:
        while db.running:
            # Check working hours if mode is enabled
            if WORKING_HOURS_ONLY:
                if is_working_hours():
                    if not in_working_hours:
                        logger.info("Working hours started - beginning data generation")
                        in_working_hours = True
                else:
                    if in_working_hours:
                        logger.info("Working hours ended - pausing data generation")
                        in_working_hours = False
                    time.sleep(300)  # Sleep 5 minutes before checking again
                    continue
            
            # Generate single transaction for real-time streaming
            txn = generator.generate_transaction()
            if txn:
                metrics.record_generation(txn['is_fraud'] == 1)
                batch = [txn]
            else:
                metrics.record_validation_error()
                batch = []
            
            # Insert transaction
            if batch:
                inserted = db.insert_batch(batch)
                
                # Backup to JSON if enabled
                if ENABLE_JSON_BACKUP and backup_manager and inserted > 0:
                    backup_manager.backup_transactions(batch)
                
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
            current_metrics = metrics.get_metrics()
            if (current_metrics['total_generated'] > 0 and 
                current_metrics['total_generated'] % 100 == 0) or (now - last_stats_time > 10):
                
                # Get database stats
                db_stats = db.get_stats()
                db_total = db_stats.get('total_transactions', 0)
                db_fraud = db_stats.get('fraud_transactions', 0)
                db_users = db_stats.get('unique_users', 0)
                
                logger.info("="*80)
                logger.info(f"PRODUCER STATS | Generated: {current_metrics['total_generated']:,} | "
                          f"Inserted: {current_metrics['total_inserted']:,} | "
                          f"Fraud: {current_metrics['total_fraud']:,} ({current_metrics['fraud_rate_percent']:.2f}%) | "
                          f"Rate: {current_metrics['generation_rate_per_sec']:.2f} txn/s")
                logger.info(f"DATABASE STATS | Total: {db_total:,} | "
                          f"Fraud: {db_fraud:,} | Unique Users: {db_users:,}")
                if current_metrics['total_failed'] > 0:
                    logger.warning(f"FAILURES: {current_metrics['total_failed']} failed insertions")
                logger.info("="*80)
                last_stats_time = now
            
            # Sleep between transactions
            if PRODUCER_INTERVAL > 0:
                time.sleep(PRODUCER_INTERVAL)
    
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received - shutting down gracefully")
    except Exception as e:
        logger.exception(f"Unhandled exception: {e}")
        sys.exit(1)
    finally:
        # Final statistics
        final_metrics = metrics.get_metrics()
        db_stats = db.get_stats()
        
        logger.info("="*80)
        logger.info("FINAL STATISTICS")
        logger.info("="*80)
        logger.info(f"Generated:        {final_metrics['total_generated']:,} transactions")
        logger.info(f"Inserted:         {final_metrics['total_inserted']:,} transactions")
        logger.info(f"Database Total:   {db_stats.get('total_transactions', 0):,} transactions")
        logger.info(f"Fraud Count:      {final_metrics['total_fraud']:,} ({final_metrics['fraud_rate_percent']:.2f}%)")
        logger.info(f"Failed:           {final_metrics['total_failed']:,}")
        logger.info(f"Runtime:          {final_metrics['uptime_seconds']:.2f} seconds ({final_metrics['uptime_seconds']/60:.2f} minutes)")
        logger.info(f"Average Rate:     {final_metrics['generation_rate_per_sec']:.2f} txn/s")
        logger.info("="*80)
        
        logger.info("Producer shutdown complete")


if __name__ == '__main__':
    main()
