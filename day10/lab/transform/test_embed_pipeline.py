import json
from unittest.mock import patch, MagicMock

import pytest

from transform.embed_pipeline import chunk_record, embed_and_upsert

def test_chunk_record():
    record = {
        "doc_id": "123",
        "content": "A" * 2500,
        "effective_date": "2024",
        "source": "src"
    }
    chunks = chunk_record(record, max_length=1000)
    
    assert len(chunks) == 3
    assert chunks[0]["chunk_id"] == "123_0"
    assert len(chunks[0]["text"]) == 1000
    assert chunks[0]["metadata"]["doc_id"] == "123"
    assert chunks[0]["metadata"]["effective_date"] == "2024"
    assert chunks[0]["metadata"]["source"] == "src"
    assert chunks[2]["chunk_id"] == "123_2"
    assert len(chunks[2]["text"]) == 500

def test_embed_and_upsert(tmp_path):
    data_file = tmp_path / "cleaned_records.jsonl"
    with open(data_file, "w", encoding="utf-8") as f:
        f.write(json.dumps({"doc_id": "1", "content": "hello", "source": "test"}) + "\n")
        f.write(json.dumps({"doc_id": "2", "content": "world", "source": "test"}) + "\n")

    with patch("transform.embed_pipeline.CLEANED_INPUT", data_file), \
         patch("transform.embed_pipeline.chromadb.PersistentClient") as mock_chroma, \
         patch("transform.embed_pipeline.OpenAI") as mock_openai:
         
        mock_collection = MagicMock()
        mock_client = MagicMock()
        mock_client.get_or_create_collection.return_value = mock_collection
        mock_chroma.return_value = mock_client
        
        mock_openai_instance = MagicMock()
        mock_embeddings_response_1 = MagicMock()
        mock_embedding_data_1 = MagicMock()
        mock_embedding_data_1.embedding = [0.1, 0.2]
        mock_embeddings_response_1.data = [mock_embedding_data_1]
        
        mock_embeddings_response_2 = MagicMock()
        mock_embedding_data_2 = MagicMock()
        mock_embedding_data_2.embedding = [0.3, 0.4]
        mock_embeddings_response_2.data = [mock_embedding_data_2]
        
        mock_openai_instance.embeddings.create.side_effect = [
            mock_embeddings_response_1, mock_embeddings_response_2
        ]
        mock_openai.return_value = mock_openai_instance

        embed_and_upsert(run_id="test_run")

        mock_collection.upsert.assert_called_once()
        kwargs = mock_collection.upsert.call_args.kwargs
        assert kwargs["ids"] == ["1_0", "2_0"]
        assert kwargs["embeddings"] == [[0.1, 0.2], [0.3, 0.4]]
        assert kwargs["metadatas"][0]["run_id"] == "test_run"
        assert kwargs["metadatas"][0]["doc_id"] == "1"
