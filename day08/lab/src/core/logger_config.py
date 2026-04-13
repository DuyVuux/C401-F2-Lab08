"""
Centralized logging configuration.
Avoids print() and standardizes output for observability tools.
"""
import logging
import sys

def get_logger(name: str) -> logging.Logger:
    """
    Initializes and returns a structured logger.
    
    Args:
        name (str): The name of the logger, typically __name__ of the calling module.
        
    Returns:
        logging.Logger: A configured logger instance.
    """
    logger = logging.getLogger(name)
    if not logger.hasHandlers():
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.INFO)
        
        # Tag-based formatting for downstream Log Aggregators (e.g., ELK, Datadog)
        formatter = logging.Formatter(
            '%(asctime)s | [%(levelname)s] | %(name)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        
    return logger
