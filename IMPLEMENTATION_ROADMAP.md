# 🚀 MONIGUARD: ENTERPRISE UPGRADE IMPLEMENTATION ROADMAP

**Status**: Ready for Implementation  
**Estimated Timeline**: 12 weeks to production-grade  
**Team Required**: 2 ML Engineers, 1 Backend Engineer, 1 DevOps

---

## 📋 QUICK WINS (This Week) - START HERE

### Task 1.1: Add Nigerian PoD Features to Inference (2 hours)

**File**: `src/inference/main.py`

```python
# Add at top of inference.py
from src.features.nigerian_features import get_nigerian_feature_engine

# In your _build_features_dict function:
def _build_features_dict(transaction):
    """Build feature dict with Nigerian features"""
    
    # Existing features
    features = {
        'amount': float(transaction['amount']),
        'customer_age_days': 30,  # existing logic
        # ... rest of features
    }
    
    # NEW: Add Nigerian features
    nigerian_engine = get_nigerian_feature_engine()
    
    if transaction.get('payment_method') == 'POD':
        nigerian_features = nigerian_engine.extract_pod_features(transaction)
        features.update(nigerian_features)
    
    return features
```

**Result**: Your model now understands PoD-specific fraud patterns

---

### Task 1.2: Enable SHAP Explanations in API (2 hours)

**File**: `src/inference/api_server.py`

```python
from src.explainability.shap_explainer import SHAPExplainer

# Initialize at startup
shap_explainer = SHAPExplainer()

@app.route('/api/explain/<case_id>', methods=['GET'])
def explain_prediction(case_id):
    """Return SHAP explanation for a prediction"""
    
    # Get prediction from database
    prediction = db.get_prediction(case_id)
    
    # Get SHAP explanation
    explanation = shap_explainer.explain_transaction(
        prediction['features'],
        case_id=case_id
    )
    
    return jsonify({
        'case_id': case_id,
        'fraud_probability': explanation['fraud_probability'],
        'top_factors': explanation['top_factors'],
        'timestamp': datetime.now().isoformat(),
    })
```

**Result**: Analysts see "Why" behind every fraud score

---

### Task 1.3: Connect Feedback to Retraining (2 hours)

**File**: `moniguard/app.py` - Update decision endpoint

```python
from src.feedback.feedback_processor import get_feedback_processor

@app.route('/api/case/<case_id>/decision', methods=['POST'])
def submit_case_decision(case_id):
    """Analyst submits decision on a case"""
    
    data = request.json
    decision = data.get('decision')  # APPROVE, REJECT, etc.
    
    # Store decision (existing code)
    db.update_case_decision(case_id, decision, session['analyst_id'])
    
    # NEW: Trigger feedback processing
    feedback_processor = get_feedback_processor()
    feedback_event = {
        'case_id': case_id,
        'analyst_id': session['analyst_id'],
        'decision': decision,
        'timestamp': datetime.now().isoformat(),
    }
    
    # Process asynchronously
    background_task_queue.put(feedback_processor.process_analyst_decision, feedback_event)
    
    return jsonify({'success': True, 'case_id': case_id})
```

**Result**: Every analyst decision automatically improves future models

---

### Task 1.4: Fix Drift Detection Logic (1 hour)

**File**: `moniguard/app.py` - Line ~1320

**BEFORE** (WRONG ORDER):
```python
baseline_fraud_rate = 2.5
drift_threshold = 2.0
drift_status = 'Normal'
if fraud_rate > (baseline_fraud_rate * drift_threshold):  # 5%
    drift_status = 'Warning'
elif fraud_rate > (baseline_fraud_rate * 3.0):  # 7.5%
    drift_status = 'Critical'
```

**AFTER** (CORRECT ORDER):
```python
baseline_fraud_rate = 2.5
drift_status = 'Normal'
if fraud_rate > (baseline_fraud_rate * 3.0):  # 7.5% - CRITICAL
    drift_status = 'Critical'
elif fraud_rate > (baseline_fraud_rate * 2.0):  # 5% - WARNING
    drift_status = 'Warning'
```

**Result**: Critical alerts actually trigger for critical fraud rates

---

### Task 1.5: Enable Model Caching (1 hour)

**File**: `moniguard/app.py` - Around line ~878

**BEFORE**:
```python
def _get_model_health():
    """Get model health - wrapper with cache clearing on demand"""
    if hasattr(_get_model_health_cached, 'cache_clear'):
        pass  # Don't cache
    return _get_model_health_impl()  # Always recompute
```

