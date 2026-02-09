#!/usr/bin/env python3
"""Backfill transactions table with realistic test data.

Usage: python scripts/backfill_transactions.py --rows 150000

This script connects to the transactions DB using environment variables and
inserts the requested number of rows using batched INSERTs for speed.
"""

import os
import sys
import time
import random
from datetime import datetime, timezone

from faker import Faker
import psycopg2
from psycopg2.extras import execute_values

fake = Faker()

DB_HOST = os.getenv('TRANSACTIONS_HOST', os.getenv('DB_HOST', '127.0.0.1'))
DB_PORT = int(os.getenv('TRANSACTIONS_PORT', os.getenv('DB_PORT', 5432)))
DB_NAME = os.getenv('TRANSACTIONS_DB', os.getenv('DB_NAME', 'transactions_db'))
DB_USER = os.getenv('TRANSACTIONS_USER', os.getenv('DB_USER', 'fraud_producer'))
DB_PASSWORD = os.getenv('TRANSACTIONS_PASSWORD', os.getenv('DB_PASSWORD', 'producer_password'))

BATCH = 2000


def gen_transaction():
    txn_id = f"TXN_{fake.uuid4().upper()}"
    order_id = f"ORD_{fake.uuid4().upper()}"
    user_id = f"USER_{random.randint(1,1000000):06d}"
    ts = datetime.now(timezone.utc).isoformat()
    amount = round(random.uniform(50, 20000), 2)
    is_fraud = 1 if random.random() < 0.028 else 0
    full_name = fake.name()
    email = fake.email()
    phone = f"+234{random.randint(7000000000, 9099999999)}"
    product_id = f"PRD_{fake.uuid4().hex[:8].upper()}"
    product_name = fake.word().title()
    currency = 'NGN'

    return (
        txn_id, order_id, user_id, full_name, email, phone,
        ts, product_id, product_name, amount, currency, is_fraud
    )


def run(n_rows: int):
    url = dict(host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD)
    print(f"Connecting to {DB_HOST}:{DB_PORT}/{DB_NAME} as {DB_USER}")
    conn = psycopg2.connect(**url)
    cur = conn.cursor()

    insert_sql = """
        INSERT INTO transactions (transaction_id, order_id, user_id, full_name, email, phone_number, timestamp,
                                  product_id, product_name, amount, currency, is_fraud)
        VALUES %s ON CONFLICT (transaction_id) DO NOTHING
    """

    start = time.time()
    total = 0
    try:
        for i in range(0, n_rows, BATCH):
            batch = min(BATCH, n_rows - i)
            rows = [gen_transaction() for _ in range(batch)]
            execute_values(cur, insert_sql, rows, page_size=1000)
            conn.commit()
            total += batch
            print(f"Inserted {total}/{n_rows} rows...", end='\r')
    finally:
        cur.close()
        conn.close()

    elapsed = time.time() - start
    print(f"\nInserted {total} rows in {elapsed:.1f}s ({total/elapsed:.1f} rows/s)")


if __name__ == '__main__':
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument('--rows', '-r', type=int, default=150000, help='Number of rows to insert')
    args = p.parse_args()
    run(args.rows)
