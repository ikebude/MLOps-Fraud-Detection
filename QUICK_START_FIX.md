# Quick Start: Fix Your Network Issues (5 Minutes)

## TL;DR - The Problem
Your Airflow tasks are failing because:
1. Containers can't resolve DNS names (postgres, 3consult-ng.com)
2. PostgreSQL connections keep timing out
3. Task heartbeat fails → task gets killed

## TL;DR - The Solution
Added explicit DNS servers and improved retry logic. Now restart and go.

---

## Steps to Deploy Fix

### Step 1: Backup your current compose file (OPTIONAL but recommended)
```bash
cd src/
cp docker-compose.yml docker-compose.yml.backup
```

### Step 2: Deploy the updated docker-compose.yml
The file is already updated! Just verify it has these sections:

```bash
# Check if DNS is in webserver (should see "8.8.8.8")
grep -A 3 "dns:" docker-compose.yml | head -20
```

Expected output:
```
    dns:
      - 8.8.8.8
      - 8.8.4.4
      - 1.1.1.1
```

### Step 3: Restart Docker Compose
```bash
# Stop everything
docker-compose down

# Start fresh with new network config
docker-compose up -d

# Wait for services to be healthy (~2 minutes)
sleep 120
```

### Step 4: Verify Everything is Running
```bash
# Check all services are healthy
docker-compose ps

# Should show "healthy" or "Up" for all services
# Pay attention to: postgres, redis, airflow-scheduler, airflow-worker
```

### Step 5: Test Network Connectivity
```bash
# Run the diagnostic script
bash check_docker_network.sh

# You should see:
# ✓ postgres is reachable
# ✓ redis is reachable
# ✓ DNS resolution for 'postgres' works
# ✓ External DNS reachable
```

### Step 6: Clear and Rerun Your DAG
In Airflow Web UI (http://localhost:8080):
1. Find DAG: `fraud_detection_training`
2. Click "Clear" (upper right)
3. Confirm "Clear the task instances"
4. Wait ~10 seconds
5. Click "Trigger DAG" or let scheduler pick it up

### Step 7: Monitor Logs
```bash
# Watch the worker process your task
docker logs -f airflow-worker 2>&1 | grep -E "Fetched|Heartbeat|ERROR"

# Should see messages like:
# Fetched 20000 records (offset 0). Total so far: 20000
# (No ERROR messages)
```

## Troubleshooting This Fix

### Services won't restart?
```bash
# Clean up any stuck containers
docker-compose down --remove-orphans
docker system prune -f
docker-compose up -d
```

### Still seeing DNS errors?
```bash
# Option 1: Check if container has DNS set
docker inspect airflow-worker | grep -A 3 "Dns"

# Option 2: Manually test DNS inside container
docker run --rm --network fraud-detection alpine nslookup postgres

# Option 3: Check host system can reach external DNS
ping 8.8.8.8
```

### Still seeing postgres connection errors?
```bash
# Verify PostgreSQL is actually running
docker exec postgres pg_isready -U airflow

# Should output: accepting connections

# If not, check postgres logs
docker logs postgres | tail -20
```

### Task still gets killed?
```bash
# Check task timeout settings in docker-compose.yml
grep "TASK_TIME_LIMIT\|JOB_HEARTBEAT" docker-compose.yml

# If needed, increase timeout:
# AIRFLOW__CELERY__TASK_TIME_LIMIT: "3600"  (1 hour)
```

## Performance Expectations

### Before Fix
- ✗ Tasks fail within 1-2 minutes
- ✗ "Temporary failure in name resolution" errors
- ✗ Job heartbeat failures in logs
- ✗ Multiple SIGTERM/SIGKILL terminations

### After Fix
- ✓ Tasks should run to completion (15-20 min for 100k records)
- ✓ Maybe 1-2 transient connection warnings (normal)
- ✓ Successful "Heartbeat recovered" messages
- ✓ API fetch completes: "Fetched 20000 records..."

## Verify It Worked

Task completion = SUCCESS:

```
[2025-12-16, XX:XX:XX UTC] {fraud_detection_training.py:496} INFO - Starting model training process
[2025-12-16, XX:XX:XX UTC] {fraud_detection_training.py:200} INFO - Starting data ingestion...
[2025-12-16, XX:XX:XX UTC] {fraud_detection_training.py:253} INFO - Fetched 20000 records (offset 0)...
[2025-12-16, XX:XX:XX UTC] {fraud_detection_training.py:253} INFO - Fetched 20000 records (offset 20000)...
[2025-12-16, XX:XX:XX UTC] {fraud_detection_training.py:253} INFO - Fetched 20000 records (offset 40000)...
[2025-12-16, XX:XX:XX UTC] {fraud_detection_training.py:253} INFO - Fetched 20000 records (offset 60000)...
[2025-12-16, XX:XX:XX UTC] {fraud_detection_training.py:253} INFO - Fetched 20000 records (offset 80000)...
[2025-12-16, XX:XX:XX UTC] {fraud_detection_training.py:XXX} INFO - Model training complete
[2025-12-16, XX:XX:XX UTC] {taskinstance.py:341} ▼ Post task execution logs
[2025-12-16, XX:XX:XX UTC] {local_task_job_runner.py:XX} INFO - Task exited with return code 0
```

## Still Having Issues?

Read the detailed guides:
- `TROUBLESHOOTING_NETWORK_ISSUES.md` - Deep technical troubleshooting
- `NETWORK_FIX_SUMMARY.md` - What changed and why

Or check logs:
```bash
docker logs airflow-scheduler 2>&1 | tail -50
docker logs airflow-worker 2>&1 | tail -50
docker logs postgres 2>&1 | tail -50
```

## Success Criteria Checklist

- [ ] `docker-compose ps` shows all services healthy/up
- [ ] `bash check_docker_network.sh` passes all tests
- [ ] DAG clear/trigger without errors
- [ ] See "Fetched 20000 records" messages in logs
- [ ] No "ERROR" or "FAIL" in task logs
- [ ] Task completes (takes ~15-20 minutes)
- [ ] MLflow shows new model run

## Estimated Time

- Restart services: 2 minutes
- Network verification: 1 minute
- DAG run: 15-20 minutes
- Total: 20-25 minutes

---

**All set!** Your network should now work reliably. The task may take a while to complete due to API pagination (100k records, 20k per page), but it should finish without errors.

Questions? Check the troubleshooting guide or review the docker-compose.yml changes.
