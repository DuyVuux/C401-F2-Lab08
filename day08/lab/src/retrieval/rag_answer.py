"""
rag_answer.py — Sprint 2 + Sprint 3: Retrieval & Grounded Answer
================================================================
Sprint 2 (60 phút): Baseline RAG
  - Dense retrieval từ ChromaDB
  - Grounded answer function với prompt ép citation
  - Trả lời được ít nhất 3 câu hỏi mẫu, output có source

Sprint 3 (60 phút): Tuning tối thiểu
  - Thêm hybrid retrieval (dense + sparse/BM25)
  - Hoặc thêm rerank (cross-encoder)
  - Hoặc thử query transformation (expansion, decomposition, HyDE)
  - Tạo bảng so sánh baseline vs variant

Definition of Done Sprint 2:
  ✓ rag_answer("SLA ticket P1?") trả về câu trả lời có citation
  ✓ rag_answer("Câu hỏi không có trong docs") trả về "Không đủ dữ liệu"

Definition of Done Sprint 3:
  ✓ Có ít nhất 1 variant (hybrid / rerank / query transform) chạy được
  ✓ Giải thích được tại sao chọn biến đó để tune
"""

import os
import time
import asyncio
import re
from typing import List, Dict, Any, Optional, Tuple
from dotenv import load_dotenv
from openai import OpenAI

from src.core.telemetry import diagnostic_decorator, apply_recency_penalty

load_dotenv()

# =============================================================================
# CẤU HÌNH
# =============================================================================

TOP_K_SEARCH = 10    # Số chunk lấy từ vector store trước rerank (search rộng)
TOP_K_SELECT = 3     # Số chunk gửi vào prompt sau rerank/select (top-3 sweet spot)

LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")


# =============================================================================
# RETRIEVAL — DENSE (Vector Search)
# =============================================================================

import logging
import time

logger = logging.getLogger(__name__)

def retrieve_dense(query: str, top_k: int = TOP_K_SEARCH) -> List[Dict[str, Any]]:
    """
    Dense retrieval: tìm kiếm theo embedding similarity trong ChromaDB.
    """
    logger.info(f"[DENSE_START] Payload: query=\"{query}\", top_k={top_k}")
    try:
        from src.indexing.index import get_embedding
        from vector_store_manager import get_chroma_collection
        
        collection = get_chroma_collection()
        
        t0 = time.time()
        query_embedding = get_embedding(query)
        latency_ms = int((time.time() - t0) * 1000)
        logger.debug(f"[DENSE_EMBEDDING] Embedding generation time: {latency_ms}ms")
        
        t1 = time.time()
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=["documents", "metadatas", "distances"]
        )
        db_latency_ms = int((time.time() - t1) * 1000)
        
        docs = []
        if results and "documents" in results and results["documents"]:
            for doc, meta, dist in zip(results["documents"][0], results["metadatas"][0], results["distances"][0]):
                docs.append({
                    "text": doc,
                    "metadata": meta,
                    "score": 1.0 - float(dist)
                })
                
        logger.info(f"[DENSE_SUCCESS] Found {len(docs)} docs | DB latency: {db_latency_ms}ms")
        return docs
    except Exception as e:
        logger.error(f"[DENSE_FAILED] DB connection broken hoặc Timeout | Details: {str(e)}")
        return []


from src.retrieval.tokenizer import MaskingTokenizer

class SparseEngine:
    _instance = None

    def __init__(self):
        self.bm25 = None
        self.corpus_chunks = []
        self.tokenizer = MaskingTokenizer()
        self._build_index()

    def _build_index(self):
        try:
            from vector_store_manager import get_chroma_collection
            from rank_bm25 import BM25Okapi

            collection = get_chroma_collection()
            results = collection.get(include=["documents", "metadatas"])

            if not results or not results["documents"]:
                raise ValueError("ChromaDB collection is empty.")

            self.corpus_chunks = []
            tokenized_corpus = []

            for doc, meta in zip(results["documents"], results["metadatas"]):
                self.corpus_chunks.append({
                    "text": doc,
                    "metadata": meta
                })
                # Tokenize document for index
                tokens = self.tokenizer.tokenize(doc)
                tokenized_corpus.append(tokens)

            self.bm25 = BM25Okapi(tokenized_corpus)
            logger.info(f"BM25 Index built with {len(self.corpus_chunks)} chunks.")
        except Exception as e:
            logger.error(f"Failed to build BM25 index: {e}")
            self.bm25 = None
            self.corpus_chunks = []

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

