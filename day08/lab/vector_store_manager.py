"""
vector_store_manager.py
=======================
Utilities để khởi tạo và lấy Collection từ ChromaDB.
Dùng chung cho build_index(), list_chunks(), và diagnostics_report()
để đảm bảo tất cả trỏ đúng vào cùng một collection.
"""

from pathlib import Path

try:
    import chromadb
    _CHROMADB_IMPORT_ERROR = None
except ImportError as exc:
    chromadb = None
    _CHROMADB_IMPORT_ERROR = exc


def get_chroma_collection(
    db_dir: Path,
    collection_name: str = "rag_lab",
) -> "chromadb.api.models.Collection":
    """
    Khởi tạo ChromaDB PersistentClient và trả về collection sẵn sàng dùng.

    Args:
        db_dir:          Thư mục lưu dữ liệu Chroma (sẽ tạo nếu chưa có).
        collection_name: Tên collection (mặc định "rag_lab").

    Returns:
        chromadb Collection với cosine similarity.

    Raises:
        RuntimeError: nếu package chromadb chưa được cài.
    """
    if chromadb is None:
        raise RuntimeError(
            "Chưa cài `chromadb`. Chạy `pip install chromadb` rồi thử lại."
        ) from _CHROMADB_IMPORT_ERROR

    db_dir.mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(path=str(db_dir))

    collection = client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )

    return collection