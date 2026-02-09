"""
Quick validation script for in-container run.
Creates a sklearn-version-compatible OneHotEncoder and runs a lightweight training
(uses `FraudDetectionTraining.engineer_features`).
Run inside the airflow-worker container:
  docker compose exec -T airflow-worker bash -lc "python /opt/airflow/plugins/quick_validate.py"
"""

import os
import sys
import time
import traceback

import numpy as np
import pandas as pd

# Ensure plugins package is importable when running in container
import importlib
import importlib.util

# Try multiple plugin locations and import fallbacks (package import, then file import)
fraud_detection_training = None
plugin_paths = [
    '/opt/airflow/plugins',
    '/usr/local/airflow/plugins',
    os.path.join(os.getcwd(), 'plugins')
]
for p in plugin_paths:
    try:
        if os.path.isdir(p) and p not in sys.path:
            sys.path.insert(0, p)
        # Try importing as a package module first
        try:
            mod = importlib.import_module('plugins.fraud_detection_training')
            fraud_detection_training = mod
            break
        except Exception:
            # Fallback: import the module by file path
            fp = os.path.join(p, 'fraud_detection_training.py')
            if os.path.isfile(fp):
                spec = importlib.util.spec_from_file_location('fraud_detection_training', fp)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                fraud_detection_training = mod
                break
    except Exception:
        continue

if fraud_detection_training is None:
    # Don't raise during Airflow plugin import - just warn.
    # The quick-validate script will attempt an explicit import when executed directly.
    import logging as _logging
    _logging.getLogger(__name__).warning('Could not locate fraud_detection_training in plugin paths: %s', ','.join(plugin_paths))
    fraud_detection_training = None

# sklearn imports
from sklearn.model_selection import train_test_split, RandomizedSearchCV, StratifiedKFold
from sklearn.metrics import precision_score, recall_score, f1_score, average_precision_score, precision_recall_curve
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import FunctionTransformer
from xgboost import XGBClassifier
from imblearn.pipeline import Pipeline as ImbPipeline
from imblearn.over_sampling import SMOTE

# Compatibility helper for OneHotEncoder across scikit-learn versions
def make_onehot(handle_unknown='ignore'):
    try:
        from sklearn.preprocessing import OneHotEncoder
    except Exception:
        raise
    # Try newer API
    try:
        return OneHotEncoder(handle_unknown=handle_unknown, sparse_output=False)
    except TypeError:
        # Fallback to older API
        return OneHotEncoder(handle_unknown=handle_unknown, sparse=False)


