"""
setup_index.py — Build ChromaDB index from data/docs/
Sprint 2B: Chạy một lần để index 5 tài liệu vào ChromaDB.

Chạy:
    python setup_index.py

Output:
    ./chroma_db/  — ChromaDB persistent storage
"""

import os
import sys
from pathlib import Path

DOCS_DIR = Path("data/docs")
CHROMA_PATH = "./chroma_db"
COLLECTION_NAME = "day09_docs"
CHUNK_SIZE = 500        # characters
CHUNK_OVERLAP = 80      # characters overlap giữa các chunks


# ─────────────────────────────────────────────
# 1. Load tất cả .txt files từ data/docs/
# ─────────────────────────────────────────────

def load_docs(docs_dir: Path) -> list[dict]:
    """Đọc tất cả .txt files, trả về list of {text, source, filepath}."""
    docs = []
    for fpath in sorted(docs_dir.glob("*.txt")):
        try:
            text = fpath.read_text(encoding="utf-8").strip()
            if text:
                docs.append({"text": text, "source": fpath.name, "filepath": str(fpath)})
                print(f"  ✓ Loaded {fpath.name} ({len(text)} chars)")
            else:
                print(f"  ⚠ Skipped {fpath.name} (empty)")
        except UnicodeDecodeError:
            print(f"  ⚠ Skipped {fpath.name} (binary/non-UTF8 — chỉ .txt mới index được)")
    return docs


# ─────────────────────────────────────────────
# 2. Chunk documents
# ─────────────────────────────────────────────

def chunk_text(text: str, source: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[dict]:
    """
    Chia text thành chunks với overlap.
    Cố gắng cắt ở newline để giữ nguyên cấu trúc câu/đoạn.
    """
    chunks = []
    start = 0
    chunk_id = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))

        # Tìm newline gần nhất để cắt đẹp hơn
        if end < len(text):
            newline_pos = text.rfind("\n", start, end)
            if newline_pos > start + chunk_size // 2:
                end = newline_pos

        chunk_text = text[start:end].strip()
        if chunk_text:
            chunks.append({
                "id": f"{source}__chunk{chunk_id:03d}",
                "text": chunk_text,
                "metadata": {
                    "source": source,
                    "chunk_id": chunk_id,
                    "char_start": start,
                    "char_end": end,
                }
            })
            chunk_id += 1

        start = max(start + 1, end - overlap)  # overlap để không mất context

    return chunks


# ─────────────────────────────────────────────
# 3. Get embedding function
# ─────────────────────────────────────────────

def get_embed_fn():
    """
    Trả về embedding function.
    Ưu tiên: SentenceTransformers (offline) → OpenAI → random (test only)
    """
    # Option A: Sentence Transformers (không cần API key)
    try:
        from sentence_transformers import SentenceTransformer
        print("  Using: SentenceTransformer (all-MiniLM-L6-v2)")
        model = SentenceTransformer("all-MiniLM-L6-v2")
        def embed(texts: list[str]) -> list[list[float]]:
            return model.encode(texts, show_progress_bar=False).tolist()
        return embed
    except ImportError:
        pass

    # Option B: OpenAI
    try:
        from openai import OpenAI
        from dotenv import load_dotenv
        load_dotenv()
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            print("  Using: OpenAI text-embedding-3-small")
            client = OpenAI(api_key=api_key)
            def embed(texts: list[str]) -> list[list[float]]:
                resp = client.embeddings.create(input=texts, model="text-embedding-3-small")
                return [d.embedding for d in resp.data]
            return embed
    except ImportError:
        pass

    # Fallback: random (KHÔNG dùng production)
    import random
    print("  ⚠️  WARNING: Using random embeddings — install sentence-transformers!")
    def embed(texts: list[str]) -> list[list[float]]:
        return [[random.gauss(0, 1) for _ in range(384)] for _ in texts]
    return embed


# ─────────────────────────────────────────────
# 4. Build ChromaDB index
# ─────────────────────────────────────────────

