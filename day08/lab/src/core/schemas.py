"""
Data models and schemas for the Enterprise RAG System.
Strictly heavily typed using Pydantic for input/output validation.
"""
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional

class Document(BaseModel):
    """
    Core document schema representing an indexed chunk.
    """
    id: str = Field(..., description="Unique identifier for the document chunk.")
    text: str = Field(..., description="The textual content of the chunk.")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadata associated with the document.")
    score: Optional[float] = Field(default=None, description="Retrieval or Reranking score.")

class SearchContext(BaseModel):
    """
    Context passed through the retrieval pipeline.
    """
    query: str = Field(..., description="The original user query.")
    filters: Dict[str, Any] = Field(default_factory=dict, description="Pre-filtering criteria for the vector store.")
    top_k: int = Field(default=5, description="Number of documents to retrieve per search strategy.")

class AnswerResponse(BaseModel):
    """
    Final response output to the user.
    """
    answer: str = Field(..., description="Generated grounded answer from the LLM.")
    sources: List[Document] = Field(default_factory=list, description="Source documents used for generation.")
    latency_ms: float = Field(..., description="Total pipeline processing time.")
