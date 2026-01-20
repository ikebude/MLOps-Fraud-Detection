# 🚨 URGENT FIX GUIDE - Airflow & FraudGuard Issues

## ✅ GOOD NEWS

**FraudGuard API is working!** The API returns:
- ✅ 1000 transactions
- ✅ 21.5% fraud rate
- ✅ Data is available

The issue is likely that the **UI frontend** needs to be refreshed or there's a JavaScript loading issue.

---

## 🔧 QUICK FIXES

### Fix 1: Airflow Credentials

**Run this command:**

```powershell
powershell -ExecutionPolicy Bypass -File "scripts\fix-airflow-user-direct.ps1"
```

**OR manually:**

```powershell
$podName = kubectl get pods -n mlops -l app=airflow-webserver -o jsonpath='{.items[0].metadata.name}'
kubectl exec -n mlops $podName -c airflow-webserver -- python3 -c "from airflow import settings; from airflow.auth.managers.fab.models import User; from flask_bcrypt import generate_password_hash; session = settings.Session(); user = session.query(User).filter(User.username == 'airflow').first(); user = user or User(); user.username = 'airflow'; user.email = 'admin@example.com'; user.first_name = 'Admin'; user.last_name = 'User'; user.active = True; session.add(user) if not session.query(User).filter(User.username == 'airflow').first() else None; user.password = generate_password_hash('airflow'); session.commit(); print('SUCCESS')"
```

**Then login with:**
- URL: http://4.153.190.166/airflow
- Username: `airflow`
- Password: `airflow`

---

### Fix 2: FraudGuard UI Data

**The API is working, but UI might need refresh:**

1. **Hard refresh the browser:**
   - Press `Ctrl + Shift + R` (Windows) or `Cmd + Shift + R` (Mac)
   - Or clear browser cache

2. **Click "Refresh Model" button** in FraudGuard UI

3. **If still not working, trigger inference:**
   ```powershell
   Invoke-WebRequest -Uri "http://4.153.190.166/inference/inference/run" -Method POST -ContentType "application/json" -Body '{"max_records": 100}'
   ```
   Wait 30 seconds, then refresh FraudGuard UI

4. **Check browser console for errors:**
   - Press F12 in browser
   - Go to Console tab
   - Look for JavaScript errors

---

## 📊 Current Status

✅ **Inference Service:** Working (1000 records, 21.4% fraud rate)  
✅ **FraudGuard API:** Working (returns data correctly)  
⚠️ **FraudGuard UI:** May need browser refresh  
⚠️ **Airflow Login:** Needs user creation/reset  

---

## 🔍 Troubleshooting

### If Airflow login still fails:

1. **Check if user exists:**
   ```powershell
   $podName = kubectl get pods -n mlops -l app=airflow-webserver -o jsonpath='{.items[0].metadata.name}'
   kubectl exec -n mlops $podName -c airflow-webserver -- python3 -c "from airflow import settings; from airflow.auth.managers.fab.models import User; session = settings.Session(); user = session.query(User).filter(User.username == 'airflow').first(); print('User exists:', user is not None)"
   ```

2. **Reset database (WARNING: Deletes all data):**
   ```powershell
   kubectl exec -n mlops $podName -c airflow-webserver -- airflow db reset --yes
   ```
   This will recreate the default `airflow/airflow` user.

### If FraudGuard UI still shows "Loading...":

1. **Check browser network tab:**
   - Press F12 → Network tab
   - Refresh page
   - Look for failed requests to `/api/data`

2. **Check FraudGuard logs:**
   ```powershell
   kubectl logs -n mlops deployment/fraudguard --tail=50
   ```

3. **Verify inference has data:**
   ```powershell
   Invoke-WebRequest -Uri "http://4.153.190.166/inference/stats" -UseBasicParsing | ConvertFrom-Json
   ```

---

## ✅ Verification

After fixes, verify:

1. **Airflow:**
   - Go to http://4.153.190.166/airflow
   - Login with `airflow/airflow`
   - Should see DAGs page

2. **FraudGuard:**
   - Go to http://4.153.190.166/fraudguard
   - Should see transaction data (not "Loading...")
   - Metrics should show numbers, not "Loading..."

---

## 📞 If Still Not Working

Run the comprehensive diagnostic:

```powershell
powershell -ExecutionPolicy Bypass -File "scripts\FINAL_FIX.ps1"
```

This will show detailed status and next steps.

---

**Last Updated:** $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")
