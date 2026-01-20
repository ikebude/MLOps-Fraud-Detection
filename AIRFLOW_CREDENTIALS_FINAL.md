# 🔐 Airflow Login Credentials - Final Solution

## ✅ Current Credentials

**URL:** http://4.153.190.166/airflow

**Username:** `airflow`  
**Password:** `airflow`

The user has been created/updated in the database.

---

## 🚨 If Login Still Fails

### Quick Fixes (Try These First):

1. **Clear Browser Cache:**
   - Press `Ctrl + Shift + Delete`
   - Clear cookies and cached files
   - Close and reopen browser

2. **Try Incognito/Private Window:**
   - Open new incognito window
   - Go to http://4.153.190.166/airflow
   - Try logging in

3. **Hard Refresh:**
   - Press `Ctrl + Shift + R` on the login page
   - Try logging in again

4. **Check Airflow is Ready:**
   ```powershell
   Invoke-WebRequest -Uri "http://4.153.190.166/airflow/api/v2/monitor/health" -UseBasicParsing
   ```
   Should return 200 status.

---

## 🔧 Nuclear Option: Database Reset

**If nothing else works, reset the database:**

⚠️ **WARNING: This deletes ALL DAG run history!**

```powershell
kubectl exec -n mlops deployment/airflow-webserver -c airflow-webserver -- airflow db reset --yes
```

**After reset:**
1. Wait 2-3 minutes for Airflow to fully restart
2. The default user `airflow/airflow` will be automatically created
3. Try logging in

---

## 🔍 Verify User Exists

To check if the user exists in the database:

```powershell
$podName = kubectl get pods -n mlops -l app=airflow-webserver -o jsonpath='{.items[0].metadata.name}'
kubectl exec -n mlops $podName -c airflow-webserver -- python3 -c "from airflow import settings; from airflow.providers.fab.auth_manager.models import User; session = settings.Session(); user = session.query(User).filter(User.username == 'airflow').first(); print('User exists:', user is not None if user else False)"
```

---

## 📝 Alternative: Check Pod Logs

If login fails, check for errors:

```powershell
kubectl logs -n mlops deployment/airflow-webserver -c airflow-webserver --tail=50
```

Look for authentication or database errors.

---

## ✅ Expected Behavior

After successful login:
- You should see the Airflow DAGs page
- No error messages
- Can see and trigger DAGs

If you see "401 Unauthorized" or "Invalid credentials":
- The password hash might not match
- Try database reset (see above)

---

**The credentials are: `airflow` / `airflow`**

If they don't work after clearing cache and trying incognito, use the database reset method.
