import json
from unittest.mock import patch, MagicMock

import pytest

from transform.embed_pipeline import chunk_record, embed_and_upsert


def test_stress_chunk_record_large_content():
    large_content = "X" * 10_000_000
    record = {
        "doc_id": "huge_doc",
        "content": large_content,
        "effective_date": "2026-04-15",
        "source": "stress_test"
    }
    chunks = chunk_record(record, max_length=1000)
    assert len(chunks) == 10000
    assert chunks[9999]["chunk_id"] == "huge_doc_9999"


def test_stress_chunk_record_missing_fields():
    record = {}
    chunks = chunk_record(record)
    assert len(chunks) == 1
    assert chunks[0]["chunk_id"] == "unknown_0"
    assert "{" in chunks[0]["text"]
    assert chunks[0]["metadata"]["doc_id"] == ""


@patch("transform.embed_pipeline.chromadb.PersistentClient")
@patch("transform.embed_pipeline.OpenAI")
def test_stress_embed_and_upsert(mock_openai_cls, mock_chroma_cls, tmp_path):
    data_file = tmp_path / "cleaned_records_stress.jsonl"
    
    with open(data_file, "w", encoding="utf-8") as f:
        for i in range(1000):
            f.write(json.dumps({
                "doc_id": f"doc_{i}",
                "content": f"text_for_doc_{i}",
                "source": "stress"
            }) + "\n")
        f.write("THIS_IS_A_CORRUPT_JSON_LINE\n")
        
    with patch("transform.embed_pipeline.CLEANED_INPUT", data_file):
        mock_collection = MagicMock()
        mock_client = MagicMock()
        mock_client.get_or_create_collection.return_value = mock_collection
        mock_chroma_cls.return_value = mock_client
        
        mock_openai_instance = MagicMock()
        
        def create_embedding_side_effect(*args, **kwargs):
            val = kwargs.get("input", "")
            if val == "text_for_doc_50":
                raise Exception("Simulated API Error")
            resp = MagicMock()
            d = MagicMock()
            d.embedding = [0.0] * 1536
            resp.data = [d]
            return resp
            
        mock_openai_instance.embeddings.create.side_effect = create_embedding_side_effect
        mock_openai_cls.return_value = mock_openai_instance
        
        embed_and_upsert(run_id="stress_run")
        
        mock_collection.upsert.assert_called_once()
        kwargs = mock_collection.upsert.call_args.kwargs
        
        assert len(kwargs["ids"]) == 999
        assert "doc_50_0" not in kwargs["ids"]
        assert "doc_51_0" in kwargs["ids"]
