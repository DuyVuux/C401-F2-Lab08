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
            
            if elapsed_ms > 500:
                logger.warning(
                    f"[WARN] [DEBUG_TREE] LATENCY_SPIKE: {func.__name__} took {elapsed_ms:.0f}ms (> 500ms Threshold). Consider scaling hardware."
                )
            elif elapsed_ms > 250:
                logger.warning(
                    f"[WARN] [LATENCY_ALERT] {func.__name__} violates budget! "
                    f"Took {elapsed_ms:.2f}ms (Budget < 250ms)"
                )
            else:
                logger.debug(f"[DEBUG] {func.__name__} completed in {elapsed_ms:.2f}ms")
                
    return wrapper

def apply_recency_penalty(score: float, days_old: int, doc_id: str = "Unknown") -> float:
    """
    Giảm điểm các tài liệu cũ dựa theo hệ số time-decay 0.95 ^ years.
    """
    import math
    if days_old <= 0:
        return score
        
    years = days_old / 365.0
    penalty_rate = math.pow(0.95, years)
    new_score = score * penalty_rate
    
    logger.info(
        f"[INFO] [DEBUG_TREE] RECENCY_PENALTY: Doc_ID {doc_id} is old (Updated {years:.1f} years ago). Original Score: {score:.3f} -> Penalized: {new_score:.3f}"
    )
    return new_score
