# FraudGuard Dashboard Updates - Risk Score & Risk Level Enhancements

## Date: 2026-02-11

## Changes Made

### 1. **Added Risk Level Column to Transactions Page**
   - **File**: `fraudguard/templates/transactions.html`
   - **Changes**:
     - Added "Risk Level" column header to the table
     - Updated JavaScript to display risk_level with color-coded badges:
       - **CRITICAL**: Red background (bg-red-100 text-red-800 font-bold)
       - **HIGH**: Orange background (bg-orange-100 text-orange-800)
       - **MEDIUM**: Yellow background (bg-yellow-100 text-yellow-800)
       - **LOW**: Blue background (bg-blue-100 text-blue-800)
       - **MINIMAL**: Green background (bg-green-100 text-green-800)
       - **UNKNOWN**: Gray background (fallback)
     - Added debug console logging to verify fraud_probability and risk_score values
     - Updated colspan from 7 to 8 for details row
     - Added tooltip to Risk Score showing exact fraud probability percentage

### 2. **Added Risk Level Column to Live Fraud Transaction Feed**
   - **File**: `fraudguard/templates/dashboard.html`
   - **Changes**:
     - Added "Risk Level" column header to the Live Fraud Feed table
     - Updated loading placeholder colspan from 8 to 9

   - **File**: `fraudguard/static/js/dashboard.js`
   - **Changes**:
     - Updated `buildTransactionRows()` function to include risk_level column
     - Added same color-coded badge styling as Transactions page
     - Added debug console logging for fraud_probability verification
     - Updated colspan from 6 to 9 for details row
     - Added tooltip to Risk Score showing exact fraud probability percentage
     - Added location column display (was missing before)
     - Added "View" button in Details column

## Debug Features Added

### Console Logging
Both pages now log transaction data to the browser console:
```javascript
console.log('Transaction:', txn.id, 'fraud_probability:', txn.fraud_probability, 'risk_score:', riskScore, 'risk_level:', txn.risk_level);
```

This will help verify:
1. If `fraud_probability` is being passed from the backend
2. If `risk_score` is being calculated correctly (fraud_probability * 100)
3. If `risk_level` is present in the data

## Expected Data Flow

### Backend (fraudguard/app.py)
```python
# Line 412: Risk score calculation
risk_score = int(fraud_prob * 100)

# Line 450-451: Data passed to frontend
'risk_score': risk_score,
'fraud_probability': float(fraud_prob),
'risk_level': risk_level  # From database
```

### Frontend Display
- **Risk Score**: 0-100 numeric score (calculated from fraud_probability)
- **Risk Level**: Text badge (CRITICAL/HIGH/MEDIUM/LOW/MINIMAL from database)

## Testing Instructions

1. **Open Browser Console** (F12 → Console tab)
2. **Navigate to Dashboard** or **Transactions Page**
3. **Check Console Logs** for transaction data:
   - Verify `fraud_probability` is not null/undefined
   - Verify `risk_score` matches `fraud_probability * 100`
   - Verify `risk_level` is present

4. **Visual Verification**:
   - Risk Score column should show values like "85/100" with color coding
   - Risk Level column should show badges like "CRITICAL", "HIGH", etc.
   - Hover over Risk Score to see exact fraud probability in tooltip

## Troubleshooting

### If Risk Score shows "0/100" for all transactions:
1. Check console logs - is `fraud_probability` 0.0 or null?
2. Verify database has actual fraud_probability values
3. Check if inference service is running and scoring transactions

### If Risk Level shows "UNKNOWN":
1. Check if `risk_level` column exists in fraud_predictions table
2. Verify inference service is populating risk_level field
3. Check backend query includes risk_level in SELECT statement

## Files Modified

1. `fraudguard/templates/transactions.html` - Added Risk Level column
2. `fraudguard/templates/dashboard.html` - Added Risk Level column header
3. `fraudguard/static/js/dashboard.js` - Updated row rendering with Risk Level

## Next Steps

1. Monitor browser console logs to verify data is flowing correctly
2. If fraud_probability is 0, investigate inference service
3. If risk_level is missing, check database schema and inference service
