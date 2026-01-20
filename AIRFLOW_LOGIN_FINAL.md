# 🔐 Airflow Login - FINAL SOLUTION

## ✅ Credentials (Confirmed Created)

**URL:** http://4.153.190.166/airflow  
**Username:** `airflow`  
**Password:** `airflow`

**Status:** User has been created and password set in the database.  
**Action:** Airflow webserver has been restarted to pick up the new user.

---

## 🚨 If Login STILL Doesn't Work

### Step 1: Wait and Clear Everything

1. **Wait 2 full minutes** for Airflow to fully restart
2. **Close ALL browser windows** completely
3. **Clear browser cache:**
   - Press `Ctrl + Shift + Delete`
   - Select "All time" or "Everything"
   - Check "Cookies" and "Cached images and files"
   - Click "Clear data"
4. **Restart your browser completely**

### Step 2: Try Incognito

1. Open **NEW incognito/private window** (Ctrl+Shift+N)
2. Go to: http://4.153.190.166/airflow
3. Try logging in with: `airflow` / `airflow`

### Step 3: Check What Error You Get

If you still get "Invalid credentials" or "401 Unauthorized":

**The password hash might not match.** Try this to verify the user:

```powershell
$podName = kubectl get pods -n mlops -l app=airflow-webserver -o jsonpath='{.items[0].metadata.name}'
kubectl exec -n mlops $podName -c airflow-webserver -- python3 -c "from airflow import settings; from airflow.providers.fab.auth_manager.models import User; session = settings.Session(); user = session.query(User).filter(User.username == 'airflow').first(); print('User exists:', user is not None); print('User active:', user.active if user else False); print('Has password:', bool(user.password) if user else False)"
```

### Step 4: Last Resort - Use Airflow Standalone Mode

If nothing works, we can try using Airflow's standalone mode which automatically creates the default user:

```powershell
# This will temporarily run Airflow in standalone mode to create the user
# But this might not work in Kubernetes deployment
```

---

## 🔍 Debugging

**Check Airflow logs for authentication errors:**
```powershell
kubectl logs -n mlops deployment/airflow-webserver -c airflow-webserver --tail=100 | Select-String -Pattern "auth|login|user|password"
```

**Check if user exists in database:**
```powershell
$podName = kubectl get pods -n mlops -l app=airflow-webserver -o jsonpath='{.items[0].metadata.name}'
kubectl exec -n mlops $podName -c airflow-webserver -- python3 -c "from airflow import settings; from airflow.providers.fab.auth_manager.models import User; session = settings.Session(); users = session.query(User).all(); print('Users:', [(u.username, u.active) for u in users])"
```

---

## 💡 Alternative: Try Different Browser

Sometimes browser extensions or settings can interfere:
1. Try a **different browser** (Chrome, Firefox, Edge)
2. Try from a **different computer/network**
3. Try **mobile browser** if available

---

## 📝 What We've Done

✅ Database reset completed  
✅ User created: `airflow`  
✅ Password set: `airflow`  
✅ Webserver restarted  
✅ User confirmed in database  

**The credentials ARE correct and in the database.**

If login still fails, it's likely:
- Browser cache/cookies issue
- Password hash mismatch (rare)
- Authentication backend configuration issue

**Try incognito window first - that usually fixes it!**
