import pytest
import logging
from unittest.mock import patch, MagicMock

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from src.retrieval.rag_answer import retrieve_dense

def test_retrieve_dense_success(caplog):
    # Enable capturing of INFO and DEBUG logs
    caplog.set_level(logging.DEBUG)
    
    query = "SLA xử lý ticket P1 là bao lâu?"
    top_k = 3

    # Giả định DB đã có dữ liệu mẫu (mocking chromadb và get_embedding để test output format)
    with patch('chromadb.PersistentClient') as mock_chroma, \
         patch('src.indexing.index.get_embedding') as mock_embed:
        
        # Setup mock behavior
        mock_embed.return_value = [0.1, 0.2, 0.3]
        
        mock_collection = MagicMock()
        mock_collection.query.return_value = {
            "documents": [["SLA xử lý ticket P1 là 2h", "Một text khác"]],
            "metadatas": [[{"source": "sla.txt"}, {"source": "fake.txt"}]],
            "distances": [[0.1, 0.5]]
        }
        
        mock_client_instance = MagicMock()
        mock_client_instance.get_collection.return_value = mock_collection
        mock_chroma.return_value = mock_client_instance

        # Run target function
        results = retrieve_dense(query, top_k=top_k)

        # In log ra console theo yêu cầu
        for record in caplog.records:
            print(f"[{record.levelname}] {record.message}")

        # Assert log contains [DENSE_SUCCESS]
        assert any("[DENSE_SUCCESS]" in record.message for record in caplog.records), "The [DENSE_SUCCESS] log is missing."
        assert any("[DENSE_START]" in record.message for record in caplog.records), "The [DENSE_START] log is missing."
        assert any("[DENSE_EMBEDDING]" in record.message for record in caplog.records), "The [DENSE_EMBEDDING] log is missing."
        
        # Assert số lượng documents >= 1
        assert len(results) >= 1
        assert results[0]["text"] == "SLA xử lý ticket P1 là 2h"
        assert round(results[0]["score"], 1) == 0.9 # Score is 1 - 0.1

def test_retrieve_dense_failure(caplog):
    caplog.set_level(logging.ERROR)
    
    with patch('chromadb.PersistentClient', side_effect=Exception("Timeout connection")):
        results = retrieve_dense("Test query", top_k=1)
        
        # Assert empty result
        assert results == []
        
        # In log
        for record in caplog.records:
            print(f"[{record.levelname}] {record.message}")
        
        # Assert log Error found
        assert any("[DENSE_FAILED]" in record.message for record in caplog.records), "The [DENSE_FAILED] log is missing."