def main():
    try:
        import psycopg2
        db_host = os.getenv('TRANSACTIONS_HOST','postgres')
        db_port = int(os.getenv('TRANSACTIONS_PORT','5432'))
        db_name = os.getenv('TRANSACTIONS_DB','transactions_db')
        db_user = os.getenv('TRANSACTIONS_USER','fraud_training')
        db_pass = os.getenv('TRANSACTIONS_PASSWORD','training_password')

        conn = psycopg2.connect(host=db_host, port=db_port, dbname=db_name, user=db_user, password=db_pass)
        query = 'SELECT transaction_id, order_id, user_id, full_name, email, phone_number, gender, age, registration_date, account_status, session_id, timestamp, action, device_id, ip_address, location, country, device_type, browser, geo_location, session_duration, product_id, product_name, category, price, discount, vendor_id, quantity, payment_method, payment_status, amount, currency, delivery_address, return_request, refund_status, rating, is_fraud, fraud_type, created_at FROM transactions ORDER BY timestamp DESC LIMIT 5000'
        df = pd.read_sql_query(query, conn)
        conn.close()
        print('Pulled rows:', len(df))
    except Exception as e:
        print('DB read failed:', e)
        traceback.print_exc()
        return 1

    # Engineer features using the plugin's function
    Trainer = fraud_detection_training.FraudDetectionTraining
    trainer = Trainer.__new__(Trainer)
    df_eng = Trainer.engineer_features(trainer, df)
    print('Engineered columns:', len(df_eng.columns))

    # Prepare features
    exclude_cols = ['transaction_id','order_id','user_id','full_name','email','phone_number','session_id','device_id','ip_address','product_id','product_name','delivery_address','geo_location','vendor_id','is_fraud','fraud_type','created_at','timestamp','registration_date']
    feature_cols = [c for c in df_eng.columns if c not in exclude_cols]
    X = df_eng[feature_cols].copy().fillna(0)
    y = df_eng['is_fraud'].copy()
    print('Features used:', len(feature_cols))

    # Train/test split
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

    # Identify categorical columns
    categorical_cols = X.select_dtypes(include=['object','category']).columns.tolist()
    print('Categorical cols:', len(categorical_cols))

    # --- Diagnostics: class balance and preprocessing checks ---
    print('Class distribution (train):', y_train.value_counts().to_dict())
    print('Class distribution (test):', y_test.value_counts().to_dict())

    # Build a simple preprocessor to inspect encoded feature space
    if categorical_cols:
        encoder = make_onehot()
        preprocessor = ColumnTransformer(transformers=[('cat', encoder, categorical_cols)], remainder='passthrough')
        preprocessor.fit(X_train)
        try:
            feat_names = list(preprocessor.get_feature_names_out())
        except Exception:
            # older sklearn versions
            try:
                feat_names = preprocessor.transformers_[0][1].get_feature_names(categorical_cols)
            except Exception:
                feat_names = None
        print('Transformed feature count (after preprocessor):', len(feat_names) if feat_names is not None else 'unknown')
    else:
        preprocessor = FunctionTransformer(func=lambda x: x, validate=False)
        feat_names = None

    # Apply preprocessor and inspect SMOTE resampling behavior
    try:
        X_train_trans = preprocessor.transform(X_train)
    except Exception:
        X_train_trans = preprocessor.fit_transform(X_train)

    from imblearn.over_sampling import SMOTE as SMOTE_raw
    try:
        sm = SMOTE_raw(random_state=42)
        X_res, y_res = sm.fit_resample(X_train_trans, y_train)
        print('After SMOTE resample shape:', X_res.shape, '->', 'pos_count_resampled=', int(y_res.sum()))
    except Exception as e:
        print('SMOTE resample failed:', e)

    # Compute scale_pos_weight
    pos = int(y_train.sum())
    neg = int(y_train.shape[0] - pos)
    scale_pos_weight = float(neg / pos) if pos > 0 else 1.0
    print(f'Computed scale_pos_weight={scale_pos_weight:.4f} (neg={neg}, pos={pos})')

    # Quick baseline training variants to compare behavior
    from xgboost import XGBClassifier as XGBClf
    from sklearn.metrics import precision_score, recall_score, f1_score, average_precision_score

    def eval_and_print(clf, Xtr, ytr, Xte, yte, desc='model'):
        clf.fit(Xtr, ytr)
        proba = clf.predict_proba(Xte)[:,1]
        pred = (proba >= 0.5).astype(int)
        prec = precision_score(yte, pred, zero_division=0)
        rec = recall_score(yte, pred, zero_division=0)
        f1 = f1_score(yte, pred, zero_division=0)
        aucpr = average_precision_score(yte, proba)
        print(f"{desc} -> precision={prec:.4f}, recall={rec:.4f}, f1={f1:.4f}, auc_pr={aucpr:.4f}")
        import numpy as np
        print('proba quantiles:', np.quantile(proba, [0.0,0.25,0.5,0.75,1.0]))

    # Baseline A: XGBoost with scale_pos_weight (no SMOTE)
    try:
        xb_a = XGBClf(eval_metric='aucpr', random_state=42, n_estimators=50, tree_method='hist', scale_pos_weight=scale_pos_weight, use_label_encoder=False)
        # need to pass through preprocessor manually
        Xtr_a = X_train_trans
        try:
            Xte_a = preprocessor.transform(X_test)
        except Exception:
            Xte_a = preprocessor.transform(X_test)
        eval_and_print(xb_a, Xtr_a, y_train, Xte_a, y_test, desc='XGB scale_pos_weight only')
    except Exception as e:
        print('Baseline A failed:', e)

    # Baseline B: SMOTE + XGBoost (no scale_pos_weight)
    try:
        xb_b = XGBClf(eval_metric='aucpr', random_state=42, n_estimators=50, tree_method='hist', use_label_encoder=False)
        X_res_b, y_res_b = SMOTE_raw(random_state=42).fit_resample(X_train_trans, y_train)
        eval_and_print(xb_b, X_res_b, y_res_b, Xte_a, y_test, desc='SMOTE only')
    except Exception as e:
        print('Baseline B failed:', e)

    # Baseline C: SMOTE + XGBoost with scale_pos_weight
    try:
        xb_c = XGBClf(eval_metric='aucpr', random_state=42, n_estimators=50, tree_method='hist', scale_pos_weight=scale_pos_weight, use_label_encoder=False)
        X_res_c, y_res_c = SMOTE_raw(random_state=42).fit_resample(X_train_trans, y_train)
        eval_and_print(xb_c, X_res_c, y_res_c, Xte_a, y_test, desc='SMOTE + scale_pos_weight')
    except Exception as e:
        print('Baseline C failed:', e)

    # Preprocessor using compatibility helper
    if categorical_cols:
        encoder = make_onehot()
        preprocessor = ColumnTransformer(transformers=[('cat', encoder, categorical_cols)], remainder='passthrough')
    else:
        preprocessor = FunctionTransformer(func=lambda x: x, validate=False)

    # Light XGBoost configuration
    xgb = XGBClassifier(eval_metric='aucpr', random_state=42, n_estimators=50, n_jobs=1, tree_method='hist')

    pipeline = ImbPipeline([('preprocessor', preprocessor), ('smote', SMOTE(random_state=42)), ('classifier', xgb)])

    param_dist = {'classifier__max_depth': [3,5], 'classifier__learning_rate': [0.05,0.1], 'classifier__subsample':[0.8], 'classifier__colsample_bytree':[0.8]}

    searcher = RandomizedSearchCV(pipeline, param_distributions=param_dist, n_iter=5, scoring='precision', cv=StratifiedKFold(n_splits=3, shuffle=True), n_jobs=1, refit=True, random_state=42, verbose=1)

    start = time.time()
    searcher.fit(X_train, y_train)
    print('Search done in', round(time.time()-start,2),'s')
    best = searcher.best_estimator_
    print('Best params:', searcher.best_params_)

    proba = best.predict_proba(X_test)[:,1]
    pred_default = (proba >= 0.5).astype(int)
    prec_def = precision_score(y_test, pred_default, zero_division=0)
    rec_def = recall_score(y_test, pred_default, zero_division=0)
    f1_def = f1_score(y_test, pred_default, zero_division=0)
    aucpr = average_precision_score(y_test, proba)
    print('\nDefault threshold metrics: precision={:.4f}, recall={:.4f}, f1={:.4f}, auc_pr={:.4f}'.format(prec_def, rec_def, f1_def, aucpr))

    precision_arr, recall_arr, thresholds_arr = precision_recall_curve(y_train, best.predict_proba(X_train)[:,1])
    desired = 0.6
    valid = [i for i,p in enumerate(precision_arr[:-1]) if p>=desired]
    if valid and len(thresholds_arr)>0:
        best_idx = max(valid, key=lambda i: recall_arr[i])
        thresh = thresholds_arr[best_idx]
    else:
        f1s = [2*(p*r)/(p+r) if (p+r)>0 else 0 for p,r in zip(precision_arr[:-1], recall_arr[:-1])]
        thresh = thresholds_arr[np.argmax(f1s)] if len(thresholds_arr)>0 else 0.5

    pred_thresh = (proba >= thresh).astype(int)
    prec_t = precision_score(y_test, pred_thresh, zero_division=0)
    rec_t = recall_score(y_test, pred_thresh, zero_division=0)
    f1_t = f1_score(y_test, pred_thresh, zero_division=0)
    print('Threshold chosen:', round(thresh,4))
    print('Threshold metrics: precision={:.4f}, recall={:.4f}, f1={:.4f}'.format(prec_t, rec_t, f1_t))

    # Print top importances
    clf = best.named_steps['classifier']
    try:
        feat_names = list(best.named_steps['preprocessor'].get_feature_names_out())
    except Exception:
        feat_names = None
    if hasattr(clf, 'feature_importances_'):
        imps = clf.feature_importances_
        if feat_names is not None and len(imps)==len(feat_names):
            pairs = sorted(zip(feat_names, imps), key=lambda x:x[1], reverse=True)
        else:
            pairs = sorted([(f'feat_{i}',float(v)) for i,v in enumerate(imps)], key=lambda x:x[1], reverse=True)
        print('\nTop importances:')
        for n,v in pairs[:10]:
            print(n, round(v,6))

    print('\nDone')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
