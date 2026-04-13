import pytest
import logging
from typing import List, Dict, Any

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from src.retrieval.rag_answer import compute_rrf

def test_compute_rrf(caplog):
    caplog.set_level(logging.DEBUG)
    
    # Create mock lists
    dense_docs = [
        {"id": "doc1", "text": "This is doc 1"},
        {"id": "doc_shared", "text": "This is shared doc"},
        {"id": "doc2", "text": "This is doc 2"}
    ]
    
    sparse_docs = [
        {"id": "doc3", "text": "This is doc 3"},
        {"id": "doc_shared", "text": "This is shared doc"}, 
    ]
    
    # Expected ranks for "doc_shared":
    # dense_rank = 2
    # sparse_rank = 2
    # rrf_k = 60
    # Expected score = 1/(60+2) + 1/(60+2) = 1/62 + 1/62 = 2/62 ≈ 0.03225806
    
    merged_docs = compute_rrf(dense_docs, sparse_docs, rrf_k=60, top_k=20)
    
    # Find "doc_shared" in output
    shared_doc = next((d for d in merged_docs if d["id"] == "doc_shared"), None)
    assert shared_doc is not None
    
    expected_score = 1.0 / (60 + 2) + 1.0 / (60 + 2)
    assert abs(shared_doc["score"] - expected_score) < 1e-6
    
    # Check Logs
    has_start = any("[RRF_START]" in r.message for r in caplog.records)
    has_success = any("[RRF_SUCCESS]" in r.message for r in caplog.records)
    assert has_start
    assert has_success
    
    # Check Math Log for doc_shared
    math_log = next((r.message for r in caplog.records if "[RRF_MATH]" in r.message and "doc_shared" in r.message), None)
    assert math_log is not None
    assert "Dense Rank: 2" in math_log
    assert "Sparse Rank: 2" in math_log
    assert f"Final Score: {expected_score:.6f}" in math_log
    
    # Check correct order
    assert len(merged_docs) == 4
    
def test_compute_rrf_empty(caplog):
    caplog.set_level(logging.WARNING)
    merged_docs = compute_rrf([], [], rrf_k=60, top_k=20)
    assert merged_docs == []
    has_warn = any("[RRF_WARN]" in r.message for r in caplog.records)
    assert has_warn
