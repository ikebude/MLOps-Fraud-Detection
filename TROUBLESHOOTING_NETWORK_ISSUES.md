# Airflow Task Failure Troubleshooting Guide

## Issue Summary

Your Airflow DAG `fraud_detection_training` is failing with two main errors:

1. **DNS Resolution Failures**: `Temporary failure in name resolution` for both:
   - External API: `3consult-ng.com`
   - Internal PostgreSQL: `postgres` service

2. **Database Connection Failures**: `psycopg2.OperationalError: could not translate host name "postgres"`

3. **Task Termination**: Tasks are being killed due to heartbeat timeout after failing to connect to PostgreSQL

## Root Cause Analysis

### Primary Issue: Docker Network DNS Configuration
The containers cannot resolve hostnames in the Docker Compose network due to:
- Missing explicit DNS server configuration
- Network isolation or DNS server unavailability
- Transient Docker daemon DNS issues

### Secondary Issue: Connection Pool Exhaustion
When database connections fail repeatedly, the connection pool gets exhausted, causing:
- Job heartbeat failures
- Task termination with `SIGTERM`/`SIGKILL`

### Tertiary Issue: External API Timeouts
The external fraud detection API (`3consult-ng.com`) has:
- Network latency/DNS issues
- Read timeout during large data transfers (100k records)
- No fallback mechanism when API is unavailable

## Solution Steps

### Step 1: Update docker-compose.yml (ALREADY COMPLETED)
✓ Added explicit DNS servers to all services:
```yaml
dns:
  - 8.8.8.8
  - 8.8.4.4
  - 1.1.1.1
```

✓ Added network configuration with proper subnet:
```yaml
networks:
  fraud-detection:
    ipam:
      config:
        - subnet: 172.20.0.0/16
          gateway: 172.20.0.1
```

✓ Assigned fixed IPs to critical services:
- postgres: 172.20.0.2
- redis: 172.20.0.3

### Step 2: Enhanced Retry Logic (ALREADY COMPLETED)
Updated `fraud_detection_training.py`:
- Added separate handling for `Timeout` and `ConnectionError`
- Improved backoff strategy with exponential backoff up to 64 seconds
- Added detailed logging for different error types
- Configured proper timeout tuple: (10s connect, 120s read)

### Step 3: Restart Docker Compose
```bash
cd src/
docker-compose down
docker-compose up -d
```

### Step 4: Verify Network Connectivity
```bash
# Run diagnostics
bash check_docker_network.sh

# Or manually test
docker run --rm --network fraud-detection alpine ping -c 3 postgres
docker run --rm --network fraud-detection alpine ping -c 3 redis
```

### Step 5: Monitor Logs
```bash
# Watch airflow-scheduler logs
docker logs -f airflow-scheduler 2>&1 | grep -E "ERROR|WARNING|Connection"

# Watch airflow-worker logs
docker logs -f airflow-worker 2>&1 | grep -E "ERROR|WARNING|DNS|postgres"

# Watch postgres logs
docker logs -f postgres 2>&1 | grep -i "connection"
```

### Step 6: Rerun the DAG
In Airflow UI:
1. Go to DAG: `fraud_detection_training`
2. Click "Clear" to reset the task state
3. Trigger a new DAG run

## Advanced Troubleshooting

### If DNS still fails inside containers:

**Option A: Fix Docker Daemon DNS**
```bash
# On Linux, edit /etc/docker/daemon.json:
{
  "dns": ["8.8.8.8", "8.8.4.4", "1.1.1.1"]
}

# Restart Docker daemon
sudo systemctl restart docker
```

**Option B: Use host network (for local testing only)**
```yaml
# In docker-compose.yml for specific services
services:
  airflow-worker:
    network_mode: host  # WARNING: not recommended for production
```

### If PostgreSQL connection fails:

**Check connection pool settings** (Already optimized in docker-compose.yml):
```yaml
AIRFLOW__DATABASE__SQL_ALCHEMY_POOL_SIZE: '50'
AIRFLOW__DATABASE__SQL_ALCHEMY_MAX_OVERFLOW: '30'
AIRFLOW__DATABASE__SQL_ALCHEMY_POOL_PRE_PING: 'true'
```

**Verify PostgreSQL is actually running:**
```bash
docker exec postgres pg_isready -U airflow
# Should output: "accepting connections"
```

### If external API times out:

**Current configuration**:
- Connection timeout: 10 seconds
- Read timeout: 120 seconds (2 minutes)
- Automatic retries with exponential backoff

**If API is consistently unavailable**, consider:

1. **Add fallback data source**:
   ```python
   # In fraud_detection_training.py
   if not all_records:
       logger.warning('API unavailable, using cached/generated data')
       # Load from local cache or generate synthetic data
   ```

2. **Reduce page size** to avoid read timeouts:
   ```bash
   # In .env or docker-compose.yml
   FRAUD_API_MAX_RECORDS=50000  # Reduce from 100000
   ```

3. **Increase task timeout**:
   ```yaml
   # In docker-compose.yml for airflow-worker
   AIRFLOW__CELERY__TASK_TIME_LIMIT: "4800"  # 80 minutes
   ```

## Verification Checklist

After applying fixes:

- [ ] Run `check_docker_network.sh` - all tests pass
- [ ] PostgreSQL logs show no connection errors
- [ ] Airflow scheduler logs show no DNS errors
- [ ] First 20000 records successfully fetched from API
- [ ] DAG completes without task termination
- [ ] MLflow artifact upload succeeds

## Performance Metrics to Monitor

1. **Database Connection Pool**:
   ```bash
   # Check active connections
   docker exec postgres psql -U airflow -d airflow -c \
     "SELECT datname, count(*) FROM pg_stat_activity GROUP BY datname;"
   ```

2. **API Fetch Performance**:
   - Check airflow logs for "Fetched X records" messages
   - Each 20k batch should take 30-90 seconds

3. **Heartbeat Health**:
   - Look for "Heartbeat recovered" in logs (good)
   - Avoid repeated "Job heartbeat failed" errors (bad)

## Long-term Recommendations

1. **Implement Circuit Breaker Pattern**:
   - Fail fast if API unreachable after N retries
   - Don't exhaust connection pools

2. **Add Health Checks**:
   ```python
   def _check_external_connectivity():
       """Verify external API and DNS before starting long task"""
   ```

3. **Implement Data Caching**:
   - Cache API responses in Minio/S3
   - Use cache when API unavailable

4. **Separate API from Training**:
   - Make data fetching a separate task
   - Allow retry at DAG level, not just connection level

5. **Monitor Resource Usage**:
   - Set memory/CPU limits on containers
   - Add Prometheus metrics for task duration

## Related Configuration Files

- `docker-compose.yml` - Network and service configuration
- `src/plugins/fraud_detection_training.py` - Task logic
- `src/.env` - Environment variables for API URL and credentials
- `src/dags/fraud_detection_training_dag.py` - DAG definition

## Support

If issues persist after these steps:

1. Collect diagnostics:
   ```bash
   bash check_docker_network.sh > diagnostics.txt
   docker logs airflow-scheduler >> diagnostics.txt
   docker logs airflow-worker >> diagnostics.txt
   docker logs postgres >> diagnostics.txt
   ```

2. Check Docker resource availability:
   ```bash
   docker stats
   docker system df
   ```

3. Verify environment variables:
   ```bash
   docker exec airflow-scheduler env | grep -E "FRAUD_API|POSTGRES|DNS"
   ```