def retrieve_sparse(query: str, top_k: int = TOP_K_SEARCH) -> List[Dict[str, Any]]:
    """
    Sparse retrieval: tìm kiếm theo keyword (BM25).
    """
    logger.info(f"[SPARSE_START] Query: \"{query}\"")
    import time
    t0 = time.time()
    
    try:
        engine = SparseEngine.get_instance()
        
        if not engine.bm25 or not engine.tokenizer:
            raise ValueError("BM25 Index trống hoặc Tokenizer null")

        tokenized_query = engine.tokenizer.tokenize(query)
        scores = engine.bm25.get_scores(tokenized_query)
        
        # Sort scores in descending order and get indices of top_k
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
        
        results = []
        for idx in top_indices:
            score = scores[idx]
            if score > 0:
                chunk = engine.corpus_chunks[idx].copy()
                chunk["score"] = score
                results.append(chunk)

        latency_ms = int((time.time() - t0) * 1000)
        logger.info(f"[SPARSE_SUCCESS] Retrieved {len(results)} exact matches in {latency_ms}ms.")
        
        if not results:
            match = re.search(r'\b(ERR-\d+)\b', query, re.IGNORECASE)
            if match:
                code = match.group(1).upper()
                logger.critical(f'[CRITICAL] [DEBUG_TREE] RECALL_MISSING: Sparse Result is Empty for IT Code "{code}". Suggestion: Check Custom Regex Tokenizer in config.')
                
        return results

    except Exception as e:
        import traceback
        logger.error(f"[SPARSE_FAILED] BM25 Index trống hoặc Tokenizer null | Details: {traceback.format_exc()}")
        return []


# =============================================================================
# RETRIEVAL — HYBRID (Dense + Sparse với Reciprocal Rank Fusion)
# =============================================================================

def compute_rrf(dense_docs: List[Dict[str, Any]], sparse_docs: List[Dict[str, Any]], rrf_k: int = 60, top_k: int = 20) -> List[Dict[str, Any]]:
    import time
    t0 = time.time()
    
    if not dense_docs and not sparse_docs:
        logger.warning("[RRF_WARN] Dữ liệu truyền vào rỗng từ cả hai luồng.")
        return []

    logger.info(f"[RRF_START] Input Docs - Dense: {len(dense_docs)}, Sparse: {len(sparse_docs)} | K_factor={rrf_k}")
    
    # Store combined scores and document content
    # Key: doc_id -> value: {"score": float, "chunk": Dict}
    doc_map = {}
    
    # Build a helper function to process a list
    def process_list(docs, is_dense):
        for rank, doc in enumerate(docs):
            # doc_id is derived from chunk metadata or text if id isn't explicitly set
            doc_id = doc.get("id", doc.get("text", ""))
            
            if doc_id not in doc_map:
                doc_map[doc_id] = {
                    "score": 0.0,
                    "chunk": doc,
                    "dense_rank": None,
                    "sparse_rank": None
                }
                
            if is_dense:
                doc_map[doc_id]["dense_rank"] = rank + 1
            else:
                doc_map[doc_id]["sparse_rank"] = rank + 1

    process_list(dense_docs, is_dense=True)
    process_list(sparse_docs, is_dense=False)
    
    for doc_id, data in doc_map.items():
        r_d = data["dense_rank"]
        r_s = data["sparse_rank"]
        
        score_d = 1.0 / (rrf_k + r_d) if r_d is not None else 0.0
        score_s = 1.0 / (rrf_k + r_s) if r_s is not None else 0.0
        
        final_score = score_d + score_s
        data["score"] = final_score
        
        # Format strings for logging
        r_d_str = r_d if r_d is not None else "N/A"
        r_s_str = r_s if r_s is not None else "N/A"
        
        logger.debug(f"[RRF_MATH] Document ID {doc_id} | Dense Rank: {r_d_str}, Sparse Rank: {r_s_str} -> Final Score: {final_score:.6f}")

    # Sort array of dicts by score
    merged_docs = [data["chunk"] for data in sorted(doc_map.values(), key=lambda x: x["score"], reverse=True)]
    
    # Add final score to output chunks
    sorted_scores = sorted(doc_map.values(), key=lambda x: x["score"], reverse=True)
    for res, data in zip(merged_docs, sorted_scores):
        res["score"] = data["score"]

    merged_docs = merged_docs[:top_k]
    
    latency_ms = int((time.time() - t0) * 1000)
    logger.info(f"[RRF_SUCCESS] Output {len(merged_docs)} unique docs | Execution: {latency_ms}ms")
    
    return merged_docs

