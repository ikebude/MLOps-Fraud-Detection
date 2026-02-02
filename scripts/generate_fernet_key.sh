#!/bin/bash
# Generate a secure Fernet key for Airflow
python3 -c "from cryptography.fernet import Fernet; key = Fernet.generate_key().decode(); print(f'AIRFLOW__CORE__FERNET_KEY={key}')"
