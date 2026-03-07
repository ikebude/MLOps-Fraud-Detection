# Start Transaction Producer on Windows

This PowerShell script starts the transaction producer with pre-flight checks and monitoring.

## Usage

```powershell
# Basic startup
.\scripts\start-producer.ps1

# With custom environment file
.\scripts\start-producer.ps1 -EnvFile "custom.env"

# With verbose output
.\scripts\start-producer.ps1 -Verbose
```

## Features

✅ Environment variable validation
✅ Database connectivity check
✅ Python dependency verification
✅ Automatic retry with exponential backoff
✅ Detailed logging to file
✅ Health status monitoring
✅ Graceful shutdown handling

## Prerequisites

- Python 3.8+
- PostgreSQL client tools (psql, nc)
- .env file with database credentials

## Configuration

### Required Environment Variables

```env
DB_HOST=127.0.0.1
DB_PORT=5432
DB_NAME=transactions_db
DB_USER=fraud_user
DB_PASSWORD=your_password
```

### Optional Variables

```env
PRODUCER_INTERVAL=0.5      # Time between transaction batches (seconds)
PRODUCER_BATCH_SIZE=1      # Transactions per batch
LOG_LEVEL=INFO             # DEBUG, INFO, WARNING, ERROR, CRITICAL
```

## Monitoring

While the producer is running, check its status:

```powershell
# View logs
Get-Content logs\producer.log -Tail 50 -Wait

# Check database stats
psql -h 127.0.0.1 -U fraud_user -d transactions_db -c "SELECT COUNT(*), COUNT(CASE WHEN is_fraud=1 THEN 1 END) FROM transactions;"
```

## Troubleshooting

### "Database connection refused"
- Ensure PostgreSQL is running
- Check DB_HOST is correct (127.0.0.1 for local)
- Verify credentials in .env

### "Missing Python dependencies"
```powershell
pip install -r producer\requirements.txt
```

### "Transactions table not found"
- Producer will create it automatically on startup
- If manual creation needed:
  ```sql
  psql -h 127.0.0.1 -U fraud_user -d transactions_db < schemas/transactions.sql
  ```

### High memory/CPU usage
- Reduce PRODUCER_BATCH_SIZE in .env
- Increase PRODUCER_INTERVAL (e.g., 1.0 instead of 0.5)

## Performance Tips

- **For testing**: PRODUCER_INTERVAL=1, PRODUCER_BATCH_SIZE=10
- **For production**: PRODUCER_INTERVAL=0.1, PRODUCER_BATCH_SIZE=100
- **Monitor**: Query database periodically to ensure data is being inserted

## Output Example

```
[INFO] Loading environment from: .env
[✓] Environment loaded
[INFO] Configuration:
  Database Host: 127.0.0.1:5432
  Database Name: transactions_db
  Database User: fraud_user
  ...
[✓] All pre-flight checks passed
[INFO] Starting transaction producer...

Producer is starting... (Press Ctrl+C to stop)
```

## Logs Location

- **File**: `producer/producer.log`
- **Tail in real-time**: 
  ```powershell
  Get-Content producer/producer.log -Tail 20 -Wait
  ```