def retrieve_hybrid(
    query: str,
    top_k: int = TOP_K_SEARCH,
    dense_weight: float = 0.6,
    sparse_weight: float = 0.4,
) -> List[Dict[str, Any]]:
    """
    Hybrid retrieval: kết hợp dense và sparse bằng Reciprocal Rank Fusion (RRF).

    Mạnh ở: giữ được cả nghĩa (dense) lẫn keyword chính xác (sparse)
    Phù hợp khi: corpus lẫn lộn ngôn ngữ tự nhiên và tên riêng/mã lỗi/điều khoản
    """
    dense_results = retrieve_dense(query, top_k=top_k)
    sparse_results = retrieve_sparse(query, top_k=top_k)
    
    # Ở đây chúng ta gán doc_id từ thuộc tính chunk['id'] hoặc md5 text nếu cần
    for i, d in enumerate(dense_results):
        if "id" not in d:
             import hashlib
             text = d.get("text", "")
             d["id"] = hashlib.md5(text.encode("utf-8")).hexdigest()

    for i, d in enumerate(sparse_results):
        if "id" not in d:
             import hashlib
             text = d.get("text", "")
             d["id"] = hashlib.md5(text.encode("utf-8")).hexdigest()

    return compute_rrf(dense_results, sparse_results, rrf_k=60, top_k=top_k)



# =============================================================================
# RERANK (Sprint 3 alternative)
# Cross-encoder để chấm lại relevance sau search rộng
# =============================================================================

def rerank(query: str, candidates: List[Dict[str, Any]], top_n: int = 3) -> List[Dict[str, Any]]:
    """
    Rerank các candidate chunks bằng LLM (OpenAI) do user không muốn cài sentence-transformers.
    """
    import time
    from openai import OpenAI
    import os
    import re
    
    t0 = time.time()
    
    if not candidates:
        logger.error("[RERANK_CRASH] Input candidates rỗng")
        return []

    logger.info(f"[RERANK_START] Query=\"{query}\" | Input Candidates from RRF: {len(candidates)}")
    
    try:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        prompt = "Bạn là hệ thống chấm điểm tài liệu. Hãy đọc câu hỏi và các tài liệu sau.\n"
        prompt += f"Câu hỏi: {query}\n\n"
        for i, chunk in enumerate(candidates):
            text = chunk.get("text", "")[:300]  # Giới hạn text để tiết kiệm token
            prompt += f"Tài liệu [{i}]: {text}\n---\n"
            
        prompt += f"\nTrích xuất chỉ số (index) của các tài liệu liên quan nhất đến câu hỏi, xếp theo thứ tự giảm dần. Chỉ in ra các số cách nhau bằng dấu phẩy. Tối đa {top_n} số."
        
        response = client.chat.completions.create(
            model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=20,
        )
        
        result_str = response.choices[0].message.content.strip()
        indices = [int(x) for x in re.findall(r'\d+', result_str)]
        
        reranked = []
        for rank, idx in enumerate(indices):
            if 0 <= idx < len(candidates):
                chunk = candidates[idx]
                doc_id = chunk.get("id", "Unknown")
                latency_ms = int((time.time() - t0) * 1000)
                
                # Giả lập Logit score giảm dần
                score = 1.0 / (rank + 1)
                chunk["score"] = score
                logger.debug(f"[RERANK_SCORE] Candidate Doc_ID: {doc_id} | Logit Score: {score:0.4f} | Rerank Latency: {latency_ms}ms")
                reranked.append(chunk)
                
        # Fill up if not enough
        if len(reranked) < top_n:
            seen = {c.get("id") for c in reranked}
            for chunk in candidates:
                if len(reranked) >= top_n: break
                if chunk.get("id") not in seen:
                    chunk["score"] = 0.0
                    reranked.append(chunk)

        top_docs = reranked[:top_n]
        logger.info(f"[RERANK_SUCCESS] Narrowed to Top {top_n} docs.")
        return top_docs
    except Exception as e:
        import traceback
        logger.error(f"[RERANK_CRASH] Rerank bằng LLM failed | Trace: {traceback.format_exc()}")
        return candidates[:top_n]

