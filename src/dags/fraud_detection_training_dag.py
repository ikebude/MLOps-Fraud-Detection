from datetime import datetime, timedelta

from airflow import DAG
from airflow.exceptions import AirflowException
try:
    from airflow.providers.standard.operators.python import PythonOperator
except ImportError:
    from airflow.operators.python import PythonOperator
from airflow.models import Variable
from airflow.utils.trigger_rule import TriggerRule
import logging
import os
import glob
import yaml
import sys
import time

sys.path.insert(0, '/opt/airflow/plugins')

# Import Prometheus metrics
try:
    from prometheus_client import Counter, Histogram, Gauge
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

logger = logging.getLogger(__name__)

# Initialize Prometheus metrics if available
if PROMETHEUS_AVAILABLE:
    try:
        training_duration = Histogram(
            'fraud_detection_training_duration_seconds',
            'Time taken for training pipeline',
            buckets=(60, 300, 600, 1200, 3600)
        )
        training_accuracy = Gauge(
            'fraud_detection_training_accuracy',
            'Model accuracy from latest training'
        )
        training_precision = Gauge(
            'fraud_detection_training_precision',
            'Model precision from latest training'
        )
        training_recall = Gauge(
            'fraud_detection_training_recall',
            'Model recall from latest training'
        )
        training_f1_score = Gauge(
            'fraud_detection_training_f1_score',
            'Model F1 score from latest training'
        )
        training_roc_auc = Gauge(
            'fraud_detection_training_roc_auc',
            'Model ROC AUC from latest training'
        )
        training_errors_total = Counter(
            'fraud_detection_training_errors_total',
            'Total number of training errors',
            ['error_type']
        )
        training_runs_total = Counter(
            'fraud_detection_training_runs_total',
            'Total number of training runs',
            ['status']
        )
    except ValueError:
        # Metrics already registered (module re-import); reuse existing registry silently
        pass

# Default DAG args; keep lightweight so daemon can schedule easily
default_args = {
    'owner': 'datamasterylab.com',
    'depends_on_past': False,
    'start_date': datetime(2025, 3, 3),
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}


def _load_config(config_path: str = None):
    """Load YAML config from a path. Path can be provided via Airflow Variable `config_path`.

    Returns a dict (possibly empty) on failure.
    Note: Variable.get() is called at runtime, not during DAG parsing.
    """
    try:
        # Try to get from Variable at runtime (not during DAG parse)
        try:
            cfg_path = config_path or Variable.get('config_path', default_var='/app/config.yaml')
        except Exception:
            # If Variable.get() fails (e.g., during DAG parse), use default
            cfg_path = config_path or '/app/config.yaml'
        
        if os.path.exists(cfg_path):
            with open(cfg_path, 'r') as f:
                return yaml.safe_load(f) or {}
        else:
            logger.warning('Config file not found at %s; using defaults/Variables', cfg_path)
            return {}
    except Exception as e:
        logger.exception('Failed to load config: %s', e)
        return {}