def build_index(docs: list[dict], embed_fn, chroma_path: str = CHROMA_PATH, collection_name: str = COLLECTION_NAME):
    """Index tất cả chunks vào ChromaDB."""
    import chromadb

    client = chromadb.PersistentClient(path=chroma_path)

    # Xoá collection cũ nếu có (để re-index sạch)
    try:
        client.delete_collection(collection_name)
        print(f"  Deleted existing collection '{collection_name}'")
    except Exception:
        pass

    collection = client.create_collection(
        collection_name,
        metadata={"hnsw:space": "cosine"}
    )

    all_chunks = []
    for doc in docs:
        chunks = chunk_text(doc["text"], doc["source"])
        all_chunks.extend(chunks)
        print(f"  {doc['source']}: {len(chunks)} chunks")

    if not all_chunks:
        print("  ❌ No chunks to index!")
        return 0

    print(f"\n  Total chunks: {len(all_chunks)}")
    print("  Embedding...", end=" ", flush=True)

    # Batch embed để tránh OOM
    BATCH = 32
    ids, texts, metas, embeddings = [], [], [], []
    for i in range(0, len(all_chunks), BATCH):
        batch = all_chunks[i:i + BATCH]
        batch_texts = [c["text"] for c in batch]
        batch_embeddings = embed_fn(batch_texts)
        for chunk, emb in zip(batch, batch_embeddings):
            ids.append(chunk["id"])
            texts.append(chunk["text"])
            metas.append(chunk["metadata"])
            embeddings.append(emb)
        print(".", end="", flush=True)

    print()
    collection.add(
        ids=ids,
        documents=texts,
        metadatas=metas,
        embeddings=embeddings,
    )

    print(f"  ✅ Indexed {len(all_chunks)} chunks into '{collection_name}'")
    return len(all_chunks)


# ─────────────────────────────────────────────
# 5. Smoke test — quick retrieval check
# ─────────────────────────────────────────────

def smoke_test(embed_fn, chroma_path: str = CHROMA_PATH, collection_name: str = COLLECTION_NAME):
    """Kiểm tra nhanh index bằng cách query 3 câu hỏi test."""
    import chromadb

    client = chromadb.PersistentClient(path=chroma_path)
    col = client.get_collection(collection_name)

    test_queries = [
        "SLA ticket P1 response time",
        "hoàn tiền Flash Sale điều kiện",
        "cấp quyền Level 3 phê duyệt",
    ]

    print("\n  Smoke test queries:")
    all_ok = True
    for q in test_queries:
        emb = embed_fn([q])[0]
        results = col.query(query_embeddings=[emb], n_results=1,
                            include=["documents", "metadatas", "distances"])
        if results["documents"][0]:
            doc = results["documents"][0][0]
            src = results["metadatas"][0][0].get("source", "?")
            score = round(1 - results["distances"][0][0], 3)
            print(f"    [{score}] {src}: {doc[:70]}...")
        else:
            print(f"    ❌ No result for: {q}")
            all_ok = False

    return all_ok


# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("Day 09 Lab — ChromaDB Index Builder")
    print("=" * 60)

    print(f"\n📂 Loading docs from {DOCS_DIR}/ ...")
    docs = load_docs(DOCS_DIR)

    if not docs:
        print(f"\n❌ Không tìm thấy file .txt nào trong {DOCS_DIR}/")
        print("   Kiểm tra lại: data/docs/ phải có ít nhất 1 file .txt có thể đọc được.")
        sys.exit(1)

    print(f"\n🔧 Setting up embedding function...")
    embed_fn = get_embed_fn()

    print(f"\n📑 Chunking & indexing {len(docs)} docs...")
    n = build_index(docs, embed_fn)

    if n > 0:
        print(f"\n🔍 Running smoke test...")
        ok = smoke_test(embed_fn)
        if ok:
            print("\n✅ Index ready! Workers can now retrieve from ChromaDB.")
        else:
            print("\n⚠️  Smoke test had issues — check the output above.")
    else:
        print("\n❌ Index failed — no chunks were created.")
        sys.exit(1)