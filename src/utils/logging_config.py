"""
Structured JSON Logging Configuration

Provides centralized logging setup with JSON formatting for all services.
Enables structured logging for better observability and log aggregation.
"""

import logging
import json
import sys
from datetime import datetime
from pythonjsonlogger import jsonlogger


class CustomJsonFormatter(jsonlogger.JsonFormatter):
    """Custom JSON formatter with additional context fields."""
    
    def add_fields(self, log_record, record, message_dict):
        """Add custom fields to log record."""
        super().add_fields(log_record, record, message_dict)
        
        # Add timestamp in ISO format
        log_record['timestamp'] = datetime.utcnow().isoformat() + 'Z'
        
        # Add service context
        log_record['service'] = record.name
        log_record['level'] = record.levelname
        
        # Add exception info if present
        if record.exc_info:
            log_record['exception'] = self.formatException(record.exc_info)


def setup_structured_logging(service_name: str, level=logging.INFO):
    """
    Setup structured JSON logging for a service.
    
    Args:
        service_name: Name of the service (e.g., 'inference', 'training', 'producer')
        level: Logging level (default: INFO)
    
    Returns:
        Configured logger instance
    """
    # Create logger
    logger = logging.getLogger(service_name)
    logger.setLevel(level)
    
    # Clear existing handlers
    logger.handlers.clear()
    
    # Create console handler with JSON formatter
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    
    # Create JSON formatter
    json_formatter = CustomJsonFormatter()
    console_handler.setFormatter(json_formatter)
    
    # Add handler to logger
    logger.addHandler(console_handler)
    
    # Prevent propagation to root logger
    logger.propagate = False
    
    return logger


def get_logger(name: str, level=logging.INFO):
    """
    Get or create a structured logger.
    
    Args:
        name: Logger name (typically __name__)
        level: Logging level
    
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    
    if not logger.handlers:
        setup_structured_logging(name, level)
    
    return logger