def _train_model(**context):
    """Airflow wrapper for the training task with Prometheus metrics.

    This version reads the transactions table name from an Airflow Variable called
    `transactions_table`. If not set, it will fall back to `transactions` or the
    value from `config.yaml` (if present). This allows you to adapt the DAG to
    environments where the transactions table name differs.
    """
    start_time = time.time()
    
    # load config (Variable overrides file)
    cfg = _load_config()
    transactions_table = Variable.get('transactions_table', default_var=cfg.get('transactions_table', 'transactions'))

    try:
        logger.info('Initializing fraud detection training (transactions_table=%s)', transactions_table)
        # Import at runtime so DAG parse doesn't require heavy deps
        # Import from plugins folder where the actual implementation lives
        from fraud_detection_training import FraudDetectionTraining

        trainer = FraudDetectionTraining()

        logger.info('Starting model training...')
        # Batch size and minimum required records for training (configurable via Airflow Variables)
        # Default to 100,000 records for both batch and minimum to speed up iterative experiments.
        batch_size = int(Variable.get('training_batch_size', default_var=100000))
        min_records = int(Variable.get('training_min_records', default_var=100000))

        logger.info('Requested training batch_size=%s, min_records=%s', batch_size, min_records)

        # Fetch transactions into a DataFrame (table can be overridden via Variable)
        df = trainer.ingest_data(transactions_table, limit=batch_size)

        # Validate we have enough data to proceed
        if len(df) < min_records:
            msg = (
                f"Not enough transactions for training: requested {batch_size}, "
                f"received {len(df)}. Ensure the producer has generated sufficient records in "
                f"{trainer.ingest_data.__defaults__ if hasattr(trainer.ingest_data, '__defaults__') else 'transactions_db'} or lower the batch_size/min_records variables."
            )
            logger.error(msg)
            if PROMETHEUS_AVAILABLE:
                training_errors_total.labels(error_type='insufficient_data').inc()
            raise AirflowException(msg)

        model, metrics = trainer.train_model(df)
        precision = None
        if isinstance(metrics, dict):
            precision = metrics.get('precision')

        logger.info('Training completed with metrics=%s', metrics)
        
        # Record Prometheus metrics
        if PROMETHEUS_AVAILABLE and isinstance(metrics, dict):
            try:
                if 'accuracy' in metrics:
                    training_accuracy.set(float(metrics.get('accuracy', 0)))
                if 'precision' in metrics:
                    training_precision.set(float(metrics.get('precision', 0)))
                if 'recall' in metrics:
                    training_recall.set(float(metrics.get('recall', 0)))
                if 'f1' in metrics:
                    training_f1_score.set(float(metrics.get('f1', 0)))
                if 'roc_auc' in metrics:
                    training_roc_auc.set(float(metrics.get('roc_auc', 0)))
                
                training_runs_total.labels(status='success').inc()
                training_duration.observe(time.time() - start_time)
                logger.info('Prometheus metrics recorded successfully')
            except NameError:
                logger.debug('Prometheus metrics not initialized, skipping recording')
            except Exception as e:
                logger.warning('Failed to record Prometheus metrics: %s', str(e))
        
        return {'status': 'success', 'metrics': metrics}
    except Exception as e:
        if PROMETHEUS_AVAILABLE:
            training_errors_total.labels(error_type='training_failure').inc()
            training_runs_total.labels(status='failure').inc()
            training_duration.observe(time.time() - start_time)
        logger.error('Training failed: %s', str(e), exc_info=True)
        raise AirflowException(f'Model training failed: {str(e)}')


def _cleanup_resources(**context):
    """Safer cleanup implemented in Python to avoid shell-specific behaviour.

    Removes any .pkl files under /app/tmp (if present). This is used as the
    DAG's final step and runs even when previous tasks fail.
    """
    tmp_dir = Variable.get('tmp_dir', default_var='/app/tmp')
    if not os.path.isdir(tmp_dir):
        logger.info('No tmp dir to clean: %s', tmp_dir)
        return
    removed = []
    for path in glob.glob(os.path.join(tmp_dir, '*.pkl')):
        try:
            os.remove(path)
            removed.append(path)
        except Exception:
            logger.exception('Failed to remove %s', path)
    logger.info('Cleanup removed %d files', len(removed))


def _validate_environment(**context):
    """Validate runtime environment at task execution time.

    Reads `config_path` from Airflow Variables at runtime so this check does
    not run during DAG parse.
    """
    cfg_path = Variable.get('config_path', default_var='/app/config.yaml')
    logger.info('Validating environment...')
    if os.path.exists(cfg_path):
        logger.info('Config found: %s', cfg_path)
    else:
        logger.warning('Config not found at %s', cfg_path)
    logger.info('Environment validation complete')


with DAG(
    'fraud_detection_training',
    default_args=default_args,
    description='Fraud detection model training pipeline (configurable)',
    schedule='0 12 * * *',
    max_active_runs=1,
    catchup=False,
    tags=['fraud', 'ML']
) as dag:
    # Validate the runtime environment. This check is intentionally permissive,
    # because different deploys may place `config.yaml` or env files in different locations.
    validate_environment = PythonOperator(
        task_id='validate_environment',
        python_callable=_validate_environment,
    )

    training_task = PythonOperator(
        task_id='execute_training',
        python_callable=_train_model,
        retries=0,
    )

    cleanup_task = PythonOperator(
        task_id='cleanup_resources',
        python_callable=_cleanup_resources,
        trigger_rule=TriggerRule.ALL_DONE,
    )

    validate_environment >> training_task >> cleanup_task

    # Documentation
    dag.doc_md = """
    ## Fraud Detection Training Pipeline

    This DAG runs daily and is configurable via Airflow Variables or a YAML
    file mounted into the container at `/app/config.yaml`.

    Important notes:
    - The transactions table name may differ between environments. Set the
      Airflow Variable `transactions_table` to the correct table name for your
      environment. If not set, the DAG uses `transactions` or the value in
      `config.yaml` under `transactions_table`.
    - Training code is loaded at runtime to avoid heavy imports during DAG parse.
    - Cleanup is done in Python for portability and to avoid shell-specific issues.
    """