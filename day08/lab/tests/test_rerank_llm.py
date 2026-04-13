import pytest
import sys
import os
from typing import List, Dict, Any

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
from src.retrieval.rag_answer import rerank_cross_encoder as rerank

@pytest.fixture
def mock_openai_rerank_response(monkeypatch):
    """
    Mock class để giả lập response từ OpenAI GPT-4o-mini
    """
    class MockMessage:
        content = "2, 0, 1"

    class MockChoice:
        message = MockMessage()

    class MockResponse:
        choices = [MockChoice()]

    class MockCompletions:
        def create(self, **kwargs):
            return MockResponse()

    class MockChat:
        completions = MockCompletions()

    class MockClient:
        chat = MockChat()
        
    def mock_openai_init(*args, **kwargs):
        return MockClient()
        
    import openai
    monkeypatch.setattr("openai.OpenAI", mock_openai_init)

def test_rerank_success(mock_openai_rerank_response):
    """
    Test rerank trả về danh sách được sắp xếp theo đúng thứ tự mock LLM (2, 0, 1).
    """
    query = "Làm sao để xử lý lỗi VPN?"
    candidates = [
        {"id": "doc1", "text": "Đây là tài liệu không liên quan về máy in."},  # 0
        {"id": "doc2", "text": "Đây là tài liệu về mật khẩu wifi."},          # 1
        {"id": "doc3", "text": "Để xử lý lỗi VPN, hãy khởi động lại Cisco."}, # 2
    ]
    
    # Rerank lấy top 2
    results = rerank(query, candidates, top_n=2)
    
    assert len(results) == 2
    # doc3 ở vị trí index 2, nên theo mock trả về "2, 0, 1", doc3 phải nằm đầu tiên
    assert results[0]["id"] == "doc3"
    # doc1 ở vị trí index 0, nằm thứ 2
    assert results[1]["id"] == "doc1"
    
    # Score được gán (dựa theo rank giả lập 1.0, 0.5, 0.33)
    assert results[0]["score"] == 1.0
    assert results[1]["score"] == 0.5

def test_rerank_empty_candidates():
    """
    Test rerank với list input rỗng
    """
    results = rerank("query", [], top_n=3)
    assert results == []

def test_rerank_api_exception(monkeypatch):
    """
    Test rerank khi OpenAI API throw exception, phải fallback trả lại top kết quả ban đầu nguyên vẹn.
    """
    def mock_raise_error(*args, **kwargs):
        raise Exception("API Connection Failed")
        monkeypatch.setattr("openai.OpenAI", mock_raise_error)
    
    query = "Làm sao để xử lý lỗi VPN?"
    candidates = [
        {"id": "doc1", "text": "Tài liệu 1"},
        {"id": "doc2", "text": "Tài liệu 2"},
    ]
    
    # Nên trả lại nguyên vẹn do Exception
    results = rerank(query, candidates, top_n=2)
    assert len(results) == 2
    assert results[0]["id"] == "doc1"
    assert results[1]["id"] == "doc2"
