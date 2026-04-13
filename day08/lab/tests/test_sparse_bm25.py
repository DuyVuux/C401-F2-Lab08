import pytest
import logging
from unittest.mock import patch, MagicMock

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from day08.lab.src.retrieval.rag_answer import retrieve_sparse, SparseEngine

def test_sparse_bm25_tokenize_trace(caplog):
    caplog.set_level(logging.DEBUG)
    SparseEngine._instance = None
    
    query = "Làm sao sửa mã ERR-403 trên IP 192.168.1.1?"
    top_k = 3

    # Giả định collection tồn tại với các tokens cụ thể
    with patch('chromadb.PersistentClient') as mock_chroma:
        mock_collection = MagicMock()
        mock_collection.get.return_value = {
            "documents": [
                "Để sửa mã ERR-403 trên IP 192.168.1.1 bạn làm như sau.",
                "Một tài liệu khác không liên quan.",
                "Thêm một tài liệu nữa."
            ],
            "metadatas": [{"source": "bug.txt"}, {"source": "other.txt"}, {"source": "third.txt"}]
        }
        
        mock_client_instance = MagicMock()
        mock_client_instance.get_collection.return_value = mock_collection
        mock_chroma.return_value = mock_client_instance

        # Thực thi sparse retrieval
        results = retrieve_sparse(query, top_k=top_k)

        # In log
        found_trace = False
        has_err = False
        has_ip = False
        for record in caplog.records:
            if "[TOKENIZER_TRACE]" in record.message:
                found_trace = True
                if "err-403" in record.message.lower():
                    has_err = True
                if ("192.168.1.1" in record.message.lower()) or ("ip_192.168.1.1" in record.message.lower()):
                    has_ip = True

        assert found_trace, "Không tìm thấy log [TOKENIZER_TRACE]"
        assert has_err, "Token ERR-403 bị cắt vụn!"
        assert has_ip, "Token 192.168.1.1 bị cắt vụn!"
        
        # Assert log START and SUCCESS
        assert any("[SPARSE_START]" in record.message for record in caplog.records)
        assert any("[SPARSE_SUCCESS]" in record.message for record in caplog.records)
        
        assert len(results) > 0
        assert results[0]["score"] > 0

def test_sparse_bm25_failure(caplog):
    caplog.set_level(logging.ERROR)
    SparseEngine._instance = None
    
    # Test failed case
    with patch('chromadb.PersistentClient', side_effect=Exception("Chroma DB died!")):
        results = retrieve_sparse("Test query", top_k=1)
        
        assert results == []
        assert any("[SPARSE_FAILED]" in record.message for record in caplog.records)
