import sys
import os
import pytest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from src.retrieval.rag_answer import retrieve_documents

def fake_retrieve_sparse(query, top_k):
    import time
    time.sleep(0.015) # 15ms latency
    return [{"id": f"sparse_{i}", "text": f"Sparse match {i} for {query}", "score": 0.9} for i in range(15)]

def fake_retrieve_dense(query, top_k):
    import time
    time.sleep(0.040) # 40ms latency
    return [{"id": f"dense_{i}", "text": f"Dense match {i} for {query}", "distance": 0.2} for i in range(15)]

def fake_rerank_cross_encoder(query, candidates, top_n):
    import time
    time.sleep(0.080) # 80ms latency LLM mock
    result = candidates[:top_n]
    for idx, c in enumerate(result):
        c["cross_score"] = 0.99 - idx * 0.01
    return result


@patch('src.retrieval.rag_answer.retrieve_sparse', side_effect=fake_retrieve_sparse)
@patch('src.retrieval.rag_answer.retrieve_dense', side_effect=fake_retrieve_dense)
@patch('src.retrieval.rag_answer.rerank_cross_encoder', side_effect=fake_rerank_cross_encoder)
def test_retrieve_pipeline_e2e_normal(mock_rerank, mock_dense, mock_sparse, caplog):
    import logging
    caplog.set_level(logging.INFO)
    """
    Integration test kiểm tra luồng song song RRF -> Reranker.
    Tổng Latency lý thuyết: Max(40, 15) + fusion + 80 = ~120ms < 250ms Budget.
    """
    import time
    start = time.time()
    
    query = "Làm sao để đổi mật khẩu VPN"
    results = retrieve_documents(query, fast_path=True)
    
    end = time.time()
    total_latency_ms = int((end - start) * 1000)
    
    # 1. Assert Budget Latency < 250ms
    assert total_latency_ms < 250, f"Latency ({total_latency_ms}ms) exceeded 250ms budget!"
    
    # 2. Assert số lượng đầu ra chính xác 3
    assert len(results) == 3, "Phải gạn lại đúng top 3 tài liệu"
    
    # 3. Kích hoạt logging hooks
    log_text = caplog.text
    assert "[PIPELINE_INIT]" in log_text
    assert "[PIPELINE_DENSE_SPARSE]" in log_text
    assert "[PIPELINE_STAGE] RRF output size: 20 docs" in log_text # RRF top 20 max
    assert "[PIPELINE_FINAL] Pipeline Latency" in log_text

@patch('src.retrieval.rag_answer.retrieve_sparse', side_effect=fake_retrieve_sparse)
def test_retrieve_pipeline_e2e_bypass(mock_sparse, caplog):
    import logging
    caplog.set_level(logging.INFO)
    """
    Kiểm tra Fast Bypass bằng Keyword (ERR-403) -> Only Sparse -> No Rerank.
    Tổng Latency lý thuyết: 15ms < 250ms.
    """
    import time
    start = time.time()
    
    query = "Lỗi ERR-403 permission denied"
    results = retrieve_documents(query, fast_path=True)
    
    end = time.time()
    total_latency_ms = int((end - start) * 1000)
    
    # 1. Assert cực nhanh < 50ms
    assert total_latency_ms < 50, f"Bypass failed, took {total_latency_ms}ms"
    
    # 2. Kích hoạt logging hooks
    log_text = caplog.text
    assert "[PIPELINE_INIT]" in log_text
    assert "[PIPELINE_BYPASS]" in log_text
    assert "[PIPELINE_DENSE_SPARSE]" not in log_text # Bypass rồi nên không gọi
    assert len(results) == 3
