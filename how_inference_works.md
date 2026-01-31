# How the Fraud Detection Inference System Works

## 🎯 Overview

The inference system loads a trained machine learning model and uses it to predict whether new e-commerce transactions are fraudulent. It takes raw transaction data, engineers the same 62 features used during training, and returns a fraud probability score.

---

## 📊 Step-by-Step Inference Process

### Step 1: System Initialization

When you start the inference system, it performs these actions:

```python
inference = FraudDetectionInference(model_path='/app/models/fraud_detection_model.pkl')
```

**What happens:**
1. **Loads the trained model** from disk (the `.pkl` file created by training)
2. **Connects to PostgreSQL** database to fetch transaction data
3. **Validates** that the model loaded successfully

```
┌─────────────────────────────────────────┐
│  INITIALIZATION                         │
├─────────────────────────────────────────┤
│                                         │
│  1. Load Model (.pkl file)              │
│     ├─ XGBoost classifier               │
│     ├─ SMOTE preprocessor               │
│     └─ Optimal threshold (e.g., 0.35)   │
│                                         │
│  2. Connect to Database                 │
│     └─ PostgreSQL connection pool       │
│                                         │
│  3. Ready for predictions               │
└─────────────────────────────────────────┘
```

---

### Step 2: Fetch Transaction Data

Depending on the mode you're running, the system fetches transaction(s):

#### A. Single Transaction Mode
```bash
python3 inference.py --transaction-id TXN_ABC123
```

**What happens:**
```python
# Executes SQL query
SELECT * FROM transactions WHERE transaction_id = 'TXN_ABC123'
```

Returns ONE transaction as a pandas DataFrame.

#### B. Batch Mode
```bash
python3 inference.py --batch --limit 100
```

**What happens:**
```python
# Executes SQL query
SELECT * FROM transactions 
ORDER BY timestamp DESC 
LIMIT 100
```

Returns 100 most recent transactions as a pandas DataFrame.

#### C. Continuous Monitoring Mode
```bash
python3 inference.py --monitor --interval 5
```

**What happens:**
```python
# Every 5 seconds, executes:
SELECT * FROM transactions 
WHERE timestamp > last_checked_time
ORDER BY timestamp ASC
```

Returns only NEW transactions since last check.

#### D. API Mode
```bash
python3 inference.py --api --port 5001

# Then call:
curl -X POST http://localhost:5001/predict \
  -H "Content-Type: application/json" \
  -d '{"transaction_id": "TXN_ABC123"}'
```

**What happens:**
Same as single transaction mode, but exposed via REST API.

---

### Step 3: Feature Engineering (The Critical Step)

This is where the **magic** happens. The raw transaction data doesn't go directly into the model. First, we need to create the same 62 features that were used during training.

**Raw Transaction Data (from database):**
```json
{
  "transaction_id": "TXN_001",
  "user_id": "USER_123",
  "timestamp": "2026-01-30 14:30:00",
  "registration_date": "2025-11-15 10:00:00",
  "amount": 50000,
  "device_id": "DEV_XYZ",
  "ip_address": "197.210.1.45",
  "payment_status": "success",
  "account_status": "new",
  "session_duration": 45,
  "location": "Lagos, Lagos",
  "action": "purchase",
  ...
}
```

**After Feature Engineering (62 features created):**
```python
# TEMPORAL FEATURES
account_age_days = 76                    # Days since registration
transaction_velocity_1h = 3              # 3 transactions in last hour
transaction_velocity_24h = 8             # 8 transactions in last 24h
hour_of_day = 14                         # 2 PM
is_weekend = 0                           # Not weekend
is_night_transaction = 0                 # Not 1-5 AM

# IDENTITY FEATURES
identity_verification_score = 0.30       # Low (account_status = 'new')
email_domain_risk = 0.5                  # Medium risk email domain
sim_swap_likelihood = 0.2                # Low probability

# DEVICE FEATURES
device_fingerprint_score = 0.4           # Medium trust device
device_user_count = 1                    # 1 user on this device
emulator_detection_score = 0.1           # Unlikely to be emulator

# LOCATION FEATURES
ip_risk_score = 0.3                      # Nigerian IP, lower risk
vpn_proxy_score = 0.1                    # No VPN detected
location_velocity = 0                    # Not moving between locations

# PAYMENT FEATURES
failed_payment_ratio = 0.0               # No failed payments yet
amount_anomaly_score = 0.8               # NGN 50K is high for new account
payment_method_risk = 0.2                # Card payment, moderate risk

# NETWORK FEATURES
fraud_ring_score = 0.0                   # Not connected to fraud network
linked_accounts = 1                      # Only 1 account
vendor_risk_score = 0.1                  # Reputable vendor

# BEHAVIORAL FEATURES
session_duration_anomaly = 0.9           # 45 seconds is VERY short
rapid_action_flag = 1                    # Too fast checkout
activity_consistency_score = 0.2         # Inconsistent with normal users

# ADDRESS FEATURES
address_risk_score = 0.3                 # Lagos address, moderate
address_reuse_count = 1                  # First time address used

# DELIVERY FEATURES
delivery_failure_rate = 0.0              # No history yet
return_rate = 0.0                        # No returns

# ACCOUNT LINKING FEATURES
shared_device_count = 0                  # Device not shared
shared_ip_count = 1                      # IP used by 1 account
multiple_devices_per_user = 1            # User has 1 device

... (total 62 features)
```

