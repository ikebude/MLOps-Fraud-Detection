# 🔐 Airflow Login Credentials

## Access Information

**URL:** `http://4.153.190.166/airflow`

**Username:** `admin`

**Password:** `TnzWZQPKZ3tzwd88`

---

## How to Check Your DAG

1. Go to: `http://4.153.190.166/airflow`
2. Login with:
   - Username: `admin`
   - Password: `TnzWZQPKZ3tzwd88`
3. Look for the **"fraud_detection_training"** DAG in the DAGs list
4. Make sure it's **unpaused** (green play button, not red pause button)

---

## If DAG is Not Visible

If you don't see the DAG:
1. Check the **DAG Processor** status (should be green/healthy)
2. Check the **Triggerer** status (should be green/healthy)
3. Look at the **DAGs** tab - it should show "fraud_detection_training"
4. If still not visible, check the scheduler logs for errors

---

**Your credentials are ready to use!** 🎉
