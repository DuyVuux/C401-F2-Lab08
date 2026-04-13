"""
Observability tools tailored for latency budgeting and operational alerts.
"""
from typing import Callable, Any
from functools import wraps
import time
from src.core.logger_config import get_logger

logger = get_logger(__name__)

class TelemetryTracker:
    """Manages internal metric states and aggregation windows."""
    
    # TODO [Sprint 4 - Metrics State Handling]:
    # - Lưu trữ RAM-based cache cho chỉ số trễ, rate limiting, error codes
    pass

def diagnostic_decorator(func: Callable) -> Callable:
    """
    Higher-order function wrapping critical nodes with latency checking mechanisms.
    
    Args:
        func (Callable): The pipeline function to trace.
        
    Returns:
        Callable: The observed execution wrapper.
    """
    @wraps(func)
    def wrapper(*args, **kwargs) -> Any:
        logger.info(f"[INFO] [TRACE] Starting execution of {func.__name__}")
        start_time = time.time()
        try:
            result = func(*args, **kwargs)
            return result
        except Exception as e:
            logger.error(f"[ERROR] [DIAGNOSTIC] Fallback triggered at {func.__name__}: {str(e)}")
            raise
        finally:
            elapsed_ms = (time.time() - start_time) * 1000
            
            # TODO [Sprint 4 - Telemetry Push to Log/Sink]:
            # Đẩy elapsed_ms vào Dashboard / Tracker system
            
            if elapsed_ms > 250:
                logger.warning(
                    f"[WARN] [LATENCY_ALERT] {func.__name__} violates budget! "
                    f"Took {elapsed_ms:.2f}ms (Budget < 250ms)"
                )
            else:
                logger.debug(f"[DEBUG] {func.__name__} completed in {elapsed_ms:.2f}ms")
                
    return wrapper