**How Features Are Calculated:**

Let me show you a few examples from the code:

#### Example 1: Account Age
```python
# Simple subtraction
df['account_age_days'] = (
    df['timestamp'] - df['registration_date']
).dt.total_seconds() / 86400

# Result: 76 days
```

#### Example 2: Transaction Velocity
```python
# Count transactions in rolling 1-hour window
df['transaction_velocity_1h'] = df.groupby('user_id')['timestamp'].transform(
    lambda x: x.rolling('1H').count()
)

# If user made transactions at:
# 13:30, 13:45, 14:00, 14:30
# Then at 14:30, count in last hour = 3
```

#### Example 3: Identity Verification Score
```python
# Based on account status
df['identity_verification_score'] = 0.3  # default for 'new'
df.loc[df['account_status'] == 'verified', 'identity_verification_score'] = 0.95
df.loc[df['account_status'] == 'active', 'identity_verification_score'] = 0.70

# If account_status = 'new' → score = 0.3 (risky)
```

#### Example 4: Device User Count
```python
# Count how many users share this device
device_counts = df.groupby('device_id')['user_id'].nunique()
df['device_user_count'] = df['device_id'].map(device_counts)

# If 5 different users used device_id 'DEV_XYZ' → score = 5 (suspicious)
```

#### Example 5: Failed Payment Ratio
```python
# Calculate user's historical failed payment rate
user_payment_history = df.groupby('user_id').agg({
    'payment_status': lambda x: (x == 'failed').sum() / len(x)
})

# If user had 10 transactions, 3 failed → ratio = 0.3
```

---

### Step 4: Model Prediction

Now we have a DataFrame with 62 features. Time to predict!

```python
# The model is a pipeline:
# Pipeline([
#     ('preprocessor', StandardScaler/None),
#     ('smote', SMOTE),              # Only used during training
#     ('classifier', XGBoostClassifier)
# ])

# Get probability scores (0 to 1)
fraud_probabilities = model.predict_proba(features_df)[:, 1]

# Example output:
# [0.05, 0.23, 0.87, 0.42, 0.91]
#  ^      ^      ^      ^      ^
#  5%    23%    87%    42%    91% fraud probability
```

**What the model does internally:**

1. **Preprocessor** (if used): Scales features to standard range
2. **XGBoost Trees**: Evaluates 62 features through decision trees
   - Tree 1: "Is account_age_days < 10? Is amount > 100000?"
   - Tree 2: "Is transaction_velocity_1h > 5? Is session_duration < 60?"
   - Tree 3: "Is device_user_count > 3? Is vpn_proxy_score > 0.5?"
   - ... (100+ trees voting)
3. **Ensemble**: Combines all tree votes into final probability

---

### Step 5: Apply Threshold & Classify

The model outputs a probability, but we need a binary decision: Fraud or Not Fraud?

```python
# Optimal threshold was determined during training (e.g., 0.35)
optimal_threshold = 0.35

# Make binary predictions
fraud_predictions = (fraud_probabilities >= optimal_threshold).astype(int)

# Examples:
# Probability 0.05 < 0.35 → Prediction = 0 (NOT FRAUD)
# Probability 0.87 > 0.35 → Prediction = 1 (FRAUD)
# Probability 0.91 > 0.35 → Prediction = 1 (FRAUD)
```

**Why not just use 0.5 as threshold?**

Because fraud is rare (<3% of transactions), we want to catch more fraud cases even if it means a few more false alarms. The threshold is optimized to maximize F1 score (balance of precision and recall).