# =============================================================================
# QUERY TRANSFORMATION (Sprint 3 alternative)
# =============================================================================

def rerank_cross_encoder(query: str, candidates: List[Dict[str, Any]], top_n: int = 3) -> List[Dict[str, Any]]:
    """
    Rerank sử dụng OpenAI API để thay thế Cross-Encoder (do user từ chối sử dụng sentence-transformers).
    """
    import time
    from openai import OpenAI
    import os
    import re
    
    t0 = time.time()
    
    if not candidates:
        logger.warning("[RERANK_WARN] Input candidates rỗng.")
        return []
        
    # Khống chế 20 Broad Candidates
    candidates = candidates[:20]
    
    logger.info(f"[RERANK_START] Query=\"{query}\" | Input Candidates from RRF: {len(candidates)}")
    
    try:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        prompt = "Bạn là hệ thống chấm điểm tài liệu. Hãy đọc câu hỏi và các tài liệu sau.\n"
        prompt += f"Câu hỏi: {query}\n\n"
        for i, chunk in enumerate(candidates):
            text = chunk.get("text", "")[:300]  # Giới hạn text để tiết kiệm token
            prompt += f"Tài liệu [{i}]: {text}\n---\n"
            
        prompt += f"\nTrích xuất chỉ số (index) của các tài liệu liên quan nhất đến câu hỏi, xếp theo thứ tự giảm dần dựa trên độ liên quan. Chỉ in ra các số cách nhau bằng dấu phẩy. Tối đa {top_n} số."
        
        response = client.chat.completions.create(
            model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=20,
        )
        
        result_str = response.choices[0].message.content.strip()
        indices = [int(x) for x in re.findall(r'\d+', result_str)]
        
        reranked = []
        for rank, idx in enumerate(indices):
            if 0 <= idx < len(candidates):
                chunk = candidates[idx]
                doc_id = chunk.get("id", chunk.get("metadata", {}).get("source", f"doc_{idx}"))
                latency_ms = int((time.time() - t0) * 1000)
                
                # Giả lập Logit score giảm dần
                score = 1.0 / (rank + 1)
                
                # SPRINT 4: Recency Penalty
                metadata = chunk.get("metadata", {})
                effective_date_str = metadata.get("effective_date", "")
                if effective_date_str and effective_date_str != "unknown":
                    from datetime import datetime
                    try:
                        eff_date = datetime.strptime(effective_date_str, "%Y-%m-%d")
                        current_date = datetime.strptime("2026-04-13", "%Y-%m-%d")
                        days_old = (current_date - eff_date).days
                        if days_old > 0:
                            score = apply_recency_penalty(score, days_old, doc_id=doc_id)
                    except ValueError:
                        pass
                
                chunk["score"] = score
                logger.debug(f"[RERANK_SCORE] Candidate Doc_ID: {doc_id} | Logit Score: {score:0.4f} | Rerank Latency: {latency_ms}ms")
                reranked.append(chunk)
                
        # Fill up if not enough
        if len(reranked) < top_n:
            seen = {c.get("id") for c in reranked}
            for idx, chunk in enumerate(candidates):
                if len(reranked) >= top_n: break
                doc_id = chunk.get("id", chunk.get("metadata", {}).get("source", f"doc_{idx}"))
                if doc_id not in seen:
                    chunk["score"] = 0.0
                    latency_ms = int((time.time() - t0) * 1000)
                    logger.debug(f"[RERANK_SCORE] Candidate Doc_ID: {doc_id} | Logit Score: {0.0:0.4f} | Rerank Latency: {latency_ms}ms")
                    reranked.append(chunk)

        top_docs = reranked[:top_n]
        logger.info(f"[RERANK_SUCCESS] Narrowed to Top {top_n} docs.")
        return top_docs
        
    except Exception as e:
        import traceback
        logger.error(f"[RERANK_CRASH] Cuda OOM hoặc model load failed | Trace: {traceback.format_exc()}")
        return []

