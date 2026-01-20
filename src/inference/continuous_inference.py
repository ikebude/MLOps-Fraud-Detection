"""
Continuous Real-Time Inference Worker

This worker continuously polls the fraud API and runs inference on new transactions.
It runs as a background thread in the API server to ensure real-time processing.
"""
import os
import time
import logging
import threading
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from main import FraudDetectionInference

logger = logging.getLogger(__name__)

class ContinuousInferenceWorker:
    """
    Background worker that continuously polls the fraud API and processes transactions.
    
    This ensures real-time fraud detection without manual intervention.
    """
    
    def __init__(self, inference_pipeline, poll_interval: int = 5):
        """
        Initialize the continuous inference worker.
        
        Args:
            inference_pipeline: Initialized FraudDetectionInference instance
            poll_interval: Seconds between API polls (default: 5 seconds for real-time)
        """
        self.inference_pipeline = inference_pipeline
        self.poll_interval = poll_interval
        self.running = False
        self.thread = None
        self.last_processed_count = 0
        self.last_poll_time = None
        self.processed_transaction_ids = set()  # Track processed transaction IDs to avoid duplicates
        self.last_max_id = 0  # Track highest transaction ID seen
        
    def start(self):
        """Start the continuous inference worker in a background thread."""
        if self.running:
            logger.warning('Continuous inference worker already running')
            return
            
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        logger.info('Continuous inference worker started (poll interval: %ds)', self.poll_interval)
        
    def stop(self):
        """Stop the continuous inference worker."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        logger.info('Continuous inference worker stopped')
        
    def _run_loop(self):
        """Main loop that continuously polls and processes transactions."""
        logger.info('Starting continuous inference loop')
        
        while self.running:
            try:
                self.last_poll_time = datetime.now()
                
                # Poll for new transactions (small batch for real-time processing)
                # Process 1-5 transactions at a time for true real-time
                batch_size = int(os.getenv('CONTINUOUS_INFERENCE_BATCH_SIZE', '3'))
                
                logger.debug('Polling fraud API for new transactions (batch_size=%d)', batch_size)
                
                # Fetch raw transactions from API and filter to only NEW ones
                # The API returns transactions, we need to track which ones we've seen
                try:
                    # Fetch a larger batch to ensure we get new transactions
                    raw_records, _ = self.inference_pipeline.fetch_transactions_from_api(offset=0, limit=50)
                    
                    # Filter to only NEW transactions we haven't processed
                    new_records = []
                    for record in raw_records:
                        if not isinstance(record, dict):
                            continue
                            
                        # Get transaction ID - prefer transaction_id, fallback to id
                        txn_id = record.get('transaction_id') or record.get('id') or record.get('txn_id')
                        
                        # If still no ID, create a composite ID from timestamp + user_id
                        if not txn_id:
                            txn_id = f"{record.get('timestamp', '')}_{record.get('user_id', '')}"
                        
                        if txn_id and str(txn_id) not in self.processed_transaction_ids:
                            new_records.append(record)
                            self.processed_transaction_ids.add(str(txn_id))
                            # Keep set size manageable (keep last 10000)
                            if len(self.processed_transaction_ids) > 10000:
                                # Remove oldest 1000
                                ids_list = list(self.processed_transaction_ids)
                                self.processed_transaction_ids = set(ids_list[-9000:])
                    
                    # Limit to batch_size for processing
                    new_records = new_records[:batch_size]
                    
                    if not new_records:
                        logger.debug('No new transactions found (tracking %d processed)', len(self.processed_transaction_ids))
                        time.sleep(self.poll_interval)
                        continue
                    
                    logger.info('Found %d new transactions to process', len(new_records))
                    
                    # Use the full inference pipeline but with our filtered new records
                    import pandas as pd
                    df = pd.DataFrame(new_records)
                    
                    # Run through the full pipeline: preprocess -> engineer -> predict
                    df = self.inference_pipeline.preprocess_data(df)
                    df = self.inference_pipeline.engineer_features(df)
                    
                    if self.inference_pipeline.model is None:
                        logger.warning('Model not available')
                        time.sleep(self.poll_interval)
                        continue
                    
                    # Get feature columns
                    feature_cols = self.inference_pipeline.model.feature_names_in_.tolist()
                    missing_cols = [col for col in feature_cols if col not in df.columns]
                    if missing_cols:
                        for col in missing_cols:
                            df[col] = 0
                    
                    X = df[feature_cols]
                    
                    # Get predictions
                    predictions, probabilities, confidence = self.inference_pipeline.predict(X)
                    
                    # Build results dataframe
                    results = df[['transaction_id', 'user_id', 'amount', 'timestamp'] 
                                if all(c in df.columns for c in ['transaction_id', 'user_id', 'amount', 'timestamp'])
                                else df.columns[:4]].copy()
                    
                    results['fraud_prediction'] = predictions
                    results['fraud_probability'] = probabilities
                    results['confidence'] = confidence
                    results['prediction_timestamp'] = datetime.now()
                    
                except Exception as e:
                    logger.error('Error in continuous inference processing: %s', str(e), exc_info=True)
                    # Fallback: just skip this cycle
                    time.sleep(self.poll_interval)
                    continue
                
                if isinstance(results, dict) and results.get('status') == 'model_unavailable':
                    logger.warning('Model unavailable, skipping inference cycle')
                    time.sleep(self.poll_interval)
                    continue
                
                # IMPORTANT: Update results via the API server's _append_results function
                # This ensures cumulative totals are updated
                if hasattr(results, '__len__') and len(results) > 0:
                    # Use the append function passed from api_server
                    if self._append_results_func:
                        self._append_results_func(results)
                    else:
                        # Fallback: try to import (may cause circular dependency issues)
                        try:
                            import api_server
                            api_server._append_results(results)
                        except:
                            logger.warning('Could not update results via _append_results')
                    
                    processed_count = len(results)
                    fraud_count = int(results['fraud_prediction'].sum()) if hasattr(results, 'columns') and 'fraud_prediction' in results.columns else 0
                    logger.info('Processed %d transactions (%d fraud) in continuous inference', 
                              processed_count, fraud_count)
                    self.last_processed_count = processed_count
                else:
                    logger.debug('No new transactions to process')
                    
            except Exception as e:
                logger.error('Error in continuous inference loop: %s', str(e), exc_info=True)
                # Don't crash on errors, just wait and retry
                
            # Wait before next poll
            time.sleep(self.poll_interval)
            
    def get_status(self):
        """Get current worker status."""
        return {
            'running': self.running,
            'poll_interval': self.poll_interval,
            'last_poll_time': self.last_poll_time.isoformat() if self.last_poll_time else None,
            'last_processed_count': self.last_processed_count
        }