---

### Step 6: Risk Level Classification

To make it more actionable, we categorize fraud probability into risk levels:

```python
def get_risk_level(probability):
    if probability < 0.30:
        return "LOW"         # 🟢 Green - Safe
    elif probability < 0.60:
        return "MEDIUM"      # 🟡 Yellow - Review manually
    elif probability < 0.85:
        return "HIGH"        # 🟠 Orange - Block & investigate
    else:
        return "CRITICAL"    # 🔴 Red - Immediate action
```

**Examples:**
```
Probability 0.05 → LOW RISK        → Auto-approve
Probability 0.42 → MEDIUM RISK     → Flag for review
Probability 0.78 → HIGH RISK       → Block transaction
Probability 0.95 → CRITICAL RISK   → Block + alert security
```

---

### Step 7: Format & Return Results

The system creates a structured prediction result:

```python
prediction = {
    'transaction_id': 'TXN_001',
    'user_id': 'USER_123',
    'amount': 50000.00,
    'timestamp': '2026-01-30T14:30:00Z',
    
    # Prediction results
    'fraud_probability': 0.8734,      # 87.34% chance of fraud
    'fraud_prediction': 1,             # Binary: 1 = FRAUD
    'fraud_label': 'FRAUD',            # Human-readable label
    'risk_level': 'HIGH',              # Risk category
    
    # Ground truth (if available)
    'actual_fraud': 1,                 # True label from database
    
    # Top contributing features (optional)
    'top_risk_factors': [
        'session_duration_anomaly: 0.90',
        'amount_anomaly_score: 0.85',
        'account_age_days: 76 (too new)',
        'transaction_velocity_1h: 3 (too high)'
    ]
}
```

---

### Step 8: Store Predictions (Optional)

The system can save predictions back to the database:

```python
# Creates table if not exists
CREATE TABLE fraud_predictions (
    transaction_id TEXT PRIMARY KEY,
    user_id TEXT,
    fraud_probability NUMERIC,
    fraud_prediction INTEGER,
    risk_level TEXT,
    predicted_at TIMESTAMP,
    model_version TEXT
)

# Inserts prediction
INSERT INTO fraud_predictions VALUES (...)
```

This allows you to:
- Track prediction history
- Compare predictions vs actual fraud
- Monitor model performance over time
- Audit decisions

---

## 🔄 Complete Inference Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│  USER TRIGGERS INFERENCE                                        │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
        ┌────────────────────────┐
        │  1. FETCH TRANSACTION  │
        │  FROM DATABASE         │
        └────────────┬───────────┘
                     │
                     │  Raw Data:
                     │  {transaction_id, user_id, timestamp,
                     │   amount, device_id, ip_address, ...}
                     │
                     ▼
        ┌────────────────────────────────┐
        │  2. FEATURE ENGINEERING        │
        │                                │
        │  Input: 30+ raw fields         │
        │  Output: 62 engineered features│
        │                                │
        │  ┌──────────────────────────┐  │
        │  │ Temporal (8 features)    │  │
        │  │ - account_age_days       │  │
        │  │ - transaction_velocity   │  │
        │  │ - hour_of_day            │  │
        │  └──────────────────────────┘  │
        │                                │
        │  ┌──────────────────────────┐  │
        │  │ Identity (7 features)    │  │
        │  │ - verification_score     │  │
        │  │ - email_risk             │  │
        │  └──────────────────────────┘  │
        │                                │
        │  ┌──────────────────────────┐  │
        │  │ Device (5 features)      │  │
        │  │ - device_fingerprint     │  │
        │  │ - device_user_count      │  │
        │  └──────────────────────────┘  │
        │                                │
        │  ... (7 more categories)       │
        └────────────┬───────────────────┘
                     │
                     │  Features:
                     │  [0.76, 3, 8, 14, 0, 0, 0.30, 0.5,
                     │   0.2, 0.4, 1, 0.1, 0.3, ...]
                     │
                     ▼
        ┌────────────────────────────────┐
        │  3. MODEL PREDICTION           │
        │                                │
        │  XGBoost Classifier Pipeline:  │
        │                                │
        │  ┌──────────────────────────┐  │
        │  │ Tree 1: Account age?     │  │
        │  │ Vote: 0.8 (fraud)        │  │
        │  └──────────────────────────┘  │
        │                                │
        │  ┌──────────────────────────┐  │
        │  │ Tree 2: Velocity high?   │  │
        │  │ Vote: 0.9 (fraud)        │  │
        │  └──────────────────────────┘  │
        │                                │
        │  ┌──────────────────────────┐  │
        │  │ Tree 3: Session short?   │  │
        │  │ Vote: 0.85 (fraud)       │  │
        │  └──────────────────────────┘  │
        │                                │
        │  ... (100 trees)               │
        │                                │
        │  Average: 0.8734               │
        └────────────┬───────────────────┘
                     │
                     │  Probability: 0.8734
                     │
                     ▼
        ┌────────────────────────────────┐
        │  4. THRESHOLD APPLICATION      │
        │                                │
        │  if probability >= 0.35:       │
        │      prediction = 1 (FRAUD)    │
        │  else:                         │
        │      prediction = 0 (LEGIT)    │
        │                                │
        │  0.8734 >= 0.35 → FRAUD        │
        └────────────┬───────────────────┘
                     │
                     ▼
        ┌────────────────────────────────┐
        │  5. RISK CLASSIFICATION        │
        │                                │
        │  if prob < 0.30: LOW           │
        │  elif prob < 0.60: MEDIUM      │
        │  elif prob < 0.85: HIGH        │
        │  else: CRITICAL                │
        │                                │
        │  0.8734 → HIGH RISK            │
        └────────────┬───────────────────┘
                     │
                     ▼
        ┌────────────────────────────────┐
        │  6. FORMAT RESULTS             │
        │                                │
        │  {                             │
        │    transaction_id: TXN_001     │
        │    fraud_probability: 0.8734   │
        │    fraud_prediction: 1         │
        │    fraud_label: "FRAUD"        │
        │    risk_level: "HIGH"          │
        │  }                             │
        └────────────┬───────────────────┘
                     │
                     ▼
        ┌────────────────────────────────┐
        │  7. SAVE TO DATABASE           │
        │  (fraud_predictions table)     │
        └────────────┬───────────────────┘
                     │
                     ▼
        ┌────────────────────────────────┐
        │  8. RETURN TO USER             │
        │                                │
        │  - Console output (CLI)        │
        │  - JSON response (API)         │
        │  - Log file (monitoring)       │
        └────────────────────────────────┘
