"""
Unit tests for Diagnostic and Telemetry in Sprint 4.
"""
import pytest
import time
import logging
from src.core.telemetry import apply_recency_penalty, diagnostic_decorator

def test_recency_penalty(caplog):
    """
    Tạo Mock Document có updated_at cũ. Test gọi apply_recency_penalty và Assert hàm Log [RECENCY_PENALTY] đã hạ điểm logit.
    """
    caplog.set_level(logging.INFO)
    
    original_score = 1.0
    # Giả lập tài liệu từ 2018 so với 2026 => Khoảng 8 năm (~2920 ngày)
    days_old = 8 * 365
    
    new_score = apply_recency_penalty(original_score, days_old, doc_id="TEST_DOC_2018")
    
    assert new_score < original_score
    assert "Original Score: 1.000" in caplog.text
    assert "[DEBUG_TREE] RECENCY_PENALTY:" in caplog.text
    assert "TEST_DOC_2018" in caplog.text

def test_latency_spike_telemetry(caplog):
    """
    Gây delay bằng time.sleep(). Bắt Log Warning thông báo vượt ngưỡng độ trễ LATENCY_SPIKE.
    """
    caplog.set_level(logging.WARNING)
    
    @diagnostic_decorator
    def slow_function():
        time.sleep(0.6)
        return "done"
        
    result = slow_function()
    
    assert result == "done"
    assert "[WARN] [DEBUG_TREE] LATENCY_SPIKE:" in caplog.text
    assert "slow_function took" in caplog.text
    assert "Consider scaling hardware." in caplog.text