# =============================================================================
# QUERY TRANSFORMATION (Sprint 3 alternative)
# =============================================================================

def transform_query(query: str, strategy: str = "expansion") -> List[str]:
    """
    Biến đổi query để tăng recall.

    Strategies:
      - "expansion": Thêm từ đồng nghĩa, alias, tên cũ
      - "decomposition": Tách query phức tạp thành 2-3 sub-queries
      - "hyde": Sinh câu trả lời giả (hypothetical document) để embed thay query

    TODO Sprint 3 (nếu chọn query transformation):
    Gọi LLM với prompt phù hợp với từng strategy.

    Ví dụ expansion prompt:
        "Given the query: '{query}'
         Generate 2-3 alternative phrasings or related terms in Vietnamese.
         Output as JSON array of strings."

    Ví dụ decomposition:
        "Break down this complex query into 2-3 simpler sub-queries: '{query}'
         Output as JSON array."

    Khi nào dùng:
    - Expansion: query dùng alias/tên cũ (ví dụ: "Approval Matrix" → "Access Control SOP")
    - Decomposition: query hỏi nhiều thứ một lúc
    - HyDE: query mơ hồ, search theo nghĩa không hiệu quả
    """
    # TODO Sprint 3: Implement query transformation
    # Tạm thời trả về query gốc
    return [query]


# =============================================================================
# SPRINT 3: MASTER RETRIEVE PIPELINE (005_retrieve_pipeline.md)
# =============================================================================

async def _retrieve_documents_async(query: str, fast_path: bool = True) -> List[Dict[str, Any]]:
    """
    Luồng truy xuất tổng master pipeline tích hợp song song và kiểm soát ngân sách thời gian.
    """
    t_start = time.time()
    logger.info(f"[PIPELINE_INIT] Receive Query: \"{query}\" | Budget limit: 250ms")

    # Fast Path Bypass
    if fast_path and re.search(r'\b(ERR-\d+)\b', query, re.IGNORECASE):
        logger.info(f"[PIPELINE_BYPASS] Query matches exact keyword pattern -> Bypassing Dense & Reranker.")
        sparse_res = retrieve_sparse(query, top_k=3)
        total_latency = int((time.time() - t_start) * 1000)
        logger.info(f"[PIPELINE_FINAL] Pipeline Latency: {total_latency}ms | Final Context ready (Top 3).")
        return sparse_res[:3]

    # Concurrent Dense & Sparse execution via asyncio.to_thread
    dense_task = asyncio.to_thread(retrieve_dense, query, TOP_K_SEARCH)
    sparse_task = asyncio.to_thread(retrieve_sparse, query, TOP_K_SEARCH)
    
    dense_results, sparse_results = await asyncio.gather(dense_task, sparse_task)
    
    logger.info(f"[PIPELINE_DENSE_SPARSE] Async Phase Done - Dense: {len(dense_results)} docs, Sparse: {len(sparse_results)} docs.")

    # Assign IDs string md5 for RRF 
    import hashlib
    for res_list in (dense_results, sparse_results):
        for d in res_list:
            if "id" not in d:
                 text = d.get("text", "")
                 d["id"] = hashlib.md5(text.encode("utf-8")).hexdigest()
                 
    # RRF Fusion and truncate to top 20 max
    merged_docs = compute_rrf(dense_results, sparse_results, rrf_k=60, top_k=20)
    
    logger.info(f"[PIPELINE_STAGE] RRF output size: {len(merged_docs)} docs (Max 20 Broad Candidates) -> Entering Cross-Encoder.")

    # LLM Reranking (Cross-Encoder Alternative)
    top_3_candidates = rerank_cross_encoder(query, merged_docs, top_n=3)
    
    total_latency = int((time.time() - t_start) * 1000)
    logger.info(f"[PIPELINE_FINAL] Pipeline Latency: {total_latency}ms | Final Context ready (Top 3).")
    return top_3_candidates


@diagnostic_decorator
def retrieve_documents(query: str, fast_path: bool = True) -> List[Dict[str, Any]]:
    """
    Wrapper đồng bộ gọi cấu trúc Async của Master Pipeline
    """
    return asyncio.run(_retrieve_documents_async(query, fast_path))