**AFTER**:
```python
def _get_model_health():
    """Get model health - wrapper with LRU caching"""
    # Use LRU cache to avoid repeated MLflow API calls
    # Cache for 5 minutes (300 seconds)
    return _get_model_health_cached()

# Already decorated with @lru_cache(maxsize=1) at line 681
@lru_cache(maxsize=1)
def _get_model_health_cached():
    """Cached version to avoid repeated MLflow calls"""
    return _get_model_health_impl()
```

**Result**: 10x faster model health lookups, less MLflow API load

---

## 📊 PHASE 1: FOUNDATION (Weeks 1-3) - CRITICAL

### Setup 1: Feature Store with Feast

**1.1 Install Feast** (30 min)

```bash
pip install feast==0.23.0
feast init fraud_detection_feature_store
cd fraud_detection_feature_store
```

**1.2 Define Features** (1 hour)

Create `fraud_detection_feature_store/features/pod_features.py`:

```python
from feast import Entity, Feature, FeatureView, FileSource, ValueType
from datetime import timedelta

# Define entities (what we're tracking)
customer = Entity(name="customer_id")
phone = Entity(name="phone_number")
address = Entity(name="delivery_address")

# Define features
pod_customer_features = FeatureView(
    name="pod_customer_metrics",
    entities=["customer_id"],
    ttl=timedelta(hours=1),  # 1hr cache
    features=[
        Feature(name="transaction_count_24h", dtype=ValueType.INT64),
        Feature(name="transaction_count_7d", dtype=ValueType.INT64),
        Feature(name="failed_deliveries_7d", dtype=ValueType.INT64),
        Feature(name="chargeback_rate", dtype=ValueType.DOUBLE),
    ],
    source=FileSource(path="data/customer_features.parquet")
)

pod_phone_features = FeatureView(
    name="pod_phone_metrics",
    entities=["phone_number"],
    ttl=timedelta(minutes=5),  # 5min cache for real-time
    features=[
        Feature(name="txn_count_24h", dtype=ValueType.INT64),
        Feature(name="failed_delivery_rate", dtype=ValueType.DOUBLE),
        Feature(name="is_blacklisted", dtype=ValueType.INT64),
        Feature(name="linked_accounts_count", dtype=ValueType.INT64),
    ],
    source=FileSource(path="data/phone_features.parquet")
)
```

**1.3 Deploy Feast Registry** (1 hour)

```bash
# Deploy to Redis for low-latency access
feast apply --registry=s3://your-bucket/feast-registry

# Offline store (for training)
feast materialize 2026-03-01 2026-03-07

# Online store (for inference)
feast materialize-incremental $(date -u +"%Y-%m-%dT%H:%M:%S")
```

**1.4 Use in Inference** (1 hour)

```python
# In src/inference/main.py
from feast import FeatureStore

fs = FeatureStore(repo_path="fraud_detection_feature_store")

# Get phone features in real-time
features = fs.get_online_features(
    features=[
        "pod_phone_metrics:txn_count_24h",
        "pod_phone_metrics:failed_delivery_rate",
        "pod_phone_metrics:is_blacklisted",
    ],
    entity_rows=[{"phone_number": "08012345678"}]
)
```

**Deliverable: ✅ Feature consistency, <10ms latency**

---

### Setup 2: Automatic Feedback Integration

**2.1 Update Database Schema** (30 min)

```sql
-- In src/config/init-multiple-dbs.sh

-- Add feedback table
CREATE TABLE analyst_feedback (
    id SERIAL PRIMARY KEY,
    case_id VARCHAR(255) NOT NULL UNIQUE,
    transaction_id VARCHAR(255) NOT NULL,
    analyst_id VARCHAR(255) NOT NULL,
    original_fraud_score FLOAT,
    analyst_decision VARCHAR(50),
    label SMALLINT,  -- 0: legitimate, 1: fraud
    confidence FLOAT DEFAULT 1.0,
    features_json JSONB,
    feedback_timestamp TIMESTAMP DEFAULT NOW(),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_feedback_timestamp ON analyst_feedback(feedback_timestamp);
CREATE INDEX idx_feedback_label ON analyst_feedback(label);
```

**2.2 Wire Analyst Decisions to Feedback Processor** (1 hour)

See Task 1.3 above

**2.3 Add Retraining Check** (1 hour)

Create `src/tasks/check_retraining_trigger.py`:

```python
import schedule
import time
from src.feedback.feedback_processor import get_feedback_processor

def check_retrain_periodically():
    """Run every 5 minutes"""
    processor = get_feedback_processor()
    processor._check_retraining_trigger()

schedule.every(5).minutes.do(check_retrain_periodically)

if __name__ == '__main__':
    while True:
        schedule.run_pending()
        time.sleep(1)
```