```

---

## 💻 Real Usage Examples

### Example 1: Single Transaction

```bash
$ python3 inference.py --transaction-id TXN_001

# Output:
======================================================================
FRAUD DETECTION RESULT
======================================================================
Transaction ID:    TXN_001
User ID:           USER_123
Amount:            NGN 50,000.00
Fraud Probability: 87.34%
Prediction:        FRAUD
Risk Level:        HIGH
Timestamp:         2026-01-30T14:30:00Z
Actual Label:      FRAUD
======================================================================

⚠️  HIGH RISK - Block transaction and investigate
```

### Example 2: Batch Prediction

```bash
$ python3 inference.py --batch --limit 10

# Output:
======================================================================
BATCH PREDICTION SUMMARY
======================================================================
Total Transactions:  10
Predicted Fraud:     2 (20.0%)
Avg Fraud Prob:      32.45%
======================================================================

Risk Distribution:
  LOW.................     6 (60.0%)
  MEDIUM..............     2 (20.0%)
  HIGH................     2 (20.0%)
  CRITICAL............     0 (0.0%)
======================================================================
```

### Example 3: Continuous Monitoring

```bash
$ python3 inference.py --monitor --interval 5

# Output (every 5 seconds):
2026-01-30 14:30:00 - INFO - Starting continuous monitoring (interval: 5s)
2026-01-30 14:30:05 - INFO - Found 3 new transactions
2026-01-30 14:30:05 - INFO - 🔍 TXN_001 | User: USER_123 | Amount: NGN 50,000.00 | Fraud Prob: 87.34% | Prediction: FRAUD | Risk: HIGH
2026-01-30 14:30:05 - INFO - 🔍 TXN_002 | User: USER_456 | Amount: NGN 5,200.00 | Fraud Prob: 12.45% | Prediction: LEGIT | Risk: LOW
2026-01-30 14:30:05 - INFO - 🔍 TXN_003 | User: USER_789 | Amount: NGN 95,000.00 | Fraud Prob: 91.23% | Prediction: FRAUD | Risk: CRITICAL
```

### Example 4: REST API

```bash
# Start API server
$ python3 inference.py --api --port 5001

# In another terminal, make request
$ curl -X POST http://localhost:5001/predict \
  -H "Content-Type: application/json" \
  -d '{"transaction_id": "TXN_001"}'