# =============================================================================
# GENERATION — GROUNDED ANSWER FUNCTION
# =============================================================================

def build_context_block(chunks: List[Dict[str, Any]]) -> str:
    """
    Đóng gói danh sách chunks thành context block để đưa vào prompt.

    Format: structured snippets với source, section, score (từ slide).
    Mỗi chunk có số thứ tự [1], [2], ... để model dễ trích dẫn.
    """
    context_parts = []
    for i, chunk in enumerate(chunks, 1):
        meta = chunk.get("metadata", {})
        source = meta.get("source", "unknown")
        section = meta.get("section", "")
        score = chunk.get("score", 0)
        text = chunk.get("text", "")
        
        effective_date = meta.get("effective_date", "")
        department = meta.get("department", "")

        # TODO: Tùy chỉnh format nếu muốn (thêm effective_date, department, ...)
        header = f"[{i}] {source}"
        if section:
            header += f" | {section}"
        if effective_date and effective_date != "unknown":
            header += f" | Effective Date: {effective_date}"
        if department and department != "unknown":
            header += f" | Dept: {department}"
        if score > 0:
            header += f" | score={score:.2f}"

        context_parts.append(f"{header}\n{text}")

    return "\n\n".join(context_parts)


def build_grounded_prompt(query: str, context_block: str) -> List[Dict[str, str]]:
    """
    Xây dựng grounded prompt. Đọc system_prompt từ thư mục cha.
    Sprint 4: Token Budget profiling.
    """
    try:
        from pathlib import Path
        prompt_file = Path(__file__).resolve().parents[2] / "prompt_templates.txt"
        system_prompt = prompt_file.read_text(encoding="utf-8").strip()
    except Exception as e:
        logger.warning(f"[ERROR_TREE] Cannot read prompt template: {e}")
        system_prompt = "You are a helpful assistant. Use context to answer. If no context answers the question, say: Xin lỗi, hệ thống hiện không có đủ dữ liệu trong tài liệu để trả lời câu hỏi này."

    user_prompt = f"# CONTEXT:\n{context_block}\n\n# USER QUESTION:\n{query}"

    budget_used = (len(system_prompt) + len(user_prompt)) // 4
    logger.info(f"[DIAGNOSTICS] Prompt Token Budget Estimated: {budget_used} tokens.")
    if budget_used > 6000:
        logger.warning(f"[ERROR_TREE] [CONTEXT_TOO_LONG] Prompt size is very large ({budget_used} tokens).")

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]


def call_llm(messages: List[Dict[str, str]]) -> str:
    """
    Gọi LLM để sinh câu trả lời (Có đo lường đính kèm phục vụ Diagnostics Sprint 4).
    """
    t0 = time.time()
    try:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        response = client.chat.completions.create(
            model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
            messages=messages,
            temperature=0,
            max_tokens=512,
        )
        answer = response.choices[0].message.content
        latency_ms = int((time.time() - t0) * 1000)
        
        usage = response.usage
        logger.info(f"[DIAGNOSTICS] LLM Generation Latency: {latency_ms}ms | Tokens: prompt={usage.prompt_tokens}, completion={usage.completion_tokens}, total={usage.total_tokens}")
        
        if "hệ thống hiện không có đủ dữ liệu" in answer.lower():
            logger.warning("[ERROR_TREE] [HALLUCINATION_FALLBACK] LLM triggered Graceful Fallback.")
            
        return answer
    except Exception as e:
        logger.error(f"[ERROR_TREE] [LLM_FAILED] LỖI HỆ THỐNG KHI GỌI LLM: {str(e)}")
        return f"LỖI HỆ THỐNG KHI GỌI LLM: {str(e)}"