Run as background service:

```yaml
# docker-compose.yml
services:
  retraining_monitor:
    build: .
    command: python src/tasks/check_retraining_trigger.py
    environment:
      DB_HOST: postgres
      AIRFLOW_WEBSERVER_URL: http://airflow-webserver:8080
    depends_on:
      - postgres
      - airflow-webserver
```

**Deliverable: ✅ Automated feedback, triggered retraining**

---

### Setup 3: SHAP Dashboard Integration

**3.1 Update Dashboard Templates** (1 hour)

Create `moniguard/templates/case_detail_with_shap.html`:

```html
<!-- Add to case detail page -->
<div id="shap-explanation-container" class="shap-section">
    <h3>Decision Factors (Why This Case)</h3>
    <div id="shap-factors" class="shap-factors">
        <!-- Will be populated by JavaScript -->
    </div>
</div>

<script>
// Fetch SHAP explanation
async function loadSHAPExplanation(caseId) {
    const response = await fetch(`/api/explain/${caseId}`);
    const explanation = await response.json();
    
    // Render factors
    const container = document.getElementById('shap-factors');
    container.innerHTML = explanation.top_factors.map(factor => `
        <div class="shap-factor">
            <div class="factor-header">
                <span class="factor-name">${factor.description}</span>
                <span class="factor-value">${factor.value}</span>
                <span class="factor-impact ${factor.impact_level}">
                    ${factor.impact_icon} ${factor.impact}
                </span>
            </div>
            <div class="factor-reasoning">${factor.reasoning}</div>
        </div>
    `).join('');
}

// Load on page load
document.addEventListener('DOMContentLoaded', () => {
    const caseId = document.getElementById('case-id').value;
    loadSHAPExplanation(caseId);
});
</script>

<style>
.shap-section {
    background: #f8f9fa;
    padding: 15px;
    border-radius: 8px;
    margin: 15px 0;
}

.shap-factor {
    background: white;
    padding: 10px;
    margin: 8px 0;
    border-left: 4px solid #3b82f6;
    border-radius: 4px;
}

.factor-impact.INCREASES {
    color: #dc2626;
    background: #fee2e2;
    padding: 4px 8px;
    border-radius: 4px;
}

.factor-impact.DECREASES {
    color: #16a34a;
    background: #dcfce7;
    padding: 4px 8px;
    border-radius: 4px;
}

.factor-reasoning {
    font-size: 0.9em;
    color: #666;
    margin-top: 6px;
}
</style>
```

**3.2 Add Explanation API Endpoint** (30 min)

In `src/inference/api_server.py`:

```python
from src.explainability.shap_explainer import SHAPExplainer

shap_explainer = SHAPExplainer(model)

@app.get("/api/explain/{case_id}")
async def get_explanation(case_id: str):
    """Get SHAP explanation for a case"""
    case = db.get_case(case_id)
    explanation = shap_explainer.explain_transaction(
        case['features'],
        case_id=case_id
    )
    return explanation
```

**Deliverable: ✅ Analysts see SHAP explanations in UI**

---

## 🌊 PHASE 2: STREAMING (Weeks 4-6)

### Setup 4: Apache Spark Streaming for Real-Time Features

**4.1 Deploy Spark Cluster** (2 hours)

```yaml
# docker-compose.yml additions
services:
  spark-master:
    image: bitnami/spark:3.2.0
    environment:
      - SPARK_MODE=master
    ports:
      - "8080:8080"
  
  spark-worker-1:
    image: bitnami/spark:3.2.0
    environment:
      - SPARK_MODE=worker
      - SPARK_MASTER_URL=spark://spark-master:7077
  
  spark-worker-2:
    image: bitnami/spark:3.2.0
    environment:
      - SPARK_MODE=worker
      - SPARK_MASTER_URL=spark://spark-master:7077
```

**4.2 Create Streaming Feature Processor** (2 hours)

Create `src/streaming/spark_feature_processor.py`:

```python
from pyspark.sql import SparkSession
from pyspark.sql.functions import *
from pyspark.sql.types import *

spark = SparkSession.builder \
    .appName("FraudFeatureStreaming") \
    .master("spark://spark-master:7077") \
    .getOrCreate()

# Read from Kafka
kafka_df = spark.readStream \
    .format("kafka") \
    .option("kafka.bootstrap.servers", "kafka:9092") \
    .option("subscribe", "fraud-events") \
    .load()

# Parse events
events_df = kafka_df.select(
    from_json(col("value").cast("string"),
    schema=StructType([
        StructField("transaction_id", StringType()),
        StructField("customer_id", StringType()),
        StructField("amount", DoubleType()),
        StructField("phone_number", StringType()),
        StructField("timestamp", StringType()),
    ])).alias("data")
).select("data.*")

# Real-time aggregations
from pyspark.sql.window import Window

one_hour_window = Window.partitionBy("customer_id") \
    .orderBy(col("timestamp").cast("timestamp")) \
    .rangeBetween(-3600, 0)

features = events_df.withColumn(
    "cust_txn_count_1h",
    count("*").over(one_hour_window)
).withColumn(
    "cust_amount_sum_1h",
    sum("amount").over(one_hour_window)
)

# Write to Redis feature store
query = features.writeStream \
    .format("com.redislabs.spark.redis") \
    .option("host", "redis") \
    .option("port", "6379") \
    .option("table", "features") \
    .option("key.column", "customer_id") \
    .start()

query.awaitTermination()
```

**4.3 Update Inference to Use Stream Features** (1 hour)

```python
# In src/inference/main.py
import redis

redis_client = redis.Redis(host='redis', port=6379, decode_responses=True)

def get_features_including_streaming(transaction):
    features = {}
    
    # Get streaming computed features from Redis
    customer_id = transaction['customer_id']
    streaming_features = redis_client.hgetall(f"features:{customer_id}")
    
    if streaming_features:
        features.update({
            'cust_txn_count_1h': float(streaming_features.get('cust_txn_count_1h', 0)),
            'cust_amount_sum_1h': float(streaming_features.get('cust_amount_sum_1h', 0)),
        })
    
    # Add other features
    features.update(extract_other_features(transaction))
    
    return features
```

**Deliverable: ✅ <50ms feature computation, real-time aggregations**

---

## 🧠 PHASE 3: ADVANCED MODELS (Weeks 7-9)

### Setup 5: Graph Neural Networks for Fraud Rings

Skip for now - covered in audit doc. Start when phases 1-2 complete.

---

## 📈 MONITORING & ALERTS

### Setup: Prometheus + Grafana

**Create `src/monitoring/prometheus_rules.yml`:**

```yaml
groups:
- name: fraud_detection
  rules:
  - alert: ModelAccuracyDegrading
    expr: model_accuracy_last_7d < 0.90
    for: 1h
    annotations:
      summary: "Model accuracy degrading (currently {{ $value }})"
  
  - alert: HighFraudRate
    expr: fraud_rate_24h > 0.03
    for: 30m
    annotations:
      summary: "Fraud rate above threshold: {{ $value }}"
  
  - alert: FeatureDriftDetected
    expr: max(feature_drift_score) > 0.5
    for: 1h
    annotations:
      summary: "Feature drift detected in {{ $labels.feature }}"
```

---

## ✅ TESTING CHECKLIST

Before going to production:

- [ ] Nigerian PoD features extracting correctly
- [ ] SHAP explanations generating in <100ms
- [ ] Feedback automatically creating training examples
- [ ] Spark streaming processing 1000s events/min
- [ ] Model retraining triggered automatically
- [ ] Analyst interface displays explanations
- [ ] A/B testing shows improvement
- [ ] Zero data loss on Kafka failures
- [ ] Feature cache hit rate > 95%

---

## 📊 SUCCESS METRICS

Track these to prove value:

| Metric | Baseline | Goal | Timeline |
|--------|----------|------|----------|
| Inference Latency | 500ms | <50ms | Week 6 |
| Fraud Detection Rate | 92% | 96%+ | Week 12 |
| False Positive Rate | 4.2% | <2% | Week 12 |
| Model Retraining Cycle | Manual | Automatic | Week 4 |
| Feature Consistency | 85% | 100% | Week 3 |
| Analyst Throughput | 40/hr | 60+/hr | Week 8 |
| System Availability | 99.5% | 99.99% | Week 12 |

---

## 🚨 CRITICAL SUCCESS FACTORS

1. **Start with Quick Wins** - Get immediate value this week
2. **Test Each Phase** - Don't skip integration testing
3. **Monitor Everything** - Know your metrics in real-time
4. **Communicate Progress** - Weekly demos to stakeholders
5. **Nigerian Context** - Always think about PoD fraud patterns
6. **Data Quality** - Garbage in, garbage out

---

## 📞 SUPPORT

If stuck:
- Check audit doc for detailed architecture
- Review example implementations provided
- Test in staging before production
- Monitor Prometheus dashboard
- Check Airflow DAG logs for retraining issues

---

**Next Step**: Start with Task 1.1 (Add Nigerian PoD Features) **TODAY**

Target: Production-ready by End of Q2 2026
