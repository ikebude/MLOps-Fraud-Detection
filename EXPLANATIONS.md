# 📊 FraudGuard Dashboard - Complete Explanations

## 🔍 Inference Stats Metrics Explained

### 1. **Avg Fraud Prob (Average Fraud Probability) - 34.05%**
**What it means:**
- This is the average probability score the model assigns to ALL transactions, indicating how "fraud-like" they appear
- Range: 0% (definitely not fraud) to 100% (definitely fraud)
- **34.05%** means: On average, transactions have a 34% chance of being fraudulent according to the model
- **Why it matters:** 
  - Higher values = model sees more suspicious patterns overall
  - Lower values = most transactions look legitimate
  - This helps you understand the overall "fraud risk level" in your transaction stream

### 2. **Avg Confidence (Average Confidence) - 78.90%**
**What it means:**
- This shows how confident the model is in its predictions (fraud vs not-fraud)
- Range: 0% (not confident) to 100% (very confident)
- **78.90%** means: The model is 78.9% confident in its fraud/not-fraud decisions on average
- **Why it matters:**
  - High confidence (80%+) = Model is very sure about its predictions (good!)
  - Low confidence (<60%) = Model is uncertain, might need retraining
  - Helps you trust the model's decisions

### 3. **Model Source - mlflow**
**What it means:**
- Shows where the model was loaded from
- **"mlflow"** = Model comes from MLflow model registry (the proper source)
- **Why it matters:** Confirms you're using the correct, registered model version

---

## 📈 Transaction Volume & Fraud Trends Chart - Complete Guide

### **What This Chart Shows:**
A line chart displaying transaction patterns over time to help you spot fraud trends and volume changes.

### **X-Axis (Labels) - The Time Dimension:**
- **Batch Labels** (e.g., "Batch 4", "Batch 5"): 
  - Used when many transactions have the same timestamp
  - Groups transactions into sequential batches for clarity
  - Each batch represents a group of transactions processed together
  
- **Time Labels** (e.g., "Mon, 19 Jan 2026 07:55:44 GMT"):
  - Actual timestamps when transactions occurred
  - Shows the real-time progression of transactions
  - Helps you see when fraud spikes happened

**Why both?** When transactions come in fast (same second), batching makes the chart readable. When spread out, actual times are shown.

### **Y-Axis (Volume) - The Count Dimension:**
- Shows the **number of transactions** in each time period/batch
- Auto-scales based on your data (0 to maximum)
- Example: A value of 30 means 30 transactions in that period

### **The Two Lines:**

#### **1. Valid Transactions (Dark Blue/Black Line)**
- **What it represents:** Transactions the model predicted as **NOT fraudulent** (legitimate)
- **What to look for:**
  - **Steady line** = Normal, healthy transaction flow
  - **Sudden drops** = Fewer transactions (could be system issue or low activity)
  - **Sudden spikes** = High transaction volume (busy period)
  - **Gradual rise** = Growing business (good!)

#### **2. Fraud Attempts (Orange Line)**
- **What it represents:** Transactions the model predicted as **fraudulent**
- **What to look for:**
  - **Low and stable** = Good! Few fraud attempts
  - **Sudden spike** = 🚨 **Potential fraud attack!** Take action
  - **Gradual rise** = Fraud patterns changing, model might need update
  - **Higher than normal** = Increased fraud activity

### **How to Read the Chart:**

**✅ Normal Pattern:**
- Valid transactions line is higher (most transactions are legitimate)
- Fraud line is lower and relatively stable
- Both lines move together = overall volume changes

**🚨 Fraud Attack Pattern:**
- Orange line suddenly jumps up = fraud spike detected
- Valid line stays normal = legitimate traffic unchanged
- **Action needed:** Review flagged transactions immediately

**📊 Volume Change Pattern:**
- Both lines change together = overall transaction volume changed
- Could be busy period, system issue, or business growth

**⚠️ Trend Pattern:**
- Orange line gradually rising = fraud rate increasing over time
- **Action needed:** Model might need retraining or threshold adjustment

### **Why This Chart Matters:**
- **Spot attacks instantly:** See fraud spikes as they happen
- **Monitor trends:** Watch for gradual changes in fraud patterns
- **Validate model:** Check if fraud detection is working correctly
- **Business insights:** Understand transaction volume patterns

---

## 🎯 Model Accuracy (Precision Score) - Explained

### **What is Precision?**
**Definition:** Of all transactions the model predicted as fraud, how many were ACTUALLY fraud?

**Formula:** True Positives / (True Positives + False Positives)

**Example with 94.23% precision:**
- Out of 100 transactions the model flagged as fraud:
  - ✅ 94 were actually fraud (correct predictions)
  - ❌ 6 were false alarms (legitimate transactions incorrectly flagged)

### **Why Precision Matters for Fraud Detection:**
- **High precision (90%+):** Model is reliable - when it says fraud, it's usually right
- **Low precision (<70%):** Too many false alarms - legitimate customers getting blocked (bad for business!)
- **For fraud:** We want HIGH precision to avoid blocking legitimate transactions

**Current display:** Shows precision score with 2 decimal places (e.g., "94.23%") for accuracy

---

## 💡 Total Transactions - Why It Might Show 1000

### **What It Represents:**
- Total number of transactions processed by the inference service since it started
- This is a **cumulative count** - it keeps growing as new transactions are processed

### **Why You Might See Exactly 1000:**
1. **Inference service limit:** The service might have processed exactly 1000 transactions so far
2. **Service reset:** If the service restarted, it starts counting from 0 again
3. **Caching:** Browser or service might be caching the value (try hard refresh: Ctrl+Shift+R)
4. **API limit:** The inference API might be limiting results to 1000 per request

### **How to Get More Transactions:**
1. **Run inference:** Trigger the inference service to process more transactions from the Fraud API
2. **Wait:** As new transactions come in, the count will increase
3. **Check inference service:** Make sure it's actively pulling from the Fraud API
4. **Hard refresh:** Clear cache to see updated counts

**The fix:** Now fetches the actual total from results pagination, not just stats, so you'll see the real count!

---

## ⚡ Performance Optimizations Applied

### **What We've Done:**
1. **Parallel API calls:** Stats and results fetched simultaneously (2x faster)
2. **Optimized timeouts:** 15s for parallel calls, 30s for initial load
3. **Stream optimization:** 3-second intervals (less server load, still real-time)
4. **Better error handling:** Won't block if one service is slow
5. **Smart caching:** Results are cached to reduce API calls
6. **Latest-first sorting:** Transactions sorted by newest first for live feed

### **Live Transaction Feed Optimization:**
- **Latest transactions first:** Feed shows newest transactions at the top
- **Real-time updates:** Stream updates every 3 seconds
- **Fast timestamp parsing:** Optimized to show current time accurately
- **Reduced latency:** Parallel requests cut loading time in half

---

## 🚀 Tips for Best Performance

1. **Hard refresh:** Ctrl+Shift+R to clear cache and see latest data
2. **Wait 2-3 minutes:** After deployment, services need time to stabilize
3. **Check browser console:** F12 → Console to see any errors
4. **Run inference first:** Make sure inference service has processed transactions
5. **Check service health:** All services should be running and healthy

---

**All metrics update in real-time as new transactions are processed!** 🎉