# Response:
{
  "transaction_id": "TXN_001",
  "user_id": "USER_123",
  "amount": 50000.0,
  "fraud_probability": 0.8734,
  "fraud_prediction": 1,
  "fraud_label": "FRAUD",
  "risk_level": "HIGH",
  "timestamp": "2026-01-30T14:30:00Z",
  "actual_fraud": 1
}
```

---

## 🎓 Key Concepts

### 1. Why Feature Engineering Matters

**Bad Approach** (won't work well):
```
Raw Data → Model → Prediction
```

**Good Approach** (what we do):
```
Raw Data → Feature Engineering → Model → Prediction
```

**Example:**
- Raw: `timestamp = "2026-01-30 14:30:00"`
- Feature: `hour_of_day = 14, is_night = 0, is_weekend = 0`

The model can't understand "2026-01-30 14:30:00" directly, but it CAN understand that transactions at 3 AM (is_night=1) are more likely fraudulent.

### 2. Feature Consistency is CRITICAL

**Training time features:**
```python
account_age_days = (timestamp - registration_date) / 86400
```

**Inference time features (MUST BE IDENTICAL):**
```python
account_age_days = (timestamp - registration_date) / 86400
```

If you calculate features differently, predictions will be garbage.

### 3. Model is a "Frozen" Snapshot

The model file (`.pkl`) contains:
- Learned tree structures
- Feature importances
- Optimal threshold
- Preprocessing parameters

It does NOT learn from new data during inference. To improve, you must:
1. Collect new transactions
2. Retrain the model
3. Deploy new model

### 4. Probability vs Prediction

```
Probability = 0.37
Threshold = 0.35
Prediction = 1 (FRAUD)

Probability = 0.33
Threshold = 0.35
Prediction = 0 (NOT FRAUD)
```

Same model, different inputs, different outcomes based on threshold.

---

## ⚙️ Configuration & Tuning

### Adjusting the Threshold

If you want to be more aggressive (catch more fraud, more false positives):
```python
# Lower threshold
optimal_threshold = 0.25  # Default is 0.35
```

If you want fewer false alarms (miss some fraud, fewer false positives):
```python
# Higher threshold
optimal_threshold = 0.50
```

### Performance Monitoring

Track these metrics over time:
```python
# Confusion Matrix
True Positives (TP):  Predicted Fraud, Actually Fraud     ✅
True Negatives (TN):  Predicted Legit, Actually Legit     ✅
False Positives (FP): Predicted Fraud, Actually Legit     ❌ (Type I Error)
False Negatives (FN): Predicted Legit, Actually Fraud     ❌ (Type II Error)

# Key Metrics
Precision = TP / (TP + FP)  # Of predicted frauds, how many were correct?
Recall    = TP / (TP + FN)  # Of actual frauds, how many did we catch?
F1 Score  = 2 * (Precision * Recall) / (Precision + Recall)
```

---

## 🚀 Production Deployment Checklist

Before deploying to production:

- [ ] Test inference on 1000+ transactions
- [ ] Validate feature consistency (training vs inference)
- [ ] Set up monitoring/alerting
- [ ] Configure database connection pooling
- [ ] Add API authentication
- [ ] Set up model versioning
- [ ] Create rollback plan
- [ ] Load test API endpoints
- [ ] Set up logging/metrics
- [ ] Document threshold decisions

---

## ❓ Common Questions

**Q: How fast is inference?**
A: < 100ms per transaction (including database fetch + feature engineering + prediction)

**Q: Can I predict on transactions not in the database?**
A: Yes, you'd need to modify the code to accept JSON input directly instead of fetching from DB.

**Q: How often should I retrain?**
A: Monthly or when performance degrades. Fraud patterns evolve.

**Q: Can I use multiple models?**
A: Yes, implement ensemble by loading multiple models and averaging predictions.

**Q: What if a feature is missing?**
A: The feature engineering code has defaults. Missing = 0 or safe value.

**Q: How do I debug wrong predictions?**
A: Check feature values. Often incorrect predictions are due to feature calculation errors.

---

## 📝 Summary

The inference system works by:

1. **Loading** a trained model from disk
2. **Fetching** transaction data from database
3. **Engineering** 62 features (matching training exactly)
4. **Predicting** fraud probability with XGBoost
5. **Classifying** into risk levels
6. **Returning** structured results
7. **Storing** predictions for audit

The key is **feature engineering consistency** - the inference features MUST match training features exactly, or predictions will be unreliable.
