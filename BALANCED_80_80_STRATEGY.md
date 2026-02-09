# Balanced 80%+ Precision & Recall Strategy

**Date:** February 6, 2026  
**Goal:** Achieve 80%+ precision AND 80%+ recall simultaneously

---

## Business Priority: Excellence on Both Metrics

### Core Principle
**Catch fraud AND minimize false alarms: Find the sweet spot where both metrics excel**

- High Recall (80%+): Catch fraud before it happens
- High Precision (80%+): Reduce customer friction and alert fatigue
- Result: Operational efficiency without false alarms

---

## Model Configuration for Dual Metric Success

### 1. **Balanced Class Weight Boosting**
```
scale_pos_weight = base_weight * 2.0 = ~70x
```
- Strong fraud signal without overweighting
- Impact: Model learns to identify fraud while maintaining precision

### 2. **SMOTE Aggressive Oversampling**
```
SMOTE(sampling_strategy=0.8, k_neighbors=3)
```
- Oversample fraud to 80% of legitimate count
- Creates balanced training set (~50/50 after SMOTE)
- Impact: Model learns diverse fraud patterns effectively

### 3. **Hyperparameter Tuning: Balanced Scoring**
```python
scoring = make_scorer(fbeta_score, beta=2)
```
- **beta=2**: Recall weighted 2x over precision (balanced)
- 40 iterations for comprehensive search
- Finds hyperparameters that excel at both metrics

### 4. **Threshold Optimization: Sweet Spot Finding**

**Three-tier strategy:**

```python
# Tier 1: Perfect Sweet Spot
if threshold achieves BOTH precision >= 80% AND recall >= 80%:
    ✓✓✓ USE THIS THRESHOLD (best case)

# Tier 2: Close Compromise  
if no perfect sweet spot exists:
    → Use F1-optimal threshold
    → May achieve 80%+ on test set even if not on train
    
# Tier 3: Fallback
if still below target:
    → Recommend feature improvements
```

**Expected thresholds:** 0.3-0.5 (balanced, not extreme)

### 5. **Enhanced Validation Logging**

```
IF both precision >= 80% AND recall >= 80%:
    ✓✓✓ TARGET ACHIEVED
    
ELSE IF one metric is good:
    ⚠ Specific feedback on what to improve
    
ELSE:
    Need feature quality or data quantity improvements
```

---

## Target Metrics

| Metric | Target | Why |
|--------|--------|-----|
| **Recall** | 80%+ | Catch 80%+ of fraud |
| **Precision** | 80%+ | 80%+ of alerts are real fraud |
| **F1-Score** | 80%+ | Balanced excellence |
| **Threshold** | 0.3-0.5 | Balanced (not too aggressive) |

---

## How This Achieves 80/80

### The Strategy

1. **Balance both metrics during training**
   - Use F2 score (recall weighted 2x, not 5x)
   - Find hyperparameters good at both metrics

2. **Smart threshold selection**
   - Search for intersection where BOTH >= 80%
   - If exists: use it (perfect scenario)
   - If not: use F1-optimal compromise

3. **Validate achievability**
   - Clear logging showing:
     - ✓✓✓ if both metrics hit target
     - ⚠ specific feedback if one misses
     - ✗ what needs improvement if both miss

### Why This Might Work

With 96.8% legitimate / 3.2% fraud data:
- If fraud patterns are **sufficiently distinct**, sweet spot threshold exists
- SMOTE + class weighting helps model learn distinctions
- Test set may outperform training set (no SMOTE on test)

### Why It Might Not Work (and fixes)

| Scenario | Diagnosis | Fix |
|----------|-----------|-----|
| Recall 80%+, Precision <80% | Features not distinct enough | Engineer better features |
| Precision 80%+, Recall <80% | Not enough fraud examples | Collect more data |
| Both <80% | Fundamental data quality issue | Data validation/cleaning or ensemble methods |

---

## Expected Performance

### Previous Model (Feb 6, 14:56)
- Recall: 15.6% ❌
- Precision: 47% ❌
- F1: 0.23 ❌
- Business impact: Miss 84% of fraud

### Target After New Tuning
- Recall: **80%+** ✓
- Precision: **80%+** ✓
- F1: **80%+** ✓
- Business impact: Catch 80%+, low false alarms

---

## Implementation Details

### What Changed from Previous Approaches

| Approach | Scoring | Recall Target | Precision Target | Use Case |
|----------|---------|---------------|------------------|----------|
| Old (Feb 6) | F1 (beta=1) | 15% | 47% | Broken baseline |
| Fraud Prevention | Beta=5 | 85%+ | 60% | Safety first |
| **Balanced 80/80** | **Beta=2** | **80%+** | **80%+** | **Operational excellence** |

### Key Tuning Parameters

```python
# Class imbalance handling
scale_pos_weight = 70x              # Strong fraud penalty

# Training set balancing
SMOTE(sampling_strategy=0.8)       # 80% oversample

# Hyperparameter search
beta=2 (F2 score)                  # Both metrics matter
n_iter=40                          # Comprehensive search

# Threshold optimization
"Sweet spot" finding               # Both 80%+, or F1-best
```

---

## Validation & Next Steps

### Success Criteria

```
PASS:  Precision >= 80% AND Recall >= 80%
       → Deploy immediately
       
WARN:  One metric >= 80%, other >= 75%
       → Investigate and tune
       
FAIL:  Both metrics < 75%
       → Need major improvements
```

### If PASS (Both 80%+)

✓ Deploy immediately with:
- Single-tier system (block at threshold, no manual review)
- Monthly retraining
- Both-metric monitoring

### If WARN (One Metric OK)

Investigate:
- Feature importance: Which features matter?
- Error analysis: What patterns are we missing?
- Threshold tuning: Try slightly different threshold

### If FAIL (Both <75%)

Major improvements needed:
- Feature engineering review
- Data quality validation
- Collect more fraud examples
- Consider ensemble methods

---

## Business Impact

| Scenario | Old | Target | Improvement |
|----------|-----|--------|-------------|
| 1000 fraud cases | 156 caught | 800 caught | **+5.1x** |
| False alarm rate | 53% FP | 20% FP | **-62%** |
| Missed fraud | 844 | 200 | **-76%** |
| Operational cost | High | Low | **Efficient** |

---

## Production Deployment (When 80/80 Achieved)

### Simple Single-tier System

```
if prediction_probability >= threshold:
    BLOCK transaction
else:
    ALLOW transaction
```

**Why this works:**
- Both precision and recall strong
- Minimal false alarms (80%+ precision)
- Minimal missed fraud (80%+ recall)
- No manual review queue needed

---

## Success Indicators

When training completes, look for:

✓ **"✓✓✓ SWEET SPOT FOUND!"** in logs  
✓ **Precision & Recall both 80%+** in metrics  
✓ **F1-score 80%+** (balanced performance)  
✓ **Feature importance** shows clear fraud signals  
✓ **Threshold 0.3-0.5** (reasonable, not extreme)  

---

## Risk Management

| Risk | Mitigation |
|------|-----------|
| Can't achieve both 80% | Have clear fallback (prioritize recall) |
| Threshold drift | Monthly monitoring of both metrics |
| New fraud patterns | Retrain monthly with new data |
| Feature degradation | Recompute feature importance quarterly |

---

## Next Steps

1. **Run training** with new balanced configuration
2. **Check for sweet spot** in logs
3. **Validate both metrics** on test set
4. **If 80/80 achieved:** Deploy single-tier system
5. **If not achieved:** Implement improvement recommendations

---

**Goal:** Both precision AND recall exceeding 80% for operational excellence.
