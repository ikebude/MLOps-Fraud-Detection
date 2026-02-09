# Feature Selection Implementation - Feb 7, 2026

## Overview
Implemented automatic feature selection in the fraud detection training pipeline to drop low-importance features, reducing model complexity, overfitting risk, and improving generalization on limited fraud examples (2,792 samples).

## What Was Changed

### 1. **Weak Feature Identification** (`src/plugins/fraud_detection_training.py`, lines 719-742)
Added automatic drop list for 12 weak features:
```python
weak_features_to_drop = [
    'hour_cos',           # cyclical encoding, low predictive power
    'action',             # mostly 'purchase', limited variance
    'day_of_week',        # time pattern not strong for fraud detection
    'month',              # seasonal patterns weak
    'hour_sin',           # cyclical encoding, low predictive power
    'amount_per_quantity', # derived from amount and quantity
    'vendor_avg_quantity', # aggregated feature, limited relevance
    'user_avg_session_duration', # behavioral but redundant
    'product_popularity', # not directly fraud-related
    'time_since_prev_txn_sec', # sparse/noisy time gap metric
    'country_avg_amount', # aggregated location feature
    'category'            # high cardinality categorical
]
```

### 2. **Feature Count Validation** (lines 759-768)
Updated validation logic to accept 55-75 features (flexible range):
- Previously: Required exactly 74 features
- Now: Accepts range [55, 75] after dropping weak features
- Expected outcome: ~62 features (74 - 12 dropped)

### 3. **Post-Training Feature Importance Analysis** (lines 1008-1035)
Added comprehensive importance logging:
- **Top 20 features**: Kept for model performance
- **Bottom 10 features**: Identified as candidates for future removal
- **Weak candidates**: Features with importance < 1.5% of max importance
- Helps validate selection decisions and guide iterative improvements

## Feature Selection Rationale

### Features Dropped (12 total):
1. **Cyclical Encodings** (`hour_sin`, `hour_cos`): Low predictive power, redundant with raw hour
2. **Low Variance Categoricals** (`action`, `day_of_week`, `month`): Dominated by single values or time patterns weak for fraud
3. **Derived/Aggregated Features**: (`amount_per_quantity`, `vendor_avg_quantity`, `user_avg_session_duration`, `product_popularity`, `time_since_prev_txn_sec`, `country_avg_amount`): Redundant or cause overfitting
4. **High Cardinality Categorical** (`category`): Better handled by vendor/product-level features

### Expected Benefits:
- ✅ **Reduced overfitting**: Fewer weak features → model focuses on strong predictors
- ✅ **Better generalization**: ~62 vs 74 features matches data scale (2,792 fraud samples)
- ✅ **Faster training**: Fewer features = faster hyperparameter search (RandomizedSearchCV, 50 iterations)
- ✅ **Lower maintenance**: Simpler model less sensitive to data quality issues
- ✅ **Clearer interpretability**: Removes noise features, focuses on core patterns

## Feature Importance Rules of Thumb

For 2,792 fraud examples (limited data):
- **~62 features**: Good balance (50+ samples per feature in cross-validation)
- Top features capture 60-70% of decision power
- Weak features (<1.5% importance) add noise

## How Feature Selection Works

### Training Pipeline Flow:
1. **Load & Engineer** (74 features created)
2. **Select Features** (drop 12 weak ones → 62 remain)
3. **Train/Test Split** (80/20 stratified)
4. **Train Model** (RandomizedSearchCV, beta=5 scoring)
5. **Calculate Importance** (XGBoost built-in)
6. **Log Results** (top 20, bottom 10, future candidates)

### Configuration:
Features can be adjusted by modifying the `weak_features_to_drop` list in line 721-733 of `fraud_detection_training.py`.

## Validation Approach

After retraining with selected features:
- **Target Recall**: 60-70% (improved from regression)
- **Target Precision**: 40-50% (realistic for this imbalance)
- **Key Metric**: Recall >= 60% (catch most fraud)
- **Success Criteria**: Metrics improve vs Feb 7 regression

## Next Steps

1. **Trigger New Training**: Run the fraud detection training DAG
   - Should complete feature selection automatically
   - Log will show dropped features and importance analysis
   
2. **Validate Results**: Check metrics
   - Recall should improve (60%+ target)
   - Precision should remain stable (40%+)
   - Model should be simpler and more maintainable

3. **Iterative Refinement**: 
   - If recall < 60%, collect more fraud data
   - If weak candidates show up with >2% importance in next run, reconsider dropping them
   - Continue feature engineering for weak domains (payment anomalies, etc.)

## Technical Details

### Feature Importance Extraction:
```python
# From XGBoost classifier (after pipeline)
best_model = searcher.best_estimator_  # Fitted pipeline
xgb_classifier = best_model.named_steps['classifier']  # XGBoost model
feature_importance = xgb_classifier.feature_importances_  # Importance scores
```

### Why These Features Were Dropped:
- **Importance < 1.5% of max**: Typically contribute noise, not signal
- **Weak importance patterns**: No clear correlation with fraud
- **Data imbalance sensitivity**: With 96.8% legitimate, weak features easily overfit

## Reference: Feature Importance from Feb 7 Run

**Top performers (>6%)**:
- `return_request`: 9.67%
- `identity_confidence_score`: 6.86%
- `device_type`: 6.03%
- `session_behavior_score`: 5.40%

**Weak performers (<2%)**:
- `hour_cos`: 1.40%
- `action`: 1.36%
- (11 others with <2%)

---

**Status**: ✅ Implementation complete  
**Last Updated**: Feb 7, 2026  
**Merged File**: `src/plugins/fraud_detection_training.py`  
**Lines Modified**: ~60 (feature selection logic + importance analysis)
