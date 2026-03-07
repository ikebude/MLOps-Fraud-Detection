"""
Continuous Inference Worker for Real-Time Fraud Detection

Runs inference continuously in background thread, polling for new transactions
every N seconds and scoring them automatically.

This worker:
1. Polls the database every poll_interval seconds
2. Calls run_inference() to score new transactions
3. Updates cumulative statistics
4. Maintains live inference stream for dashboard
"""

import logging
import threading
import time
from datetime import datetime

try:
    from utils.logging_config import setup_structured_logging
    from utils.prometheus_metrics import (
        inference_data_points_total, inference_predictions_total
    )
    logger = setup_structured_logging('continuous-inference', logging.INFO)
    PROM_AVAILABLE = True
except Exception:
    logger = logging.getLogger('fraud_detection_continuous')
    PROM_AVAILABLE = False


class ContinuousInferenceWorker:
    """
    Background worker that continuously runs inference on new transactions.
    
    Polls the database at regular intervals and scores transactions that
    haven't been scored yet. Updates are streamed to dashboard via API.
    """
    
    def __init__(self, inference_pipeline, poll_interval: int = 5):
        """
        Initialize continuous inference worker.
        
        Args:
            inference_pipeline: FraudDetectionInference instance
            poll_interval: Seconds between polling for new transactions (default: 5)
        """
        self.inference_pipeline = inference_pipeline
        self.poll_interval = poll_interval
        self.running = False
        self.thread = None
        self._append_results_func = None  # Will be set by api_server.py
        
        logger.info(f"ContinuousInferenceWorker initialized (poll_interval={poll_interval}s)")
    
    def start(self):
        """Start continuous inference in background thread."""
        if self.running:
            logger.warning("Continuous inference worker already running")
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.thread.start()
        logger.info("Continuous inference worker started")
    
    def stop(self):
        """Stop continuous inference worker."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=10)
        logger.info("Continuous inference worker stopped")
    
    def _worker_loop(self):
        """
        Main worker loop - runs continuously until stopped.
        
        Polls for new transactions and scores them automatically.
        """
        logger.info(f"Continuous inference loop started (polling every {self.poll_interval}s)")
        
        last_log_time = time.time()
        
        while self.running:
            try:
                # Run inference on unscored transactions
                results = self.inference_pipeline.run_inference(
                    max_records=1000,
                    explain=False,
                    top_k=5
                )
                
                # Update results if callback provided
                if self._append_results_func and results is not None:
                    try:
                        self._append_results_func(results)
                    except Exception as e:
                        logger.error(f"Error appending results: {e}")

                # Update Prometheus metrics if available
                try:
                    if PROM_AVAILABLE and results is not None and hasattr(results, 'columns'):
                        total = len(results)
                        inference_data_points_total.inc(total)
                        if 'fraud_prediction' in results.columns:
                            fraud_count = int(results['fraud_prediction'].sum())
                            legit = int(total - fraud_count)
                            if fraud_count > 0:
                                inference_predictions_total.labels(prediction_type='fraud').inc(fraud_count)
                            if legit > 0:
                                inference_predictions_total.labels(prediction_type='legitimate').inc(legit)
                except Exception:
                    logger.debug('Failed to update Prometheus metrics from continuous worker')
                
                # Log status periodically (every 60 seconds)
                current_time = time.time()
                if current_time - last_log_time >= 60:
                    if hasattr(results, '__len__'):
                        logger.info(f"Continuous inference: scored {len(results)} transactions")
                    last_log_time = current_time
                
            except Exception as e:
                logger.error(f"Error in continuous inference loop: {e}", exc_info=True)
            
            # Wait before next poll
            time.sleep(self.poll_interval)
        
        logger.info("Continuous inference loop stopped")
    
    def is_running(self) -> bool:
        """Check if worker is running."""
        return self.running and self.thread and self.thread.is_alive()
    
    def set_poll_interval(self, interval: int):
        """
        Update polling interval.
        
        Args:
            interval: New poll interval in seconds
        """
        self.poll_interval = interval
        logger.info(f"Poll interval updated to {interval}s")
    
    def get_status(self) -> dict:
        """
        Get worker status.
        
        Returns:
            Dictionary with worker status info
        """
        return {
            'running': self.is_running(),
            'poll_interval': self.poll_interval,
            'thread_alive': self.thread.is_alive() if self.thread else False
        }