def rag_answer(
    query: str,
    retrieval_mode: str = "dense",
    top_k_search: int = TOP_K_SEARCH,
    top_k_select: int = TOP_K_SELECT,
    use_rerank: bool = False,
    verbose: bool = False,
) -> Dict[str, Any]:
    """
    Pipeline RAG hoàn chỉnh: query → retrieve → (rerank) → generate.

    Args:
        query: Câu hỏi
        retrieval_mode: "dense" | "sparse" | "hybrid"
        top_k_search: Số chunk lấy từ vector store (search rộng)
        top_k_select: Số chunk đưa vào prompt (sau rerank/select)
        use_rerank: Có dùng cross-encoder rerank không
        verbose: In thêm thông tin debug

    Returns:
        Dict với:
          - "answer": câu trả lời grounded
          - "sources": list source names trích dẫn
          - "chunks_used": list chunks đã dùng
          - "query": query gốc
          - "config": cấu hình pipeline đã dùng

    TODO Sprint 2 — Implement pipeline cơ bản:
    1. Chọn retrieval function dựa theo retrieval_mode
    2. Gọi rerank() nếu use_rerank=True
    3. Truncate về top_k_select chunks
    4. Build context block và grounded prompt
    5. Gọi call_llm() để sinh câu trả lời
    6. Trả về kết quả kèm metadata

    TODO Sprint 3 — Thử các variant:
    - Variant A: đổi retrieval_mode="hybrid"
    - Variant B: bật use_rerank=True
    - Variant C: thêm query transformation trước khi retrieve
    """
    config = {
        "retrieval_mode": retrieval_mode,
        "top_k_search": top_k_search,
        "top_k_select": top_k_select,
        "use_rerank": use_rerank,
    }

    # --- Bước 1 & 2: Retrieve + Rerank ---
    if retrieval_mode == "master":
        # Sprint 3: Master Retrieve Pipeline covers Dense + Sparse + RRF + Rerank
        candidates = retrieve_documents(query, fast_path=True)
    else:
        if retrieval_mode == "dense":
            candidates = retrieve_dense(query, top_k=top_k_search)
        elif retrieval_mode == "sparse":
            candidates = retrieve_sparse(query, top_k=top_k_search)
        elif retrieval_mode == "hybrid":
            candidates = retrieve_hybrid(query, top_k=top_k_search)
        else:
            raise ValueError(f"retrieval_mode không hợp lệ: {retrieval_mode}")

        if verbose:
            print(f"\n[RAG] Query: {query}")
            print(f"[RAG] Retrieved {len(candidates)} candidates (mode={retrieval_mode})")
            for i, c in enumerate(candidates[:3]):
                print(f"  [{i+1}] score={c.get('score', 0):.3f} | {c['metadata'].get('source', '?')}")

        if use_rerank:
            candidates = rerank_cross_encoder(query, candidates, top_n=top_k_select)
        else:
            candidates = candidates[:top_k_select]

    if verbose:
        print(f"[RAG] After select: {len(candidates)} chunks")

    # --- Bước 3: Build context và prompt ---
    context_block = build_context_block(candidates)
    prompt = build_grounded_prompt(query, context_block)

    if verbose:
        print(f"\n[RAG] Prompt:\n{prompt[:500]}...\n")

    # --- Bước 4: Generate ---
    answer = call_llm(prompt)

    # --- Bước 5: Extract sources ---
    sources = list({
        c["metadata"].get("source", "unknown")
        for c in candidates
    })

    return {
        "query": query,
        "answer": answer,
        "sources": sources,
        "chunks_used": candidates,
        "config": config,
    }


# =============================================================================
# SPRINT 3: SO SÁNH BASELINE VS VARIANT
# =============================================================================

def compare_retrieval_strategies(query: str) -> None:
    """
    So sánh các retrieval strategies với cùng một query.

    TODO Sprint 3:
    Chạy hàm này để thấy sự khác biệt giữa dense, sparse, hybrid.
    Dùng để justify tại sao chọn variant đó cho Sprint 3.

    A/B Rule (từ slide): Chỉ đổi MỘT biến mỗi lần.
    """
    print(f"\n{'='*60}")
    print(f"Query: {query}")
    print('='*60)

    strategies = ["dense", "hybrid"]  # Thêm "sparse" sau khi implement

    for strategy in strategies:
        print(f"\n--- Strategy: {strategy} ---")
        try:
            result = rag_answer(query, retrieval_mode=strategy, verbose=False)
            print(f"Answer: {result['answer']}")
            print(f"Sources: {result['sources']}")
        except NotImplementedError as e:
            print(f"Chưa implement: {e}")
        except Exception as e:
            print(f"Lỗi: {e}")


# =============================================================================
# MAIN — Demo và Test
# =============================================================================

