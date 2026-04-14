import sys
from pathlib import Path
from datetime import datetime
from typing import Any

# Thêm Day 08 vào path để dùng lại retrieve_dense
_ROOT = str(Path(__file__).parents[3])  # /home/.../C401-F2-Lab08
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

_DAY08_LAB = str(Path(__file__).parents[3] / "day08" / "lab")
if _DAY08_LAB not in sys.path:
    sys.path.insert(0, _DAY08_LAB)

TOP_K = 3

def run(state: dict) -> dict:
    task = state.get("task", "")
    log_entry = {
        "worker": "retrieval_worker",
        "input": {"task": task, "top_k": TOP_K},
        "timestamp": datetime.now().isoformat(),
    }

    try:
        from day08.lab.src.retrieval.rag_answer import retrieve_dense
        chunks = retrieve_dense(task, top_k=TOP_K)
    except Exception as e:
        # Fallback nếu Day 08 không load được
        chunks = _fallback_retrieve(task)
        log_entry["warning"] = f"Day08 import failed, using fallback: {e}"

    sources = list({c["metadata"].get("source", "unknown") for c in chunks})
    log_entry["output"] = {"chunks_count": len(chunks), "sources": sources}

    state["retrieved_chunks"]  = chunks
    state["retrieved_sources"] = sources
    state["workers_called"]    = state.get("workers_called", []) + ["retrieval_worker"]
    state["history"].append({"step": "retrieval_worker", **log_entry})

    if not hasattr(state.get("worker_io_logs"), "append"):
        state["worker_io_logs"] = []
    state["worker_io_logs"].append(log_entry)

    return state

def _fallback_retrieve(task: str) -> list:
    """Fallback: đọc trực tiếp ChromaDB local nếu Day 08 import fail."""
    try:
        import chromadb
        from pathlib import Path
        import os
        from openai import OpenAI
        from dotenv import load_dotenv

        load_dotenv()

        db_path = Path(__file__).parents[1] / "chroma_db"
        client = chromadb.PersistentClient(path=str(db_path))
        # Try Day 09 collection first, fallback to Day 08
        existing = [c.name for c in client.list_collections()]
        col_name = "day09_docs" if "day09_docs" in existing else "rag_lab"
        col = client.get_collection(col_name)

        openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        embedding = openai_client.embeddings.create(
            input=task, model="text-embedding-3-small"
        ).data[0].embedding

        results = col.query(query_embeddings=[embedding], n_results=3,
                            include=["documents", "metadatas", "distances"])
        chunks = []
        for doc, meta, dist in zip(results["documents"][0],
                                   results["metadatas"][0],
                                   results["distances"][0]):
            chunks.append({"text": doc, "metadata": meta, "score": round(1 - dist, 4)})
        return chunks
    except Exception:
        return []

if __name__ == "__main__":
    state = {'task': 'SLA ticket P1 deadline là bao lâu?', 'history': [], 'workers_called': []}
    result = run(state)
    print(f'Chunks: {len(result["retrieved_chunks"])}')
    print(f'Sources: {result["retrieved_sources"]}')