def run_test():
    print("🚀 TESTING...\n")
    print("="*60)
    
    # Tạo Ảo ảnh (Mock Chunks) giả lập kết quả từ Retrieval
    mock_chunks = [
        {
            "metadata": {"source": "data/docs/policy_refund_v4.txt", "section": "Điều 2", "effective_date": "2026-02-01"},
            "text": "Khách hàng được quyền yêu cầu hoàn tiền khi đáp ứng đủ các điều kiện sau: Yêu cầu được gửi trong vòng 7 ngày làm việc kể từ thời điểm xác nhận đơn hàng."
        },
        {
            "metadata": {"source": "data/docs/policy_refund_v4.txt", "section": "Điều 3", "effective_date": "2026-02-01"},
            "text": "Sản phẩm thuộc danh mục hàng kỹ thuật số (license key, subscription) là ngoại lệ không được hoàn tiền."
        }
    ]

    context_block = build_context_block(mock_chunks)

    # --- TEST CASE 1: CÓ THÔNG TIN (Kỳ vọng: Trả lời có trích dẫn) ---
    query_1 = "Tôi mua license key phần mềm diệt virus hôm qua thì hôm nay có được hoàn tiền không?"
    print(f"👉 TEST CASE 1 (Có thông tin):\nUser hỏi: {query_1}")
    prompt_1 = build_grounded_prompt(query_1, context_block)
    answer_1 = call_llm(prompt_1)
    print(f"\n🤖 LLM Trả lời:\n{answer_1}\n")
    print("-" * 60)

    # --- TEST CASE 2: KHÔNG CÓ THÔNG TIN (Kỳ vọng: Khởi động Abstain) ---
    query_2 = "Làm thế nào để xin cấp quyền Level 3 (Admin)?"
    print(f"👉 TEST CASE 2 (Ép Abstain - Chống Hallucination):\nUser hỏi: {query_2}")
    prompt_2 = build_grounded_prompt(query_2, context_block)
    answer_2 = call_llm(prompt_2)
    print(f"\n🤖 LLM Trả lời:\n{answer_2}\n")
    print("="*60)

# if __name__ == "__main__":
#     print("=" * 60)
#     print("Sprint 2 + 3: RAG Answer Pipeline")
#     print("=" * 60)

#     # Test queries từ data/test_questions.json
#     test_queries = [
#         "SLA xử lý ticket P1 là bao lâu?",
#         "Khách hàng có thể yêu cầu hoàn tiền trong bao nhiêu ngày?",
#         "Ai phải phê duyệt để cấp quyền Level 3?",
#         "ERR-403-AUTH là lỗi gì?",  # Query không có trong docs → kiểm tra abstain
#     ]

#     print("\n--- Sprint 2: Test Baseline (Dense) ---")
#     for query in test_queries:
#         print(f"\nQuery: {query}")
#         try:
#             result = rag_answer(query, retrieval_mode="dense", verbose=True)
#             print(f"Answer: {result['answer']}")
#             print(f"Sources: {result['sources']}")
#         except NotImplementedError:
#             print("Chưa implement — hoàn thành TODO trong retrieve_dense() và call_llm() trước.")
#         except Exception as e:
#             print(f"Lỗi: {e}")

#     # Uncomment sau khi Sprint 3 hoàn thành:
#     # print("\n--- Sprint 3: So sánh strategies ---")
#     # compare_retrieval_strategies("Approval Matrix để cấp quyền là tài liệu nào?")
#     # compare_retrieval_strategies("ERR-403-AUTH")

#     print("\n\nViệc cần làm Sprint 2:")
#     print("  1. Implement retrieve_dense() — query ChromaDB")
#     print("  2. Implement call_llm() — gọi OpenAI hoặc Gemini")
#     print("  3. Chạy rag_answer() với 3+ test queries")
#     print("  4. Verify: output có citation không? Câu không có docs → abstain không?")

#     print("\nViệc cần làm Sprint 3:")
#     print("  1. Chọn 1 trong 3 variants: hybrid, rerank, hoặc query transformation")
#     print("  2. Implement variant đó")
#     print("  3. Chạy compare_retrieval_strategies() để thấy sự khác biệt")
#     print("  4. Ghi lý do chọn biến đó vào docs/tuning-log.md")

if __name__ == "__main__":
    run_test()
